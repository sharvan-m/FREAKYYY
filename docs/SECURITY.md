# Security and privacy

## Microphone and audio
- Wake-word detection (Vosk) and speech recognition (faster-whisper) run **on the laptop**. Audio is never written to disk or sent anywhere.
- The microphone is visibly marked whenever it's open: a title-bar chip (`MIC ON · WAKE ONLY` / `MIC LIVE`) and a red dot on the tray icon. "Stop listening", the tray toggle or Settings close the microphone completely.
- On the phone, Android's speech recognizer is used only while the mic button is active.
- To keep Freakyyy from waking itself, wake-word detection pauses while Freakyyy is speaking.

## Freakyyy Link
- **Local network only.** The server refuses peers outside private, loopback and link-local ranges (configurable, off by default). There is no cloud relay.
- **TLS with a pinned certificate.** Each laptop generates an ECDSA P-256 certificate. The phone learns its SHA-256 fingerprint from the QR code and rejects any other certificate.
- **Pairing:**
  - The pairing token is 32 random bytes, works once and expires after 5 minutes.
  - Both screens show a 6-digit code that the phone computes independently (HMAC of the token and device ID).
  - Both people/devices must confirm.
- **Sessions:**
  - Each phone has its own 32-byte secret: in Windows Credential Manager on the laptop, and encrypted with an Android Keystore AES-GCM key on the phone.
  - Every connection does a mutual HMAC challenge–response.
  - Unauthenticated sockets are closed after 10 seconds.
- **No remote shell.**
  - Only allow-listed actions are accepted.
  - `run_command` text is interpreted by the receiving device's own command parser, so the remote side can't do anything a spoken command couldn't.
  - URLs must be http/https. File names are stripped of paths, sizes are capped, and transfers are verified with SHA-256 before saving.
- **Clipboard:** the laptop reading the phone's clipboard (and vice versa) is **off by default**, and Android only allows it while Freakyyy is open. Sending clipboard text that looks like a password asks first.

## Confirmations
- Spoken confirmation is required for destructive or sensitive actions:
  - delete files or folders (to the Recycle Bin by default; "permanently delete" asks more strongly)
  - empty the Recycle Bin
  - shut down, restart, sleep or sign out
  - force-close an app
  - git commit and git push
  - running a Python project
  - clearing phone notifications
  - accessibility taps on pay/send/delete buttons
  - quitting Freakyyy
- Low-risk actions run immediately.
- Protected locations (your home folder root, Desktop, Documents, Downloads, Pictures, and anything outside your profile) can't be deleted by voice.

## Data
| Data | Where |
|---|---|
| Settings, history, routines | `%APPDATA%\Freakyyy` (laptop), app-private storage (phone) |
| Secrets (AI key, email app password, device keys) | Windows Credential Manager (laptop), Android Keystore (phone) |
| Email | Read-only IMAP; Freakyyy never sends, deletes or moves mail |
| AI requests (only if you add a key) | The request text plus whatever its tools return (email snippets, page text, files you asked about) is sent to Anthropic's API. Everything else stays local. |

Android's Accessibility and Notification access remain optional, user-enabled helpers, as in Freakyyy Mobile 1.0.
