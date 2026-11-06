const OFFSCREEN_URL = "offscreen.html";
const LANGUAGE_KEY = "language";
const LANGUAGES = ["en", "hi"];

// session storage survives the service worker being evicted between selection and click.
async function readLanguage() {
    try {
        const stored = await chrome.storage.session.get(LANGUAGE_KEY);
        return LANGUAGES.includes(stored[LANGUAGE_KEY]) ? stored[LANGUAGE_KEY] : "en";
    } catch {
        return "en";
    }
}

async function clearSession(badge = "") {
    await chrome.action.setBadgeText({ text: badge });
    try {
        await chrome.runtime.sendMessage({ target: "clock", type: "CLOCK_STOP" });
    } catch {
        // no reporter in the tab
    }
    if (await chrome.offscreen.hasDocument()) {
        await chrome.offscreen.closeDocument().catch(() => {});
    }

    if (badge === "ERR") {
        setTimeout(() => chrome.action.setBadgeText({ text: "" }), 3000);
    }
}

chrome.runtime.onMessage.addListener((message) => {
    if (message?.target !== "background") return;

    if (message.type === "STOPPED") {
        void clearSession();
    } else if (message.type === "ERROR") {
        console.error("EchoScribe capture error:", message.message);
        void clearSession("ERR");
    }
});

chrome.action.onClicked.addListener(async (tab) => {
    if (tab.id && chrome.sidePanel?.open) {
        void chrome.sidePanel.open({ tabId: tab.id }).catch(() => {});
    }

    try {
        if (await chrome.offscreen.hasDocument()) {
            await chrome.runtime.sendMessage({ target: "offscreen", type: "STOP" });
            return;
        }

        if (!tab.id) throw new Error("No active tab id");

        await chrome.offscreen.createDocument({
            url: OFFSCREEN_URL,
            reasons: [chrome.offscreen.Reason.USER_MEDIA],
            justification: "Capture tab audio for live transcription"
        });

        const streamId = await chrome.tabCapture.getMediaStreamId({
            targetTabId: tab.id
        });

        // A missing player is not fatal: the server falls back to session time.
        try {
            await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                files: ["video-clock.js"]
            });
        } catch (error) {
            console.warn(`executeScript: ${error.message}`);
        }

        await chrome.runtime.sendMessage({
            target: "offscreen",
            type: "START",
            streamId,
            title: tab.title || "Lecture",
            url: tab.url || "",
            language: await readLanguage()
        });

        await chrome.action.setBadgeBackgroundColor({ color: "#c62828" });
        await chrome.action.setBadgeText({ text: "REC" });
    } catch (error) {
        console.error("EchoScribe start failed:", error);
        await clearSession("ERR");
    }
});