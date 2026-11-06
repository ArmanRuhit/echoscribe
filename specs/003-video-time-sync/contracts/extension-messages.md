# Contract: Extension Messages (v3)

## Captured tab → offscreen

Sent by the injected `video-clock.js` with `chrome.runtime.sendMessage`. No reply is expected.

```js
{ target: "offscreen", type: "VIDEO_CLOCK", position: 754.2, paused: false, rate: 1.0 }
```

`video-clock.js` lives in the isolated world: it can read the DOM and call `chrome.runtime`, but it
cannot touch page globals. It is injected once per capture start, and it keeps its interval across
the service worker sleeping. It stops when the document is unloaded; reporting also stops if the
user navigates, which is the fallback case.

## Background → captured tab

Unchanged from v2: one `executeScript` call at capture start.

```js
await chrome.scripting.executeScript({ target: { tabId }, files: ["video-clock.js"] });
```

A throw is logged as `executeScript: <message>` and capture continues without a reporter. It never
blocks the session and never sets the `ERR` badge.

## Offscreen → server

Unchanged channel; new frame type. The audio stamp is `samplesSent / 16000` at the moment the
reading is handled, so page time and audio time share one coordinate system.

```js
{ type: "clock", video: 754.2, audio: 96.5, paused: false, rate: 1.0 }
```

Frames are only sent while the socket is open. They are deliberately excluded from the reconnect
queue: a stale anchor is worse than no anchor.

## Offscreen → side panel

`STATUS` gains one field.

```js
{ target: "panel", type: "STATUS", state: "recording", language: "hi", model: "large-v3",
  device: "cuda", compute: "float16", clock: "video" }
```

`clock` is `"pending"`, `"video"`, or `"session"`; it is cleared on `idle` and `error` like the other
session fields. The panel renders it as a trailing `· video` or `· session`, and shows nothing while
pending.

## Unchanged

`START` (background → offscreen), `STOP`, `ERROR`, `SEGMENT`, and `LANGUAGE` keep their v2 shapes.
`START` gains nothing: the reporter is injected by the service worker, not passed through the
offscreen document.
