# Freakyyy Ecosystem

One voice-first assistant across your **Windows laptop** and **Android phone**.

Say **“Hey Freaky”** to the laptop and control apps, files, settings, your dev projects, the browser, your email and your phone, without typing.

| Folder | What it is |
|---|---|
| [`desktop/`](desktop) | **Freakyyy Desktop**: Python + PySide6 Windows app. It provides the wake word, offline speech recognition, the Kokoro am_onyx voice, Windows automation, the AI brain and the Freakyyy Link server. |
| [`mobile/`](mobile) | **Freakyyy Mobile**: Kotlin + Jetpack Compose Android app. It's the overnight Freakyyy app plus a Freakyyy Link client, laptop control, a share-to-laptop target and a Devices screen. |
| [`protocol/`](protocol) | **Freakyyy Link** v1: the typed, authenticated JSON protocol between the two apps. |
| [`docs/`](docs) | Architecture, setup, pairing, security and the completion report. |

## Quick start

1. **Laptop:** run `desktop\dist\Freakyyy\install.ps1` (or start `Freakyyy.exe` directly), then say “Hey Freaky”.
2. **Phone:** install `mobile\app\build\outputs\apk\debug\app-debug.apk`.
3. **Pair them:** on the laptop, choose Add device. On the phone, open Devices → Scan pairing code. Check that both screens show the same 6-digit code, then confirm on both.

Full steps are in [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md) and [docs/DEVICE_PAIRING_GUIDE.md](docs/DEVICE_PAIRING_GUIDE.md).

For the AI working inside apps and websites - reading a window, clicking and typing, and the limits that keep it safe - see [docs/SCREEN_CONTROL.md](docs/SCREEN_CONTROL.md).

## Things you can say

| To the laptop | To the phone |
|---|---|
| “Hey Freaky, open Android Studio and load my Freakyyy project” | “Open WhatsApp” |
| “Check git status” · “Commit these changes” · “Build my project” | “Turn on flashlight” |
| “Search my documents for resume” · “Delete this file” | “Open WhatsApp notification settings” |
| “Set volume to 40 percent” · “Take a screenshot” · “Lock my laptop” | “Check my laptop battery” |
| “Open Chrome and search for Python tutorials” · “Click the first result” | “Open VS Code on my laptop” |
| “Any important emails?” · “What happened to my internship application?” | “Send clipboard to laptop” · Share → *Send to laptop* |
| “Turn on my phone flashlight” · “Send this file to my phone” | “Find my laptop” |
| “Start study mode on both devices” | “Start study mode on both devices” |
