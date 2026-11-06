// Injected into the captured tab: reports the player position so the server can
// map audio offsets onto video time. Runs in the extension's isolated world.
(() => {
    const KEY = "__echoScribeClock";
    if (window[KEY]) return;

    const INTERVAL_MS = 500;
    const previous = { position: -1, paused: null, rate: null };
    let timer = null;

    function pickPlayer() {
        const players = [...document.querySelectorAll("video, audio")];
        return (
            players.find((el) => !el.paused && !el.ended && el.readyState > 0) ||
            players.find((el) => el.tagName === "VIDEO") ||
            players[0] ||
            null
        );
    }

    function reading() {
        const player = pickPlayer();
        if (!player || player.readyState === 0) return null;

        let position = player.currentTime;
        if (!Number.isFinite(position) || position < 0) return null;
        if (Number.isFinite(player.duration)) {
            position = Math.min(position, player.duration);
        }

        const rate =
            player.playbackRate >= 0.25 && player.playbackRate <= 4 ? player.playbackRate : 1;
        const paused = Boolean(player.paused || player.ended);

        // Unchanged readings carry nothing new; the server extrapolates between them.
        if (
            position === previous.position &&
            paused === previous.paused &&
            rate === previous.rate
        ) {
            return null;
        }

        previous.position = position;
        previous.paused = paused;
        previous.rate = rate;
        return { position, paused, rate };
    }

    function stop() {
        if (timer) clearInterval(timer);
        timer = null;
        delete window[KEY];
    }

    function tick() {
        const sample = reading();
        if (!sample) return;
        try {
            void chrome.runtime
                .sendMessage({ target: "offscreen", type: "VIDEO_CLOCK", ...sample })
                .catch(() => {});
        } catch {
            // Extension reloaded under us; nothing can receive readings any more.
            stop();
        }
    }

    chrome.runtime.onMessage.addListener((message) => {
        if (message?.target === "clock" && message.type === "CLOCK_STOP") stop();
    });

    window[KEY] = true;
    timer = setInterval(tick, INTERVAL_MS);
    tick();
})();
