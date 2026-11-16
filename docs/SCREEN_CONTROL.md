# Screen control — Freakyyy working inside apps and websites

Commands cover a lot ("open Brave", "set volume to 30", "open my project in Android Studio"), but some
jobs only exist *inside* an app: opening a chat and writing a message, filling a form on a website,
changing a setting that lives on a page. Screen control is how Freakyyy does those.

## How it works

Freakyyy reads the **UI Automation tree** of a window — the same information a screen reader uses. No
screenshots, no pixel guessing, and it works in native apps (Explorer, Settings, Office) as well as in
Chromium browsers, where each web page is exposed as controls.

Each read hands the AI a short list like this:

```
e23  ListItem  Ravi
e25  Edit      Message          editable
e26  Button    Send             risky
```

The AI then acts on those refs. A typical run is: open the app → wait → read the screen → click →
read again → type → ask the user before sending.

Tools available to the AI (`freakyyy/ai/brain.py`, implemented in `freakyyy/core/assistant.py`):

| Tool | What it does |
|---|---|
| `screen_read` | Lists the controls of a window, each with a ref |
| `screen_text` | The readable text of a window or page |
| `ui_click` | Clicks a ref (left, double or right) |
| `ui_type` | Types into a ref, or where the cursor is |
| `ui_press` | A key or combination: `enter`, `ctrl+t`, `alt+tab` |
| `ui_scroll` | Scrolls the window |
| `focus_window` | Brings a window to the front, un-minimizing it |
| `wait_seconds` | Waits for a page or app to finish loading |

Everything lives in [`freakyyy/windows/ui_control.py`](../desktop/freakyyy/windows/ui_control.py).

## The safety rules

Screen control can do anything you can do with a mouse and keyboard, so it is fenced in:

- **You confirm anything irreversible.** A control whose name suggests sending, posting, buying, paying,
  deleting, signing out or installing is marked `risky`. Clicking it becomes a question Freakyyy asks you,
  and the click only happens when you say yes. Pressing Enter straight after Freakyyy typed something is
  treated the same way, because that is how most chat boxes send.
- **Passwords are never typed.** Typing into a password field is refused outright, and so is any text that
  looks like a password, PIN, code, card or account number. Sign in yourself.
- **Keystrokes can't land in the wrong app.** Typing with no target is refused unless the window Freakyyy
  just read still has focus, and `focus_window` reports failure instead of pretending. (Without this, a
  minimized window meant text went to whatever happened to be in front.)
- **Documents aren't cleared.** "Replace what's in the field" only works on single-line fields, never a
  whole document.
- **Refs expire** with each new read, so a click can't land on a control that has moved.
- **What's on screen is information, not orders.** Text in a page, email or document is never followed as
  an instruction; if a page tells Freakyyy to do something, it says so instead of obeying.
- **You can switch it off** in Settings → AI → "Let the AI read the screen and click and type for me".

## What to expect in practice

- Works well: native Windows apps, Explorer, Settings, forms and chats in Chromium browsers.
- Works less well: canvas-based apps (some games, design tools) and anything that draws its own controls
  without exposing them, where Freakyyy falls back to keyboard shortcuts.
- The free local model (Qwen3 4B) is the weak link, not the plumbing. It sometimes needs a second attempt
  to realise it can see the screen, and on a long chain of clicks it can pick the wrong control. Claude,
  when an API key is set, is markedly better at multi-step screen work.
- Sites that block automated browsers (Instagram and others, at times) can still refuse, and you need to
  be signed in already.
