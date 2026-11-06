# Contract: Extension Messages (GPU additions)

Inherits `../001-hindi-transcript/contracts/extension-messages.md`. Background → offscreen `START`
and panel → background `LANGUAGE` are unchanged: the extension does not choose a device.

## offscreen → panel `STATUS` — extended

```js
{target: "panel", type: "STATUS", state: "recording",
 language: "hi", model: "small", device: "cuda", compute: "float16"}
```

| Field | When present | Render |
|---|---|---|
| `device` | `recording` and `reconnecting`, after `ready` | `GPU` when `"cuda"`, omitted when `"cpu"` |
| `compute` | same | Shown only with `device` (`GPU float16`) |

Status line examples:

```text
Recording · Hindi · small · GPU float16
Recording · English · small
Reconnecting…
```

Rules:

- Fields are relayed verbatim from `ready`; the client never guesses a device.
- `idle` and `error` clear them, so a later session cannot display a stale device.
- A missing `device` (old server) renders no suffix — a CPU-looking line, matching the truth that
  nothing was reported.

## offscreen → background `ERROR`

Unchanged shape. Now emitted for `error` frames received **after** `ready` as well, because the
session is over:

```js
{target: "background", type: "ERROR", message: "CUDA out of memory ..."}
```

The background badge clears to `ERR` for 3 s; the panel keeps the message until the next start.

## Unchanged

`START` (`{streamId, title, url, language}`), `STOP`, `LANGUAGE`, `SEGMENT`, and the side panel's
language selector. There is no GPU toggle: switching devices means restarting the server.
