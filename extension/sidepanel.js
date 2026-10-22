const statusEl = document.querySelector("#status");
const transcriptEl = document.querySelector("#transcript");
let emptyEl = transcriptEl.querySelector(".empty");

chrome.runtime.onMessage.addListener((message) => {
    if (message?.target !== "panel") return;

    if (message.type === "STATUS") {
        setStatus(message);
    } else if (message.type === "SEGMENT") {
        appendSegment(message.start, message.text);
    }
});

function setStatus({ state, title, message }) {
    if (state === "recording") {
        statusEl.textContent = title ? `Recording: ${title}` : "Recording";
    } else if (state === "reconnecting") {
        statusEl.textContent = "Reconnecting…";
    } else if (state === "error") {
        statusEl.textContent = `Error: ${message || "capture stopped"}`;
    } else {
        statusEl.textContent = "Stopped";
    }
}

function appendSegment(start, text) {
    if (!text) return;

    if (emptyEl) {
        emptyEl.remove();
        emptyEl = null;
    }

    const atBottom =
        transcriptEl.scrollHeight - transcriptEl.scrollTop - transcriptEl.clientHeight < 40;

    const row = document.createElement("p");
    row.className = "segment";

    const time = document.createElement("span");
    time.className = "time";
    time.textContent = formatTime(start);

    const body = document.createElement("span");
    body.textContent = text;

    row.append(time, body);
    transcriptEl.append(row);

    if (atBottom) {
        transcriptEl.scrollTop = transcriptEl.scrollHeight;
    }

    if (statusEl.textContent === "Idle" || statusEl.textContent === "Stopped") {
        statusEl.textContent = "Recording";
    }
}

function formatTime(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    const hours = String(Math.floor(total / 3600)).padStart(2, "0");
    const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
    const secs = String(total % 60).padStart(2, "0");
    return `${hours}:${minutes}:${secs}`;
}