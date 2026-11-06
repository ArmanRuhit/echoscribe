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
let sessionLanguage = "en";
let sessionModel = "";
let sessionDevice = "";
let sessionCompute = "";
let sessionClock = "";
let readySeen = false;
let samplesSent = 0;
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
    } else if (message.type === "VIDEO_CLOCK") {
        sendClock(message);
    }
});

async function start({ streamId, title, url, language }) {
    sessionId = crypto.randomUUID();
    sessionTitle = title;
    sessionUrl = url;
    sessionLanguage = language || "en";
    sessionModel = "";
    sessionDevice = "";
    sessionCompute = "";
    sessionClock = "";
    stopping = false;
    readySeen = false;
    reconnectDelay = 1000;
    samplesSent = 0;
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
    await audioContext.resume();

    source = audioContext.createMediaStreamSource(stream);
    source.connect(audioContext.destination); // keep the lecture audible

    const track = stream.getAudioTracks()[0];
    track.addEventListener("ended", () => {
        void stop({ type: "ENDED", message: "Tab audio ended" });
    });

    connectSocket();
    console.log("EchoScribe capture started");
}

// Attached only after ready: a refused language must never produce PCM.
async function attachWorklet() {
    if (worklet || !audioContext || !source) return;

    await audioContext.audioWorklet.addModule("pcm-worklet.js");

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
                sampleRate: 16000,
                language: sessionLanguage
            })
        );
        for (const chunk of pending.splice(0)) socket.send(chunk);
        console.log("EchoScribe server connected");
    });

    socket.addEventListener("message", async (event) => {
        let data;
        try {
            data = JSON.parse(event.data);
        } catch {
            return;
        }

        if (data.type === "ready") {
            readySeen = true;
            reconnectDelay = 1000;
            sessionLanguage = data.language || sessionLanguage;
            sessionModel = data.model || "";
            sessionDevice = data.device || "";
            sessionCompute = data.compute || "";
            sessionClock = data.clock || "pending";
            try {
                await attachWorklet();
            } catch (error) {
                await stop({
                    type: "ERROR",
                    message: `Audio worklet failed: ${error.message}`
                });
                return;
            }
            sendPanel({
                type: "STATUS",
                state: "recording",
                title: sessionTitle,
                language: sessionLanguage,
                model: sessionModel,
                device: sessionDevice,
                compute: sessionCompute,
                clock: sessionClock
            });
            console.log(
                "EchoScribe server ready:",
                sessionModel,
                sessionDevice,
                data.resumed ? "(resumed)" : ""
            );
        } else if (data.type === "segment") {
            if (data.clock) sessionClock = data.clock;
            console.log(`[${data.start.toFixed(1)}s] ${data.text}`);
            sendPanel({
                type: "SEGMENT",
                start: data.video ?? data.start,
                text: data.text,
                replayFrom: data.replayFrom
            });
        } else if (data.type === "error") {
            // After ready the only error is a failed transcription: the session is dead.
            await stop({
                type: "ERROR",
                message: data.message || "server error"
            });
        }
    });

    socket.addEventListener("close", () => {
        socketOpen = false;
        if (!readySeen) {
            void stop({
                type: "ERROR",
                message: "Server unreachable at ws://127.0.0.1:8765"
            });
            return;
        }
        scheduleReconnect();
    });

    socket.addEventListener("error", () => {
        // close follows; an initial failure is reported there.
        if (readySeen) scheduleReconnect();
    });
}

function scheduleReconnect() {
    if (stopping || reconnectTimer) return;
    if (socket && socket.readyState !== WebSocket.CLOSED) return;

    sendPanel({
        type: "STATUS",
        state: "reconnecting",
        title: sessionTitle,
        language: sessionLanguage,
        model: sessionModel,
        device: sessionDevice,
        compute: sessionCompute,
        clock: sessionClock
    });
    console.warn(`EchoScribe server offline; retrying in ${reconnectDelay}ms`);

    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        reconnectDelay = Math.min(reconnectDelay * 2, 10000);
        connectSocket();
    }, reconnectDelay);
}

// Clock frames ride the audio clock; while audio is queued the anchor would point
// at samples the server has not received yet, so those readings are dropped.
function sendClock({ position, paused, rate }) {
    if (!socketOpen || socket?.readyState !== WebSocket.OPEN || pending.length > 0) return;
    socket.send(
        JSON.stringify({
            type: "clock",
            video: position,
            audio: samplesSent / 16000,
            paused: Boolean(paused),
            rate
        })
    );
}

function sendChunk(chunk) {
    socket.send(chunk);
    samplesSent += chunk.byteLength / 2;
}

function sendPcm(buffer) {
    if (socketOpen && socket?.readyState === WebSocket.OPEN) {
        while (pending.length > 0 && socket.bufferedAmount < MAX_SOCKET_BUFFER) {
            sendChunk(pending.shift());
        }

        if (pending.length === 0 && socket.bufferedAmount < MAX_SOCKET_BUFFER) {
            sendChunk(buffer);
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

    worklet = null;
    source = null;
    audioContext = null;
    stream = null;

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