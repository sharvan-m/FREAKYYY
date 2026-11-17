# Good morning: start here

The Freakyyy APK is built and tested on the emulator. Full details are in `OVERNIGHT_COMPLETION_REPORT.md`.

## 1. Install on your Vivo X200 FE

**APK:** `C:\Users\samsa\AndroidStudioProjects\Dexter_Overnight\app\build\outputs\apk\debug\app-debug.apk` (362 MiB)

**Option A: USB.** Connect the phone with USB debugging on, then run:

```bash
"C:\Users\samsa\AppData\Local\Android\Sdk\platform-tools\adb.exe" install -r "C:\Users\samsa\AndroidStudioProjects\Dexter_Overnight\app\build\outputs\apk\debug\app-debug.apk"
```

It installs as an update to the old Troit app (same app ID, `com.troit.assistant`), so your App Hub preferences are kept. If Android refuses because the signature is different, uninstall Troit first.

**Option B: no cable.** Copy the APK to the phone (Drive, USB file transfer, Quick Share), tap it, and allow "Install unknown apps" for the app you opened it with.

Make sure you have about 700 MB free.

## 2. First launch

1. Open **Freakyyy**.
2. The top-right pill shows **VOICE LOADING** while the voice model installs itself (one time only, a few seconds). Then it shows **VOICE READY**.
3. Tap the pill (or **Voice** → **Test voice**). You should hear the AM Onyx voice at 1.08× with the Freakyyy sound profile.

If the pill shows **VOICE OFFLINE**, the Voice screen shows the reason and has a **Retry** button.

## 3. Permissions (Freakyyy → Permissions)

Turn on only what you want. Each card explains what it does.

| Permission | What it's for |
|---|---|
| Microphone | Voice commands. Asked when you first tap the mic |
| Modify system settings | Brightness |
| Do Not Disturb access | DND and silent mode |
| Nearby devices | Turning Bluetooth on |
| Notification access | **Optional.** Counts and clears notifications; never reads their content |
| Accessibility helper | **Optional.** Back, home, recent apps, lock screen, screenshots, scrolling, tapping buttons in routines |

**To turn on the accessibility helper:** Permissions → Accessibility helper → **Turn on**. In Android's Accessibility settings, choose **Freakyyy automation helper** and switch it on. On Vivo it may be under *Downloaded apps* or *Installed services*. To switch it off, use the same card in Freakyyy (**Turn off**) or Android's settings.

## 4. Try these

Tap the mic or type:

- "Open WhatsApp" / "Open Instagram" / "Open camera"
- "Open WhatsApp notification settings" / "Turn off WhatsApp notifications"
- "Set brightness to 40 percent" / "Increase volume" / "Set volume to 50 percent"
- "Turn on flashlight" / "Silent mode" / "Turn on do not disturb"
- "Open Bluetooth settings" / "Turn on Bluetooth" / "Open battery settings"
- "Battery status" / "How much storage is free"
- "Show installed apps" / "Start my study routine" / "Stop all current automation"
- "What can you do?"

Edit **Study**, **Sleep** and **Work**, or add your own, in **Routines**. Each step is a normal Freakyyy command, for example "open spotify", "wait 3 seconds", "set brightness to 30 percent".

## 5. Voice settings

The voice is fixed to your chosen setup:

- Voice: `am_onyx`
- Speed: 1.08
- Sound profile: high-pass 80 Hz, −2 dB at 180 Hz, +2 dB at 3 kHz, compressor, −16 LUFS / −1.5 dBTP

The Voice screen shows all of it. The settings live in `FreakyyyVoiceEngine.kt` (voice and speed) and `FreakyyyAudioProcessor.kt` (sound profile).

**Please check:** how quickly Freakyyy starts speaking on the phone. On the emulator it was slow because the emulated CPU is slow. If it lags on the phone, tell me and I'll try the GPU-vocoder model variant.

## 6. Open the project in Android Studio

Open the folder `C:\Users\samsa\AndroidStudioProjects\Dexter_Overnight`.

Note: your `JAVA_HOME` environment variable points to a JDK that no longer exists. Android Studio uses its own JDK, so this only matters if you build from a terminal. In that case, set it for the session first:

```bash
set JAVA_HOME=C:\Program Files\Android\Android Studio\jbr
```

```bash
gradlew.bat assembleDebug
```

Nothing has been committed to git. All changes are uncommitted in the working copy, so you can review them first.
