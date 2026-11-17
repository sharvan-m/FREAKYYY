<div align="center">

# Freakyyy 🤖
Personal Voice-First AI Assistant & Cross-Device Ecosystem

[![GitHub Repo](https://img.shields.io/badge/GitHub-sharvan--m%2FFREAKYYY-blue?logo=github)](https://github.com/sharvan-m/FREAKYYY)
[![Desktop](https://img.shields.io/badge/Desktop-Windows%2011%20%7C%20PySide6-blueviolet)](#-desktop-app-windows)
[![Mobile](https://img.shields.io/badge/Mobile-Android%20%7C%20Kotlin%202.2%20%7C%20Compose-green)](#-mobile-companion-android)
[![Voice](https://img.shields.io/badge/Speech-Kokoro--82M%20%7C%20Whisper%20%7C%20Vosk-orange)](#51-voice-engine--dsp-audio-profile)
[![AI Engine](https://img.shields.io/badge/Brain-Ollama%20%7C%20Qwen3%204B%20%7C%20Claude-blue)](#53-local-ai-brain--persistent-memory)
[![Link Protocol](https://img.shields.io/badge/Protocol-Freakyyy%20Link%20v1%20%7C%20TLS%20%2B%20HMAC-crimson)](#-freakyyy-link-laptop--phone)
[![License](https://img.shields.io/badge/License-MIT-lightgrey)](#-license)

**A private, offline-capable, voice-driven JARVIS-style assistant engineered for Windows 11 and Android. Seamlessly controls native applications, automates OS workflows, manages daily routines, and syncs over a zero-trust encrypted local link.**

[Overview](#-1-project-overview) • [Highlights](#-2-core-highlights) • [Tech Stack](#-3-technology-stack) • [Repository Layout](#-4-repository-layout) • [Architecture](#-5-architecture--subsystems) • [Quick Start](#-6-installation--setup) • [Security](#-7-privacy--security-model) • [Credits](#-8-references--credits)

</div>

---

## 📖 1. Project Overview

**Freakyyy** is an autonomous personal assistant built specifically for daily developer productivity and cross-device computing. Instead of relying on closed cloud assistants with recurring subscriptions and latency, Freakyyy runs **100% locally on consumer hardware**:

- 🎙️ **Voice-First Navigation:** Say **"Hey Freaky"** to command apps, manage active windows, control volume/brightness, search files, inspect browser profiles, trigger dev builds, and query emails.
- ⚡ **Zero-Wait Audio Streaming:** Uses sentence-level speculative streaming — the assistant begins speaking the first sentence through a studio-quality neural voice while subsequent sentences are being generated.
- 📱 **Seamless Cross-Device Synergy:** Connects Windows 11 and Android over **Freakyyy Link v1**, enabling bidirectional clipboard synchronization, mutual device automation, remote notification relays, and offloading mobile AI queries to the laptop.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        DESKTOP (Windows 11)                            │
│                                                                        │
│  "Hey Freaky" ──► [Vosk Stage 1] ──► [Whisper Stage 2 Verification]   │
│                                                  │                     │
│                                                  ▼                     │
│  [MacBook-Style Notch UI] ◄── [Kokoro-82M] ◄── [Qwen3 4B / Claude]     │
│  (State HUD / Waveform)       (Custom DSP)     (Sentence Streaming)    │
│                                                  │                     │
│  • Windows UI Automation (Screen Control)       ▼                     │
│  • System Tools (pycaw, psutil, pywin32)    [SQLite + FTS5 Memory]     │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                 Freakyyy Link v1 (TLS :47800 + HMAC)
                 Local Encrypted WebSocket / QR Pairing
                                   │
┌──────────────────────────────────▼─────────────────────────────────────┐
│                         MOBILE (Android)                               │
│                                                                        │
│  • Voice / Typed Commands ──► Liquid-Glass Jetpack Compose UI          │
│  • Accessibility Automation (Tap, Scroll, Back, Recents, Notifications)│
│  • Bi-Directional Clipboard Sync & SHA-256 File Transfers              │
│  • Remote AI Fallback (Delegates complex mobile queries to Laptop AI)  │
└────────────────────────────────────────────────────────────────────────┘
```

> **Design Philosophy:** Tailored specifically for personal developer workflows on an **ASUS Vivobook 15 (Intel Core 5 120U, 16 GB RAM)** — zero recurring costs, zero remote audio tracking, and instant execution.

---

## ✨ 2. Core Highlights

- **🗣️ Two-Stage Wake Word Detection:** Listens continuously offline for *"Hey Freaky"* using **[Vosk](https://alphacephei.com/vosk)**; silently verifies with **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** before activating to eliminate false triggers in noisy environments.
- **🎙️ Studio-Grade Neural Voice:** Powered by **[Kokoro-82M ONNX](https://huggingface.co/hexgrad/Kokoro-82M)** (`am_onyx` voice at 1.08× speed) routed through a custom DSP audio chain with dynamic EQ, high-pass filtering, compression, and **-16 LUFS** loudness normalization.
- **🧠 Free, Fully Local AI Brain:** Runs **[Qwen3 4B Instruct](https://github.com/QwenLM)** via **[Ollama](https://ollama.com)** completely offline with zero API fees. Optionally falls back to **[Anthropic Claude](https://www.anthropic.com)** when a credential key is saved.
- **🧠 Long-Term Memory Engine:** Automatically logs conversational facts and personal context into a local **SQLite + FTS5** database (`%APPDATA%\Freakyyy\memory.db`) with full search and manual inspection controls.
- **🖥️ MacBook-Style Notch UI:** Sleek, black hardware notch pinned to the top screen edge with curved shoulders and live status indicators. Automatically expands on cursor hover, typing, or voice activity.
- **🔍 Deep Screen & UI Automation:** Reads the live **Windows UI Automation (UIA)** tree to inspect, click, and navigate native applications and web browsers, complete with confirmation barriers for high-risk actions.
- **🔗 Encrypted Cross-Device Link:** Custom **Freakyyy Link v1** protocol over TLS (port 47800) with mutual HMAC challenge-response authentication, pinned certificates, and zero remote shell exposure.
- **⏰ Proactive Assistance:** Instant daily briefings, weather updates via **[wttr.in](https://wttr.in)**, persistent reminders, and multi-device low-battery notifications.

---

## 🛠️ 3. Technology Stack

| Layer | Technologies & Libraries | Purpose |
| :--- | :--- | :--- |
| **Desktop Application** | [Python 3.12](https://www.python.org) • [PySide6 (Qt 6)](https://wiki.qt.io/Qt_for_Python) • [PyInstaller](https://pyinstaller.org) | Windows desktop runtime, notch interface, background daemon |
| **Speech & Audio** | [Vosk](https://alphacephei.com/vosk) • [faster-whisper](https://github.com/SYSTRAN/faster-whisper) • [Kokoro-82M ONNX](https://huggingface.co/hexgrad/Kokoro-82M) • [NumPy](https://numpy.org) | Offline wake-word detection, ASR transcription, and neural TTS synthesis |
| **AI & Inference** | [Ollama](https://ollama.com) • [Qwen3 4B Instruct](https://github.com/QwenLM) • [Anthropic Claude API](https://docs.anthropic.com) | Local language model reasoning, speculative sentence streaming |
| **Context & Memory** | [SQLite](https://www.sqlite.org) with [FTS5 Full-Text Search](https://www.sqlite.org/fts5.html) | Local long-term associative memory and searchable conversation logs |
| **Windows OS Control** | [pycaw](https://github.com/AndreMiras/pycaw) • [screen-brightness-control](https://github.com/Crozzers/screen_brightness_control) • [psutil](https://github.com/giampaolo/psutil) • [pywin32](https://github.com/mhammond/pywin32) • [uiautomation](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows) • [mss](https://github.com/BoboTiG/python-mss) | Audio session control, display brightness, process tracking, screen clicks & window management |
| **Mobile Application** | [Kotlin 2.2](https://kotlinlang.org) • [Jetpack Compose](https://developer.android.com/compose) • [Android SDK (minSdk 26, targetSdk 37)](https://developer.android.com) | Native Android companion client, liquid-glass UI, AccessibilityService |
| **Mobile Networking** | [OkHttp 4.12](https://square.github.io/okhttp/) • [ZXing 4.3](https://github.com/zxing/zxing) • [MediaPipe](https://developers.google.com/mediapipe) | WebSocket communication, QR code pairing engine, on-device vision |
| **Cross-Device Link** | WebSockets over TLS • Pinned ECDSA Certificates • Mutual HMAC-SHA256 | Secure zero-trust local laptop ↔ phone communication protocol |

---

## 📂 4. Repository Layout

```text
FREAKYYY/
├── desktop/                             # Windows Desktop application (Python 3.12 + PySide6)
│   ├── app/                             # Core application runtime and main entry points
│   │   ├── notch/                       # MacBook-style notch UI, animation transitions & HUD
│   │   ├── voice/                       # Vosk wake word, Whisper STT, and Kokoro-82M TTS
│   │   ├── ai/                          # Ollama / Claude orchestrator, tool call definitions
│   │   ├── memory/                      # SQLite FTS5 database schema, fact extraction, recall
│   │   ├── automation/                  # Windows UI Automation, pycaw audio, process controls
│   │   └── server/                      # Freakyyy Link v1 WebSocket TLS server
│   ├── models/                          # Local model storage (Vosk en-us, whisper-base, Kokoro)
│   ├── build.ps1                        # PyInstaller build automation script
│   ├── install.ps1                      # Windows installer & shortcut setup script
│   └── requirements.lock.txt            # Pinned Python package dependencies
│
├── mobile/                              # Android Companion application (Kotlin + Compose)
│   ├── app/src/main/
│   │   ├── java/com/troit/assistant/
│   │   │   ├── ui/                      # Liquid-glass Jetpack Compose screens & components
│   │   │   ├── link/                    # Freakyyy Link WebSocket client & QR pairing
│   │   │   ├── automation/              # AccessibilityService tap/scroll/navigation helper
│   │   │   └── voice/                   # On-device Kokoro voice player & speech recognizer
│   │   └── AndroidManifest.xml          # Permissions, foreground service & accessibility declarations
│   └── build.gradle.kts                 # Android Gradle build configuration
│
├── protocol/                            # Cross-device networking specifications
│   ├── FREAKYYY_LINK_PROTOCOL.md        # Complete WebSocket, TLS, HMAC and payload spec
│   └── schema/                          # JSON schema definitions for allow-listed actions
│
├── brand/                               # Visual branding & media assets
│   ├── emblem.svg                       # Geometric 'F' logo icon
│   └── wordmark.png                     # Official FREAKYYY logotype
│
├── docs/                                # Technical documentation & setup guides
│   ├── ARCHITECTURE.md                  # Comprehensive system design specification
│   ├── SETUP_GUIDE.md                   # End-to-end environment and model download instructions
│   ├── SCREEN_CONTROL.md                # Windows UI Automation mechanics and safety barriers
│   └── SECURITY_MODEL.md                # Local credential isolation and encryption standards
│
└── README.md                            # Primary project documentation
```

---

## 🧠 5. Architecture & Subsystems

### 5.1 Voice Engine & DSP Audio Profile
The speech pipeline prioritizes **instant local responsiveness** and **natural conversational cadence**:

1. **Two-Stage Wake Word Gating:**
   - **Stage 1 (Vosk):** Continuously scans ambient audio for the exact acoustic phrase *"Hey Freaky"* (isolated words like *"freaky"* are rejected).
   - **Stage 2 (Whisper):** Confirms the wake phrase in the background before the notch UI expands, preventing unintended activations during background conversation.
2. **Push-To-Talk Alternative:** Instant voice trigger via global hotkey `Ctrl + Alt + D`.
3. **Speculative Sentence-by-Sentence TTS:** Answers stream from Qwen3 into Kokoro-82M sentence-by-sentence, cutting time-to-first-speech down to **under 800 ms**.
4. **Studio-Grade DSP Audio Chain:**
   ```text
   Raw PCM ──► High-Pass (80 Hz) ──► EQ (-2 dB @ 180 Hz) ──► EQ (+2 dB @ 3 kHz) ──► Dynamic Compressor ──► Loudness Normalization (-16 LUFS, -1.5 dBTP)
   ```

### 5.2 MacBook-Style Notch UI
Pinned seamlessly to the top edge of the primary display:
- **Collapsed State:** Displays the geometric **F** emblem and live status indicators (**Green** = Connected; **Red** = Link Inactive).
- **Expanded State:** Triggered by hovering the mouse, pressing the hotkey, or speaking. Opens with an animated drop displaying the live transcript, real-time waveform, tool activity, and confirmation buttons.
- **Auto-Dismiss:** Closes instantly when clicking outside or issuing a cancellation command.

### 5.3 Local AI Brain & Persistent Memory
- **Local Model Default:** [Qwen3 4B Instruct](https://github.com/QwenLM) quantized via [Ollama](https://ollama.com) (`q4_K_M`, ~2.5 GB RAM footprint). Fully functional with network cables unplugged.
- **Cloud Fallback:** Automatic failover to Anthropic Claude 3.5 Sonnet if an API key is present in **Windows Credential Manager**.
- **Long-Term Memory Database:** Conversational facts are indexed into a local SQLite database using **FTS5 (Full-Text Search with Porter stemming)**.
- **Privacy Gating:** Explicit filter blocks passwords, PINs, OTP tokens, and payment card numbers from ever persisting to disk.

### 5.4 Freakyyy Link (Laptop ↔ Phone)
Secure peer-to-peer link over local Wi-Fi / LAN via **WebSocket over TLS (Port 47800)**:
- **Pairing Ceremony:** Scans a one-time QR code containing a transient pairing token, confirmed via matching 6-digit visual check codes on both screens.
- **Cryptographic Pinning:** Mutual authentication using ECDSA certificates pinned by cryptographic SHA-256 fingerprint; sessions are secured via HMAC-SHA256 challenges.
- **Strict Allow-List:** Exclusively permits safe commands (`run_command`, `open_url`, `clipboard_push`, `clipboard_pull`, `ring`, `ask_ai`). **No arbitrary remote shell execution.**
- **File Transfer Engine:** Chunked binary streaming with SHA-256 checksum verification.

---

## ⚡ 6. Installation & Setup

### 1. Laptop Setup (Windows 11)
```powershell
# 1. Install and start Ollama, then pull the local model
ollama pull qwen3:4b-instruct-2507-q4_K_M

# 2. Build the Desktop application
Set-Location desktop
powershell -ExecutionPolicy Bypass -File build.ps1

# 3. Install shortcuts and launch the application
powershell -ExecutionPolicy Bypass -File install.ps1
```

### 2. Phone Setup (Android)
```bash
# 1. Compile the Android application using Gradle
cd mobile
./gradlew assembleDebug

# 2. Install the debug APK to your connected device
adb install app/build/outputs/apk/debug/app-debug.apk
```

### 3. Pairing
1. On your Windows desktop, click the **Notch Menu → Add Device** to display the pairing QR code.
2. In the mobile app, navigate to **Devices → Scan Pairing Code**.
3. Verify that the **6-digit security code** matches on both screens, then tap **Confirm Pairing**.

---

## 🔒 7. Privacy & Security Model

- **🛡️ 100% Offline Audio Processing:** Wake word scanning and ASR transcription execute entirely on-device; raw microphone audio is never written to disk or transmitted over the internet.
- **🛑 Human-in-the-Loop Confirmation Barrier:** Sensitive actions (permanent file deletion, credit card payments, sending emails, clearing database memory) require explicit verbal or UI confirmation.
- **🔑 Zero Plaintext Secrets:** API keys and IMAP email credentials are encrypted inside the **Windows Credential Manager (DPAPI)**, never in plain-text configuration files.
- **📖 Read-Only Email Access:** IMAP protocol integration is restricted strictly to fetching headers and viewing mail; sending emails or deleting messages via IMAP is prohibited.

---

## 💻 8. Hardware Profile & Performance

Benchmarked on **ASUS Vivobook 15 (X1504VA)**:
- **Processor:** Intel Core 5 120U (10 Cores, 12 Threads, up to 5.0 GHz)
- **Memory:** 16 GB DDR4 (8 GB onboard + 8 GB removable SO-DIMM)
- **Graphics:** Intel Integrated Graphics (CPU inference only)
- **Latency Benchmarks:**
  - Wake word detection: `< 120 ms`
  - Whisper confirmation: `< 250 ms`
  - Time-to-first-sentence TTS speech: `~800 ms - 2.1 s`
- **Future Expansion Path:** Swapping the 8 GB SO-DIMM for 32 GB (yielding 40 GB total) enables local execution of Mixture-of-Experts architectures like **Qwen3-30B-A3B**.

---

## 📋 9. Implementation Roadmap

- [x] Multi-stage offline wake word detection with Vosk and Whisper.
- [x] MacBook-style floating notch UI with smooth animation transitions.
- [x] Local LLM integration via Ollama with speculative sentence streaming.
- [x] SQLite FTS5 long-term memory engine with automated fact capture.
- [x] Windows UI Automation tree traversal for hands-free screen interaction.
- [x] Freakyyy Link v1 encrypted WebSocket pairing and bidirectional clipboard sync.
- [x] Native Android companion app with Jetpack Compose liquid-glass UI.
- [ ] Direct offline on-device SLM execution on Android when detached from laptop.
- [ ] Integration with Home Assistant for local Zigbee/Matter smart home control.
- [ ] Multi-monitor support for dynamic notch repositioning.

---

## 📚 10. References & Credits

- **Local Inference:** [Ollama](https://ollama.com) • [Qwen3 Language Models](https://github.com/QwenLM)
- **Speech & Neural TTS:** [Kokoro-82M ONNX](https://huggingface.co/hexgrad/Kokoro-82M) • [Vosk](https://alphacephei.com/vosk) • [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- **Desktop Framework:** [Qt for Python (PySide6)](https://wiki.qt.io/Qt_for_Python)
- **Mobile Development:** [Jetpack Compose](https://developer.android.com/compose) • [OkHttp](https://square.github.io/okhttp/)
- **Live Weather Feed:** [wttr.in](https://wttr.in)

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

*Crafted by [Sharvan M](https://github.com/sharvan-m).*
