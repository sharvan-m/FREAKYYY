# Freakyyy: Overnight Completion Report

**Date:** 2026-11-16
**Project:** `C:\Users\samsa\AndroidStudioProjects\Dexter_Overnight`. The original `Troit` folder was not modified. Its only pending change, a MediaPipe line in `build.gradle.kts`, was there before this session, and none of its files are newer than this session's first build.

## Summary

| | Result |
|---|---|
| App completed | **Yes.** Every phase is implemented, it compiles, and it was run on the emulator |
| Kokoro AM Onyx integrated | **Yes, and verified on the emulator.** The model loaded and speech was synthesized and played (log evidence below) |
| APK built | **Yes.** `BUILD SUCCESSFUL` (see `build_log_1.txt` … `build_log_4.txt`) |
| APK | `app\build\outputs\apk\debug\app-debug.apk`, **379,548,649 bytes (362 MiB)**. `unzip -t` reports no errors |
| Tested on | Android Emulator `Medium_Phone_API_37.0` (x86_64, API 37). **Not tested on the Vivo phone.** |

---

## 1. Completed phases

| Phase | Status |
|---|---|
| Working-directory verification and project safety | Done. Backups are in `_backup_original/` (original sources) and `_backup_original/pre_freakyyy_edit/` |
| Project inspection | Done |
| Model inspection and runtime verification | Done. API signatures were checked with `javap` against the real AAR |
| Rename to Freakyyy | Done. Launcher label, UI, spoken identity, wake words ("hey Freakyyy"; "Troit" still works) |
| Kokoro voice engine and sound profile | Done |
| Voice used for every response | Done. Android's built-in TTS is no longer used anywhere |
| Command engine (intent → structured action → executor) | Done |
| App launching and app settings | Done |
| Android settings and device controls | Done |
| Notifications (optional listener) | Done |
| Accessibility helper (optional) | Done |
| Routines (persistent, editable) | Done |
| History and Permission Center | Done |
| Liquid-glass UI pass | Done (one consistent pass) |
| Build and APK | Done |
| Emulator smoke test | Done |

## 2. Kokoro integration

- **Model:** `kokoro_int8_fp16.litertlm` (294,783,298 bytes). This is a LiteRT-LM container holding the `tf_lite_acoustic` (int8) and `tf_lite_vocoder` models, 54 voices including `am_onyx`, and built-in English G2P and text normalization. No espeak is needed.
- **Runtime:** MediaPipe Tasks Audio **`com.google.mediapipe:tasks-audio:1.2.3`** (`TextToSpeech` task). This is Google's documented runtime for Kokoro `.litertlm` bundles. I did not use ONNX or any other runtime.
- **Not found on this PC:** `model_quantized.onnx`, `am_onyx.bin`, `freakyyy-morning-v5.wav`. They weren't needed.
- **Packaging:** the model is bundled in the APK at `assets/kokoro_int8_fp16.litertlm`, stored **uncompressed** (`noCompress "litertlm"`). On first launch it is copied once into app-private storage (`files/models/`) under its original file name, which MediaPipe uses to detect the model type. The copy goes to a temp file, is checked against the asset size, and then renamed into place. No ADB transfer is needed and no PC path is used at runtime.
- **Engine (`FreakyyyVoiceEngine.kt`):**
  - Loads the model once per process. A screen rotation does not reload it.
  - Uses the CPU delegate (XNNPACK). This bundle's vocoder declares a `cpu` backend constraint.
  - Keeps an XNNPACK weight cache in `cache/kokoro/` so later starts are faster.
  - Runs inference on a dedicated thread and playback on a second thread. While one chunk plays, the next is synthesized: streaming uses `openStream(...)` / `readNext()`, the same call the library's own `synthesizeStream` makes.
  - Plays through a single reused `AudioTrack` (float PCM, 24 kHz, `USAGE_ASSISTANT`) with transient audio focus (other audio ducks).
  - `speak()` replaces any current speech, so voices never overlap. `stop()` cancels the native stream right away. Identical replies repeated within 700 ms are dropped. Text longer than 1,500 characters is cut off.
  - Short phrases (60 characters or fewer) are cached as finished audio (4 MB LRU). Three common prompts are synthesized ahead of time. A real request interrupts this warm-up.
  - If loading fails, the UI shows **VOICE OFFLINE** with the reason and a Retry button. **It never silently falls back to Android TTS.**
- **Emulator evidence (logcat, `FreakyyyVoice` tag):**
  ```
  Kokoro ready in 10222 ms          (first launch, includes the 281 MiB install copy)
  Kokoro ready in 2153 ms           (later launches)
  Synthesised "Please say yes or no.": 2.38 s audio … peak -1.8 dBFS, RMS -17.4 dBFS
  Synthesised "Okay, I cancelled that action.": 2.59 s audio … peak -1.8 dBFS, RMS -17.5 dBFS
  ```
  The UI showed **SPEAKING** while replies played.

## 3. Voice configuration

| Setting | Value |
|---|---|
| Voice | `am_onyx` |
| Speed | `1.08` (`speakingRate`) |
| High-pass | 80 Hz, 2nd-order (Q 0.707, same as FFmpeg's `highpass` default) |
| EQ 1 | 180 Hz, Q 1, −2 dB (RBJ peaking, same as FFmpeg's `equalizer`) |
| EQ 2 | 3000 Hz, Q 1, +2 dB |
| Compressor | Port of FFmpeg's `acompressor`: threshold 0.08, ratio 2, attack 15 ms, release 120 ms, makeup 1.5, RMS detection, 2.828 soft knee |
| Loudness | Target −16 LUFS (BS.1770 K-weighting, gated blocks), ceiling −1.5 dBTP |

Everything runs in Kotlin inside the app (`FreakyyyAudioProcessor.kt`). It doesn't use FFmpeg or start any extra process.

**How the loudness step differs from FFmpeg's `loudnorm`:** `loudnorm` analyses the whole file. Freakyyy streams audio, so it measures each chunk *before* playing it (in effect, a look-ahead of one sentence) and remembers earlier levels, so gain stays steady from one reply to the next. True peak is enforced with a 5 ms look-ahead limiter set 0.3 dB below the ceiling to allow for inter-sample peaks. This gives −1.8 dBFS sample peaks, as measured above. LRA 7 is met by the compressor and no extra range compression is applied. I couldn't compare against `freakyyy-morning-v5.wav` because that file isn't on this PC.

## 4. Command engine

All of it is local and deterministic, with no network calls. Every command passes through the same stages:

`speech/text → FreakyyyIntentParser → FreakyyyAction (structured) → FreakyyyAssistant (confirmation, permission, routine handling) → FreakyyyActionExecutor (Android APIs) → FreakyyyResult → UI + Kokoro + history`

Each result has an honest outcome:

- `DONE`: the change was made and confirmed by reading the value back
- `OPENED`: a screen was opened and you still have to finish the change
- `INFO`
- `NEEDS_PERMISSION`
- `NEEDS_CONFIRMATION`
- `NOT_SUPPORTED`
- `FAILED`

Freakyyy never says something is "done" when it only opened a screen.

### Capabilities and outcomes verified on the emulator

| Command | Verified result |
|---|---|
| "what can you do" | INFO (spoken by Kokoro) |
| "set volume to 40 percent" | **DONE**: media volume changed and read back |
| "battery status" | INFO: "Battery is at 100 percent and charging…" |
| "how much storage is free" | INFO: "7.0 gigabytes free out of 10…" |
| "turn on flashlight" / "turn off flashlight" | **DONE** |
| "open bluetooth settings" | OPENED: Bluetooth settings |
| "open YouTube notification settings" | OPENED: YouTube's own notification page (`ACTION_APP_NOTIFICATION_SETTINGS`) |
| "open settings for YouTube" | OPENED: YouTube app info, with an explanation that in-app settings have no public link |
| "open chrome" | **DONE**: Chrome launched |
| "open camera" → "yes" | Confirmation (original Troit behaviour kept) → Camera launched |
| "set brightness to 40 percent" | NEEDS_PERMISSION: opened the "Modify system settings" page for Freakyyy |
| "turn on wifi" | DONE: "Wi-Fi is already on" (state read) |
| "enable dark theme" | OPENED: Android's Dark theme page |
| "start my study routine" | Ran all 3 steps. Volume DONE; DND and brightness reported as needing permission |
| "show installed apps" | Opened Freakyyy's App Hub |
| "go home" | NEEDS_PERMISSION: the optional accessibility helper is off |
| "how many notifications do I have" | NEEDS_PERMISSION: notification access is off |

The crash buffer showed **0 crashes** during testing.

### Full list of supported commands

- **Apps:**
  - Open any installed app (all existing Troit matching kept, including Tanglish and preferred apps from App Hub).
  - Fallbacks for apps you don't name: camera, phone, browser, maps, contacts, calendar, email, messages, music, gallery, calculator, alarms.
  - "open bluetooth" falls through to Bluetooth settings.
- **App settings:** app info, notifications, permissions and storage for any app. For example: "open WhatsApp settings", "turn off WhatsApp notifications", "open Chrome permissions", "open WhatsApp storage", "application information for WhatsApp".
- **Android settings pages (26):**
  - Connectivity: Wi-Fi, internet/mobile data, Bluetooth, hotspot, airplane mode, NFC, data usage
  - Device: display, sound, notifications, Do Not Disturb, battery, battery saver, storage, location
  - System: accessibility, language, date and time, apps, default apps, privacy, security, developer options, about phone, main Settings
  - Each page has fallbacks for phones that lack a specific screen.
- **Device controls:**
  - Brightness: set to a percentage, up, down, max or min.
  - Volume: media, ring, alarm, notification or call; set to a percentage, up, down, max, min, mute or unmute.
  - Flashlight on, off or toggle.
  - Ringer: normal, vibrate or silent.
  - Do Not Disturb on or off.
  - Bluetooth on: Android's own Allow dialog.
  - Wi-Fi on or off, dark theme, Bluetooth off: these open the correct screen.
- **Information:** battery, storage, time, date, greeting, help.
- **Notifications (optional):** count per app; clear all, with a confirmation that it can't be undone.
- **Accessibility (optional):** back, home, recent apps, notification shade, quick settings, screenshot, lock screen, scroll, "tap <button name>".
- **Freakyyy:** open App Hub, Routines, History, Permissions or Voice; "stop" or "stop all current automation"; run a routine.

## 5. Routines

- Each routine is an ordered list of normal Freakyyy commands, so any new command also works as a routine step. "wait N seconds" is supported between steps.
- Routines are saved in app-private storage (JSON in SharedPreferences).
- The Routines screen lets you run, create, edit and delete them. Every step is checked by the parser before saving.
- They come with **Study**, **Sleep** and **Work** routines that you can edit or delete.
- Progress shows in a card on the home screen with a Stop button. Saying "stop" cancels a routine.
- Sensitive steps always pause and ask you. Steps that only open a screen, or that need a permission, are listed at the end under "waiting on you".
- Routines run while Freakyyy is open or running in the background. Freakyyy doesn't add any scheduler, so it makes no promises about exact background timing.

## 6. Privacy and safety

- No root and no internet: the `INTERNET` permission that MediaPipe adds is **removed** in the manifest.
- History stores only the command text, the interpreted action and Freakyyy's reply, kept on the phone. A Clear button deletes it.
- The notification listener only counts notifications per package. It never reads titles or content.
- The accessibility service records no events, skips password fields, and asks before tapping anything that looks like pay, buy, send, delete, transfer, uninstall, sign out, and similar. It can be turned off from inside Freakyyy.
- Every special-access permission is something you grant on Android's own screen. Freakyyy explains why it needs each one in the Permission Center.

## 7. UI changes (one liquid-glass pass)

- Deep navy and near-black background with soft electric-blue and cyan light pools, drawn as radial gradients. These are cheap, work on every API level, and use no blur pass.
- Glass cards and chips: translucent fill with a thin light border.
- The orb is kept from Troit and now shows four states: idle (static, so no battery drain), listening (cyan pulse), processing (faster spin), speaking (waveform). The mic button has a listening ring.
- A conversation view with outcome labels (DONE / OPENED · YOUR TURN / NEEDS PERMISSION / …), Yes/No buttons for confirmations, a routine progress card, quick-action chips, typed input, and the mic.
- The dark window theme removes the white flash at launch, and system-bar icons are always light.
- App Hub is restyled. The preferred-app logic is unchanged, and there's a new searchable **Installed apps** list (tap to open, ⓘ for app info).
- New screens: Routines (and editor), History, Permissions, Voice (engine status, Test voice, Stop, Retry, full sound profile).

## 8. Dependencies and configuration changes

- `gradle/libs.versions.toml`: added `mediapipe-tasks-audio 1.2.3` (pinned; replaces the earlier uncommitted `latest.release` line) and `kotlinx-coroutines-android 1.9.0`.
- `app/build.gradle.kts`:
  - `ndk.abiFilters = arm64-v8a, x86_64`. This drops 32-bit libraries, saving about 32 MB.
  - `androidResources.noCompress += "litertlm"`.
  - SDK settings unchanged: min 26, compile/target 37, Java 11.
- Manifest:
  - Permissions: `WRITE_SETTINGS`, `ACCESS_NOTIFICATION_POLICY`, `ACCESS_WIFI_STATE`, `BLUETOOTH` (≤ API 30 only), `BLUETOOTH_CONNECT`.
  - Optional services: accessibility and notification listener.
  - Removed: `INTERNET` and `ACCESS_NETWORK_STATE`.
  - Hardware features marked optional.
- `.gitignore`: the 281 MiB model in assets is ignored because it's over GitHub's 100 MB limit.
- Build environment: your `JAVA_HOME` points to a JDK that no longer exists (`jdk-25.0.1.8-hotspot`). I built with Android Studio's bundled JBR and didn't change any system settings.

## 9. Files

**New:**

| File | Purpose |
|---|---|
| `FreakyyyVoiceEngine.kt` | Kokoro engine |
| `FreakyyyAudioProcessor.kt` | Sound-profile DSP |
| `FreakyyyCommand.kt` | Action and result model |
| `FreakyyyIntentParser.kt` | Intent parser |
| `SystemSettingsPage.kt` | Settings pages |
| `FreakyyyActionExecutor.kt` | Action executor |
| `FreakyyyDeviceController.kt` | Device controls |
| `FreakyyyAssistant.kt` | Orchestrator |
| `FreakyyyRoutines.kt` | Routines and history stores |
| `FreakyyyAccessibilityService.kt` | Optional accessibility helper |
| `FreakyyyNotificationListener.kt` | Optional notification counter |
| `FreakyyyScreens.kt` | App Hub, Routines, History, Permissions, Voice screens |
| `ui/FreakyyyGlass.kt` | Glass UI components |
| `res/xml/freakyyy_accessibility.xml` | Accessibility service config |
| `app/src/main/assets/kokoro_int8_fp16.litertlm` | The model |

**Modified:**

| File | Change |
|---|---|
| `MainActivity.kt` | Rewritten: navigation, home screen, input |
| `TroitSpeaker.kt` | Now a Kokoro adapter; same `speak`/`stop`/`shutdown` methods |
| `TroitSpeechRecognizer.kt` | Optional state callback added |
| `TroitAppManager.kt` | Cached app list, refreshed when apps are installed or removed |
| `TroitCommandHandler.kt` / `TroitAppMatcher.kt` | Freakyyy wake words |
| `Theme.kt`, `strings.xml`, `themes.xml`, `colors.xml` | Freakyyy branding and theme |
| `AndroidManifest.xml`, Gradle files | See section 8 |

`TroitActionExecutor.kt` and `TroitPreferenceManager.kt` are unchanged.

## 10. Real limitations

1. **Voice speed on your phone is untested.** On the emulator (emulated x86 CPU), Kokoro took 2 to 8 times longer than real time, so short replies started several seconds late. The Vivo X200 FE's ARM CPU should be much faster, but I couldn't measure it. If replies lag, the engine and sound profile stay as they are; the next step would be the GPU-vocoder variant of the model (`kokoro_int8_gpu_fp16.litertlm`) with `Delegate.GPU`.
2. **Install size:** a 362 MiB APK, plus a 281 MiB copy in app storage after first launch (about 650 MB in total). For Play Store distribution, the model should move to a Play Asset Delivery install-time pack. For sideloading, the current setup is simplest.
3. **First launch:** copying the model and warming up the engine takes a few seconds (10 s on the emulator). The pill shows VOICE LOADING and requests wait in a queue.
4. **Android restrictions, by design:**
   - Apps can't switch Wi-Fi, mobile data, hotspot, airplane mode, dark theme or Bluetooth-off. Freakyyy opens the right screen and says so.
   - Brightness needs "Modify system settings". DND and silent mode need DND access.
   - Some phones, Vivo included, use a non-linear brightness slider, so "40 percent" may not match the slider's position.
5. **Apps' own internal settings** (for example WhatsApp privacy) have no public deep links. Freakyyy opens Android's app info or notification page and explains this.
6. **Routines that open several screens:** Android may block a second screen from opening while Freakyyy is in the background, unless the accessibility helper is on (Android exempts enabled accessibility services).
7. **"Tap <button>"** works on whatever app is in the foreground. It's mainly useful in routines (open an app, wait, tap), because Freakyyy itself is in front while you talk to it.
8. **The loudness step** is a streaming approximation of `loudnorm` (see section 3). I couldn't compare it against the reference WAV.
9. `res/xml/data_extraction_rules.xml` still has the Android Studio template's TODO comment. It's not part of the main flow.

## 11. What to do tomorrow

See **`MORNING_START_HERE.md`**. In short: install the APK, open Freakyyy, wait for VOICE READY, grant the permissions you want in Permissions, and press **Test voice** to hear AM Onyx on the real phone.
