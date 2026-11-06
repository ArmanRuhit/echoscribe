# Contract: Extension Messages

Chrome runtime messages between the side panel, the service worker, and the offscreen
document. Only the fields this feature touches are listed.

## Panel → background: `LANGUAGE`

Sent whenever the select changes.

```js
{ target: "background", type: "LANGUAGE", language: "hi" }
```

**Rules**: the service worker writes the value to `chrome.storage.session` under the key
`language`. An unknown value is ignored and the stored value is left alone.

## Background → offscreen: `START`

```js
{
  target: "offscreen",
  type: "START",
  streamId: "...",
  title: "Lecture 12",
  url: "https://...",
  language: "hi"
}
```

**Rules**: the service worker reads `chrome.storage.session` at click time and defaults to
`"en"` when nothing is stored. The value is passed through unchanged.

## Offscreen → panel: `STATUS`

```js
{
  target: "panel",
  type: "STATUS",
  state: "recording" | "reconnecting" | "idle" | "error",
  title: "Lecture 12",
  language: "hi",
  model: "small",
  message: "..."
}
```

**Rules**:
- `language` and `model` are present once the server has sent `ready`, and stay fixed for
  the session.
- The panel renders `Recording · Hindi · small` and falls back to today's text when the
  fields are absent.
- `state: "error"` carries the server's `message` verbatim.

## Background badge

Unchanged: `REC` while active, `ERR` on failure, cleared on stop. A failed start (including
a refused language) follows the existing `ERROR` path and clears the session.
