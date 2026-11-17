# Setup guide

## 1. Laptop: Freakyyy Desktop

**Install the packaged app** (no Python needed):

1. Unzip `desktop\dist\Freakyyy-Desktop.zip`, or use the `desktop\dist\Freakyyy` folder directly.
2. Right-click `install.ps1` → *Run with PowerShell*. Add `-StartWithWindows` if you want Freakyyy to start when you sign in.
3. Start **Freakyyy** from the Start menu.
4. Windows Security will ask, *"Do you want to allow public and private networks to access this app?"* Choose **Allow** if you want your phone to connect. Freakyyy Link turns away any device that isn't on a private, local network anyway, so allowing it doesn't expose Freakyyy to the internet. If you'd rather allow private networks only, open *Windows Security → Firewall → Allow an app*, find Freakyyy, and untick **Public**.

**Or run from source:**

```bash
cd C:\Users\samsa\AndroidStudioProjects\Freakyyy_Ecosystem\desktop
```

```bash
.venv\Scripts\python -m freakyyy
```

**First run**
- A boot screen shows each subsystem coming online: voice, speech recognition, wake word, Freakyyy Link and the app index.
- Freakyyy says "Good morning. Freakyyy is online."
- The title bar shows `"HEY FREAKYYY" · ON` and `MIC ON · WAKE ONLY`. The tray icon gets a red dot whenever the microphone is open.

**Using it**
- Say **"Hey Freaky"**, pause or keep talking, then give the command. Freakyyy answers out loud and goes back to waiting for the wake word.
- When Freakyyy asks you something ("Which project?", "Should I continue?"), just answer. No wake word is needed for about 8 seconds.
- Push-to-talk: **Ctrl+Alt+D** anywhere, or the Talk button.
- "Stop" interrupts speech and any routine. "Stop listening" turns the microphone off.
- Closing the window hides it to the tray; Freakyyy keeps listening. To quit, right-click the tray icon → *Quit*, or say "quit Freakyyy".

**The Dynamic Island**

A small pill sits at the top center of the screen. It's always on top but never takes keyboard focus while collapsed.

| You do | It does |
|---|---|
| Hover | Expands: "How can I help?", voice button, command field, device status, History, quick actions |
| Click | Opens the full panel: emblem and waveform, input with a **Send to** switch (Auto / Laptop / Phone / Both, which really changes where typed commands run), Conversation / Recent activity / History / Applications views, laptop and phone cards, all quick actions, Mute / Hide / Exit |
| Say "Hey Freaky" or "Wake up Freakyyy" | Expands into the live session view: transcript as you speak, waveform, target, action, status, and the real result |

- During a voice session it stays open while you speak and while Freakyyy works. Cancel and Stop are available there.
- Keyboard: **Enter** runs a typed command, **Esc** clears the field, then collapses the island.
- **Drag** the island to move it. It remembers its position per monitor. Settings → Listening → *Reset island position* puts it back.
- Spoken controls: "Stop Freakyyy" / "Cancel that" stop Freakyyy. "Go to sleep, Freakyyy" returns to standby with the wake word still on. "Hide the island" / "Show the island" do what they say. "Mute the microphone" turns the mic off.

**Optional settings** (⚙ in the title bar):

| Tab | What to set |
|---|---|
| **AI** | Paste an Anthropic API key. It's stored in Windows Credential Manager. This enables open-ended requests like email triage, "what happened to my internship application", page summaries and research. Device automation works without it. |
| **Email** | Your Gmail address and an *app password* (myaccount.google.com/apppasswords). Read-only. |
| **Listening** | Microphone, sensitivity (strict / normal / sensitive), timeouts |
| **Routines** | Study / Work / Sleep, or your own. One step per line: `laptop: open vscode`, `phone: turn on do not disturb`, `wait 3`. |
| **General** | Start with Windows, start in the background, the project folders Freakyyy searches |

## 2. Phone: Freakyyy Mobile

1. Install `mobile\app\build\outputs\apk\debug\app-debug.apk`:

   ```bash
   adb install -r mobile\app\build\outputs\apk\debug\app-debug.apk
   ```

   Or copy the APK to the phone and open it. It installs over last night's Freakyyy, keeping your App Hub choices and history.
2. Open Freakyyy → **Permissions**. Allow Microphone, Local network (Android 17+) and Notifications. Allow the others only if you want those features.
3. Optional: **Display over other apps** lets "open WhatsApp on my phone" (said to the laptop) open apps immediately while Freakyyy is in the background. Without it, Freakyyy sends a tap-to-open notification.

## 3. Connect them

See [DEVICE_PAIRING_GUIDE.md](DEVICE_PAIRING_GUIDE.md). Both devices must be on the **same Wi-Fi**. Freakyyy Link never uses the internet.
