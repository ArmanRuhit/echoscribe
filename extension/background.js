const OFFSCREEN_URL = "offscreen.html";

async function clearSession(badge = "") {
    await chrome.action.setBadgeText({ text: badge });
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

        await chrome.runtime.sendMessage({
            target: "offscreen",
            type: "START",
            streamId,
            title: tab.title || "Lecture",
            url: tab.url || ""
        });

        await chrome.action.setBadgeBackgroundColor({ color: "#c62828" });
        await chrome.action.setBadgeText({ text: "REC" });
    } catch (error) {
        console.error("EchoScribe start failed:", error);
        await clearSession("ERR");
    }
});