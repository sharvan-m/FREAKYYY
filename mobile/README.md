<div align="center">

# Freakyyy Mobile: Android Companion Assistant

[![Platform](https://img.shields.io/badge/Platform-Android%208.0%2B%20(API%2026--37)-green)](https://developer.android.com)
[![Language](https://img.shields.io/badge/Language-Kotlin%202.2-blue)](https://kotlinlang.org)
[![UI](https://img.shields.io/badge/UI-Jetpack%20Compose-blueviolet)](https://developer.android.com/compose)
[![Voice](https://img.shields.io/badge/TTS-Kokoro--82M%20ONNX-orange)](https://huggingface.co/hexgrad/Kokoro-82M)
[![Protocol](https://img.shields.io/badge/Protocol-Freakyyy%20Link%20v1%20%7C%20TLS-crimson)](../protocol/FREAKYYY_LINK_PROTOCOL.md)
[![Package](https://img.shields.io/badge/Package-com.freakyyy.assistant%20v2.0-lightgrey)](app/build.gradle.kts)

**The native Android companion app for Freakyyy. Delivers on-device voice assistance, liquid-glass Jetpack Compose design, accessibility automation, and seamless encrypted pairing with the Windows desktop assistant.**

[Overview](#-overview) • [Key Features](#-key-features) • [Architecture](#-architecture) • [Evolution & Migration](#-evolution--migration-from-troit--dexter) • [Permissions](#-permissions-guide) • [Setup & Pairing](#-setup--installation)

</div>

---

## 📱 Overview

**Freakyyy Mobile** is the mobile extension of the Freakyyy personal assistant ecosystem. Designed for modern Android hardware (tested on **Vivo X200 FE** and Android Emulators), it serves both as an independent smartphone voice controller and an encrypted bridge to your Windows laptop.

When away from your desk, Freakyyy Mobile manages phone settings, opens apps, tracks notifications, and executes automation routines. When connected to the laptop over **Freakyyy Link v1**, it unlocks bidirectional clipboard synchronization, one-tap file sharing, and relays complex language queries directly to the laptop's offline AI brain.

---

## ✨ Key Features

- **🗣️ Natural Neural Voice:** Incorporates **[Kokoro-82M ONNX](https://huggingface.co/hexgrad/Kokoro-82M)** (`am_onyx` voice at 1.08× speed) sharing the exact acoustic profile as the desktop assistant.
- **🎨 Liquid-Glass Compose UI:** Dark-themed, glassmorphic Jetpack Compose interface with live voice waveforms, animated status pills, and intuitive routine configuration screens.
- **🤖 Deep Phone Automation:** Optional **AccessibilityService** helper enables hands-free system navigation (**Back**, **Home**, **Recents**, **Scroll**, **Screen Lock**, and tapping named UI controls in external apps).
- **🔔 Notification Intelligence:** Non-intrusive notification counter and status manager that audits alert volume without reading private message contents.
- **🔗 Encrypted Freakyyy Link:** Connects to the desktop via TLS on port **47800** with mutual HMAC authentication. Features instant **QR-code pairing** with visual 6-digit verification codes.
- **💻 Desktop AI Relay:** When a query exceeds on-device rules, the phone automatically consults the laptop's local **Qwen3 4B / Claude** model with shared long-term memory.
- **📋 Cross-Device Utilities:**
  - **Shared Clipboard:** Pull and push clipboard text seamlessly between phone and laptop.
  - **Send to Laptop:** Native Android Share sheet integration to beam files and links with SHA-256 verification.
  - **Find My Laptop:** Auditory ping trigger over local LAN.

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────┐
│                   Freakyyy Mobile App                  │
│                                                        │
│  [Speech Recognizer] ──► [Intent & Command Parser]     │
│                                 │                      │
│            ┌────────────────────┴────────────────────┐ │
│            ▼                                         ▼ │
│  [Local Action Executor]               [Freakyyy Link] │
│  • App Launching & Settings            • TLS WebSocket │
│  • Accessibility Helper (Tap/Scroll)   • QR Pair / HMAC│
│  • Notification Counter                • Remote AI Call│
│            │                                         │ │
│            └────────────────────┬────────────────────┘ │
│                                 ▼                      │
│               [Kokoro-82M Neural Audio Player]         │
└─────────────────────────────────┬──────────────────────┘
                                  │ TLS :47800
                                  ▼
                [Freakyyy Desktop (Windows 11)]
```

---

## 🔄 Evolution & Migration (From TROIT & Dexter)

This mobile app began as an experimental Android voice assistant named **TROIT** (`com.troit.assistant`), was subsequently refined under the code name **Dexter**, and has now been fully unified into **Freakyyy** (`com.freakyyy.assistant`, version 2.0).

> ⚠️ **Important Installation Note:**  
> Because the application namespace and package ID transitioned to `com.freakyyy.assistant`, Android treats this as a separate application rather than an in-place upgrade. **Uninstall any previous TROIT or Dexter APK** before installing Freakyyy Mobile to ensure clean permission registration and prevent pairing conflicts.

---

## 🔒 Permissions Guide

Freakyyy Mobile follows a strict privacy-first model: sensitive permissions are completely optional and activated only if you choose to enable the corresponding feature.

| Permission | Category | Purpose |
| :--- | :--- | :--- |
| `RECORD_AUDIO` | Voice Commands | Captures user speech when the microphone button is pressed. Audio is processed on-device and never saved. |
| `WRITE_SETTINGS` | System Control | Allows voice-controlled adjustment of screen brightness. |
| `ACCESS_NOTIFICATION_POLICY` | System Control | Toggles Do Not Disturb (DND) and silent modes. |
| `BLUETOOTH_CONNECT` | Hardware | Enables or disables Bluetooth by voice. |
| `Notification Listener` | Optional Service | Displays unread notification counts; never inspects private message text. |
| `Accessibility Helper` | Optional Service | Executes simulated taps, scrolling, back, home, and recents navigation during automation routines. |

---

## ⚡ Setup & Installation

### Prerequisites
- Android device running **Android 8.0 (Oreo / API 26)** or higher (ARM64 recommended).
- Java Development Kit (JDK 17 or JDK 21).
- Android SDK Platform 37.

### 1. Build the APK
Open a terminal in the repository root:
```bash
cd mobile
./gradlew assembleDebug
```
The compiled APK will be located at:
`mobile/app/build/outputs/apk/debug/app-debug.apk`

### 2. Install to Device
Connect your Android phone via USB with **USB Debugging** enabled:
```bash
# Clean uninstall of legacy builds (if present)
adb uninstall com.troit.assistant

# Install clean Freakyyy Mobile build
adb install -r mobile/app/build/outputs/apk/debug/app-debug.apk
```
*Alternatively, transfer the APK file directly to your phone via Quick Share, Google Drive, or USB file transfer and install it using your phone's file manager.*

### 3. Pairing with Desktop
1. Launch **Freakyyy** on your Windows laptop. In the Notch Menu, select **Add Device** to reveal the pairing QR code.
2. Launch **Freakyyy** on your phone and tap **Devices → Scan Pairing Code**.
3. Point your camera at the QR code and verify that the **6-digit security code** matches on both screens.
4. Confirm the pairing. The status indicator on your desktop notch will immediately turn **Green**.
5. *(Optional)* Navigate to **Freakyyy → Permissions** to enable the **Accessibility Helper** and **Notification Counter**.

---

## 🛠️ Tech Stack & Dependencies

- **Language:** [Kotlin 2.2](https://kotlinlang.org)
- **UI Toolkit:** [Jetpack Compose](https://developer.android.com/compose) + Material 3
- **Build System:** Android Gradle Plugin 9.5 (AGP)
- **Networking:** [OkHttp 4.12](https://square.github.io/okhttp/) (WebSocket / TLS engine)
- **Vision & Scanning:** [ZXing 4.3](https://github.com/zxing/zxing) (QR code scanner) & [MediaPipe](https://developers.google.com/mediapipe)
- **Voice Engine:** Kokoro-82M ONNX Runtime Mobile integration

---

## 📄 License

This project is licensed under the MIT License — see the main [LICENSE](../LICENSE) file for details.

*Part of the Freakyyy ecosystem by [Sharvan M](https://github.com/sharvan-m).*
