# CLAUDE.md

Read `AGENTS.md` before any task. It owns scope, architecture, and build order.

Goal: live-transcribe a lecture tab and append text to a local Markdown file. Audio is temporary input, never a saved artifact.

## Delivery mode: code bodies only

Default: do not create, edit, move, or delete files. Show the code for the user to paste.

Only edit files when the user explicitly says "apply", "edit the file", "write it", or names the file and asks for the change. A question is not permission to edit.

Exception: `🔵 nit` findings from a review may be applied directly. Summarize the files changed. `🔴 bug` and `🟡 risk` fixes still require explicit permission.

When giving code:

- Put the target path on the line above the block.
- New file: full contents, no ellipses.
- Existing file: unified diff with `a/<path>` and `b/<path>` labels, exact current text, and 3 lines of context. Do not paste the whole file unless the user asks.
- Multiple files: one diff block per file, or one combined patch.
- Commands: one runnable block.
- After the code: at most 5 short bullets on what it does, then one verification step.

## Teaching mode

The user is learning Chrome extension development. Explain one concept at a time:

1. What the browser does.
2. Which API does it.
3. What the code does.
4. How to verify it.

Do not dump the whole extension in one reply. Build one step from `AGENTS.md` per turn.

## Style

- Load and follow `i-have-adhd` for every reply and code comment: action first, numbered steps, no preamble or recap, concrete time estimates.
- Load and follow `ponytail` before writing code: smallest complete change; no dependency, framework, or abstraction unless it removes more code than it adds. End with what was skipped and the remaining risk.
- Comments: one line, explain why. No banners, no restating the code.

## Git gate

Before any `git push`:

1. Run `caveman-review` on the diff.
2. Report findings as `file:Lline: problem. fix.` Ordered: bugs, risks, nits.
3. Apply nit fixes directly. Report bug and risk fixes as diffs for approval.
4. Use `caveman-commit` for the commit message.

Do not push without showing the review result.

## Hard rules

- Manifest V3, plain JavaScript, no build step.
- Permissions start at `activeTab`. Add `tabCapture`, `offscreen`, and `sidePanel` only in the step that uses them.
- No remote code, no secrets or API keys.
- Network is limited to `ws://127.0.0.1:8765` for the local Whisper server.
- Keep tab audio audible while transcribing.
- Audio is transient. Do not write it to disk unless `ECHOSCRIBE_SAVE_AUDIO=1` is explicitly set for debugging.
- One transcription session at a time. Always close the socket, stop tracks, and close the offscreen document.
- The server writes and flushes the transcript file after each segment.
- No DRM bypass. Personal study only.
