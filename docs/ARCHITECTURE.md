# Architecture

```
                 ┌──────────────────────── Freakyyy Desktop (Windows) ────────────────────────┐
 mic ─► Vosk wake word ─► energy VAD ─► faster-whisper ─┐                                     │
                                (all local)             ▼                                     │
 typed / tray / phone ─────────────────────────► Assistant pipeline ──► Kokoro ONNX am_onyx ─► DSP ─► speakers
                                                   │  parse → intent + device                │
                                                   │  confirm / clarify / context            │
                         ┌─────────────────────────┼─────────────────────┐                   │
                         ▼                         ▼                     ▼                   │
               Windows automation          AI brain (optional)     Freakyyy Link server ◄──────┼── TLS WebSocket
     apps · windows · files · settings ·   Claude + tools: email,  pairing · auth · requests │   (LAN only)
     volume · brightness · power · dev ·   web, files, browser,    file transfer · status    │
     git · gradle · npm · browser          freakyyy_command                                     │
                 └──────────────────────────────────────────────────────────────────────────┘
                                                                                ▲
                 ┌──────────────────────── Freakyyy Mobile (Android) ────────────┼────────────┐
 mic ─► SpeechRecognizer ─┐                                                     │            │
 typed / share sheet ─────┴► FreakyyyAssistant ─► FreakyyyIntentParser ─► action ──┤            │
                                │   on-phone actions → FreakyyyActionExecutor     │            │
                                │   laptop actions   → FreakyyyLink client ───────┘            │
                                └─► Kokoro (MediaPipe .litertlm) am_onyx ─► same DSP ─► speaker
                 └───────────────────────────────────────────────────────────────────────────┘
```

## Shared design

- **One command model on both devices.** Text is parsed into a typed action/intent (deterministic, offline). Each result has an honest outcome: `COMPLETED`, `OPENED`, `INFO`, `NEEDS_PERMISSION`, `NEEDS_CONFIRMATION`, `CLARIFY`, `NOT_SUPPORTED`, `FAILED` or `DEVICE_OFFLINE`.
- **Device selection** comes from the words used:
  - "on my phone", "my phone's …" → phone
  - "on my laptop" → laptop
  - "on both devices" → both
  - Corrections like "use my phone instead" re-run the last command on the other device.
- **Remote commands never become a shell.** `run_command` text goes through the *target's own parser*, so the remote side can only do what a spoken command could. The target device always applies its own confirmations, and the question goes back to whoever asked.
- **Same voice everywhere:**
  - Kokoro-82M with am_onyx at 1.08×.
  - Desktop uses the ONNX q8 export (`model_quantized.onnx` + `am_onyx.bin`), with the LiteRT-LM bundle as a fallback.
  - Phone uses MediaPipe with the LiteRT-LM bundle.
  - Both apply the identical DSP chain: HP 80 Hz, −2 dB @ 180 Hz, +2 dB @ 3 kHz, the acompressor port, −16 LUFS / −1.5 dBTP.

## Desktop modules (`desktop/freakyyy`)

| Module | Responsibility |
|---|---|
| `voice/listener.py` | Wake word (Vosk tiny grammar + decoys), two-stage check (Whisper must hear "Freakyyy"), VAD endpointing, push-to-talk, follow-up window, mic selection, error recovery |
| `voice/tts.py` | Kokoro engine (loaded once), sentence streaming, playback, cancellation, phrase cache, level meter for the orb |
| `voice/audio_dsp.py` | numpy port of the Freakyyy sound profile |
| `core/parser.py` | Normalization (wake words, fillers, Tanglish "open pannu"), device selection, chaining ("open X and load Y"), ~140 phrasings |
| `core/assistant.py` | Pipeline, context (last app, project, files, candidates), confirmations, clarifications, routines, history, phone requests, AI tool bridge |
| `windows/apps.py` | Start Menu + Store app index (240 apps here), aliases, launch, window list, focus, min/max/close |
| `windows/system.py` | Volume (Core Audio), brightness (WMI/DDC), power, battery, CPU/RAM, disks, screenshots, dark mode, 80+ `ms-settings:` pages, media keys, clipboard |
| `windows/files.py` | Known folders, Windows Search index queries (falls back to a bounded scan), Explorer selection ("this file"), Recycle Bin deletes |
| `windows/dev.py` | Project discovery, VS Code / Android Studio / Visual Studio, terminals, git status/commit/push/pull, Gradle (JBR fallback), npm, dev servers, Python entry points |
| `windows/browser.py` | Searches, site shortcuts, numbered results, reading the address bar with UI Automation, page text, PDF download, keyboard actions in your browser |
| `ai/brain.py` | Claude (`claude-opus-5-5`) tool loop: freakyyy_command, email, web search/fetch, files, browser page, device status |
| `ai/email_client.py` | Read-only IMAP (Gmail `is:important` when available) |
| `link/` | TLS identity, pairing, HMAC session auth, request routing, file transfer |
| `ui/` | Splash/boot sequence, HUD main window, orb, tray, pairing dialog, settings |

## Mobile additions (`mobile/app/src/main/java/com/troit/assistant`)

| File | Responsibility |
|---|---|
| `link/FreakyyyLink.kt` | OkHttp WebSocket client, certificate pinning, pairing (verifies the 6-digit code itself), mutual HMAC auth, reconnection, requests, file send/receive (MediaStore) |
| `link/FreakyyyLinkService.kt` | `connectedDevice` foreground service that keeps the link alive in the background, with a visible notification and a Disconnect action |
| `link/LinkStore.kt` | Pairing record; the device secret is encrypted with an Android Keystore AES-GCM key |
| `link/LaunchGate.kt` | Respects Android's background-activity-launch rules: opens directly when allowed, otherwise posts a tap-to-open notification and says so |
| `link/ShareToLaptopActivity.kt` | Share sheet → "Send to laptop" (files → Downloads\Freakyyy, links → laptop browser, text → laptop clipboard) |
| `DevicesScreen.kt` | Pairing (QR scan, pasted link, `freakyyylink://` deep link), code confirmation, laptop controls, clipboard toggles |
| `FreakyyyAssistant.kt` | Laptop actions, the handler for laptop requests, cross-device confirmations, find-my-phone ringing |
| `FreakyyyIntentParser.kt` | Laptop-directed commands, "on both devices" routines |
