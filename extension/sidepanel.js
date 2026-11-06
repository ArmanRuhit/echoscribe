const statusEl = document.querySelector("#status");
const transcriptEl = document.querySelector("#transcript");
const languageEl = document.querySelector("#language");
let emptyEl = transcriptEl.querySelector(".empty");

const LANGUAGES = { en: "English", hi: "Hindi" };
const LANGUAGE_KEY = "language";
let sessionLanguage = "";
let sessionModel = "";

void restoreLanguage();

async function restoreLanguage() {
    try {
        const { language } = await chrome.storage.session.get("language");
        if (languageEl && LANGUAGES[language]) languageEl.value = language;
    } catch {
        // storage unavailable: keep the English default
    }
}

languageEl?.addEventListener("change", () => {
    void saveLanguage(languageEl.value);
});

// Written straight from the panel: a message hop can drop before the worker wakes,
// and a lost write means every later start silently runs in English.
async function saveLanguage(language) {
    try {
        await chrome.storage.session.set({ [LANGUAGE_KEY]: language });
    } catch (error) {
        console.error("EchoScribe language save failed:", error.message);
        statusEl.textContent = "Language not saved; reload the extension";
    }
}

chrome.runtime.onMessage.addListener((message) => {
    if (message?.target !== "panel") return;

    if (message.type === "STATUS") {
        setStatus(message);
    } else if (message.type === "SEGMENT") {
        appendSegment(message.start, message.text);
    }
});

function setStatus({ state, title, message, language, model }) {
    if (language) sessionLanguage = language;
    if (model) sessionModel = model;

    if (state === "recording") {
        statusEl.textContent = recordingLabel(title);
    } else if (state === "reconnecting") {
        statusEl.textContent = "Reconnecting…";
    } else if (state === "error") {
        statusEl.textContent = `Error: ${message || "capture stopped"}`;
        sessionLanguage = "";
        sessionModel = "";
    } else {
        statusEl.textContent = "Stopped";
        sessionLanguage = "";
        sessionModel = "";
    }
}

function recordingLabel(title) {
    if (!sessionLanguage || !sessionModel) {
        return title ? `Recording: ${title}` : "Recording";
    }

    const chosen = languageEl?.value;
    if (chosen && chosen !== sessionLanguage) {
        return `Server is using ${LANGUAGES[sessionLanguage] || sessionLanguage}, not ${
            LANGUAGES[chosen] || chosen
        }`;
    }

    return `Recording · ${LANGUAGES[sessionLanguage] || sessionLanguage} · ${sessionModel}`;
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
    if (sessionLanguage) body.lang = sessionLanguage;
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