let audioContext = null;
let source = null;
let worklet = null;
let stream = null;
let socket = null;
let socketOpen = false;
let stopping = false;
let reconnectTimer = null;
let reconnectDelay = 1000;
let sessionId = "";
let sessionTitle = "";
let sessionUrl = "";
let droppedFrames = 0;
const pending = [];
const MAX_PENDING = 300;
const MAX_SOCKET_BUFFER = 1_000_000;

function sendPanel(message) {
    void chrome.runtime.sendMessage({ target: "panel", ...message }).catch(() => {});
}

chrome.runtime.onMessage.addListener((message) => {
    if (message?.target !== "offscreen") return;

    if (message.type === "START") {
        void start(message).catch((error) => {
            void stop({ type: "ERROR", message: error.message || String(error) });
        });
    } else if (message.type === "STOP") {
        void stop();
    }
});

async function start({ streamId, title, url }) {
    sessionId = crypto.randomUUID();
    sessionTitle = title;
    sessionUrl = url;
    stopping = false;
    reconnectDelay = 1000;
    droppedFrames = 0;
    pending.length = 0;

    stream = await navigator.mediaDevices.getUserMedia({
        audio: {
            mandatory: {
                chromeMediaSource: "tab",
                chromeMediaSourceId: streamId
            }
        },
        video: false
    });

    audioContext = new AudioContext({ sampleRate: 16000 });
    await audioContext.audioWorklet.addModule("pcm-worklet.js");
    await audioContext.resume();

    source = audioContext.createMediaStreamSource(stream);
    source.connect(audioContext.destination); // keep the lecture audible

    worklet = new AudioWorkletNode(audioContext, "pcm-worklet", {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        channelCount: 1
    });

    const mute = audioContext.createGain();
    mute.gain.value = 0;
    source.connect(worklet);
    worklet.connect(mute).connect(audioContext.destination);
    worklet.port.onmessage = (event) => sendPcm(event.data);

    const track = stream.getAudioTracks()[0];
    track.addEventListener("ended", () => {
        void stop({ type: "ENDED", message: "Tab audio ended" });
    });

    connectSocket();
    sendPanel({ type: "STATUS", state: "recording", title });
    console.log("EchoScribe capture started");
}

function connectSocket() {
    socket = new WebSocket("ws://127.0.0.1:8765");

    socket.addEventListener("open", () => {
        socketOpen = true;
        socket.send(
            JSON.stringify({
                type: "start",
                sessionId,
                title: sessionTitle,
                url: sessionUrl,
                sampleRate: 16000
            })
        );
        for (const chunk of pending.splice(0)) socket.send(chunk);
        sendPanel({ type: "STATUS", state: "recording", title: sessionTitle });
        console.log("EchoScribe server connected");
    });

    socket.addEventListener("message", (event) => {
        let data;
        try {
            data = JSON.parse(event.data);
        } catch {
            return;
        }

        if (data.type === "ready") {
            reconnectDelay = 1000;
            console.log(
                "EchoScribe server ready:",
                data.model,
                data.resumed ? "(resumed)" : ""
            );
        } else if (data.type === "segment") {
            console.log(`[${data.start.toFixed(1)}s] ${data.text}`);
            sendPanel({ type: "SEGMENT", start: data.start, text: data.text });
        } else if (data.type === "error") {
            console.error("EchoScribe server error:", data.message);
        }
    });

    socket.addEventListener("close", () => {
        socketOpen = false;
        scheduleReconnect();
    });

    socket.addEventListener("error", () => {
        scheduleReconnect();
    });
}

function scheduleReconnect() {
    if (stopping || reconnectTimer) return;
    if (socket && socket.readyState !== WebSocket.CLOSED) return;

    sendPanel({ type: "STATUS", state: "reconnecting", title: sessionTitle });
    console.warn(`EchoScribe server offline; retrying in ${reconnectDelay}ms`);

    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        reconnectDelay = Math.min(reconnectDelay * 2, 10000);
        connectSocket();
    }, reconnectDelay);
}

function sendPcm(buffer) {
    if (socketOpen && socket?.readyState === WebSocket.OPEN) {
        while (pending.length > 0 && socket.bufferedAmount < MAX_SOCKET_BUFFER) {
            socket.send(pending.shift());
        }

        if (pending.length === 0 && socket.bufferedAmount < MAX_SOCKET_BUFFER) {
            socket.send(buffer);
            return;
        }
    }

    if (pending.length >= MAX_PENDING) {
        pending.shift();
        droppedFrames += 1;
        if (droppedFrames === 1) {
            console.warn("EchoScribe queue full; dropping oldest audio");
        }
    }
    pending.push(buffer);
}

async function stop(reason = {}) {
    if (stopping) return;
    stopping = true;

    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }

    worklet?.disconnect();
    source?.disconnect();
    stream?.getTracks().forEach((track) => track.stop());

    if (socket) {
        if (socket.readyState === WebSocket.OPEN) {
            try {
                socket.send(JSON.stringify({ type: "stop" }));
            } catch {
                // socket closed mid-send
            }
        }
        socket.close();
    }

    socketOpen = false;

    if (audioContext) {
        try {
            await audioContext.close();
        } catch {
            // already closed
        }
    }

    const isError = reason.type === "ERROR";
    const message = isError
        ? { target: "background", type: "ERROR", message: reason.message }
        : { target: "background", type: "STOPPED" };

    sendPanel({
        type: "STATUS",
        state: isError ? "error" : "idle",
        message: reason.message || ""
    });

    try {
        await chrome.runtime.sendMessage(message);
    } catch {
        // service worker may be restarting
    }

    console.log("EchoScribe capture stopped");
}