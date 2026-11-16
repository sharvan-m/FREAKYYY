"""Windows system controls. Every change is read back before Freakyyy reports it."""
from __future__ import annotations

import ctypes
import datetime as dt
import logging
import os
import subprocess
from pathlib import Path

import psutil

from ..core.actions import Outcome, Result, confirm, done, failed, info, opened

log = logging.getLogger(__name__)
user32 = ctypes.windll.user32
CREATE_NO_WINDOW = 0x08000000

SETTINGS_PAGES = {
    "main": "ms-settings:", "windows": "ms-settings:", "system": "ms-settings:system",
    "wifi": "ms-settings:network-wifi", "wireless": "ms-settings:network-wifi",
    "network": "ms-settings:network-status", "internet": "ms-settings:network-status",
    "ethernet": "ms-settings:network-ethernet", "vpn": "ms-settings:network-vpn",
    "airplane mode": "ms-settings:network-airplanemode", "flight mode": "ms-settings:network-airplanemode",
    "hotspot": "ms-settings:network-mobilehotspot", "mobile hotspot": "ms-settings:network-mobilehotspot",
    "proxy": "ms-settings:network-proxy",
    "bluetooth": "ms-settings:bluetooth", "devices": "ms-settings:bluetooth", "printers": "ms-settings:printers",
    "mouse": "ms-settings:mousetouchpad", "touchpad": "ms-settings:devices-touchpad",
    "display": "ms-settings:display", "screen": "ms-settings:display", "brightness": "ms-settings:display",
    "night light": "ms-settings:nightlight", "resolution": "ms-settings:display",
    "sound": "ms-settings:sound", "audio": "ms-settings:sound", "volume": "ms-settings:apps-volume",
    "microphone": "ms-settings:privacy-microphone", "camera": "ms-settings:privacy-webcam",
    "notifications": "ms-settings:notifications", "notification": "ms-settings:notifications",
    "focus": "ms-settings:quiethours", "focus assist": "ms-settings:quiethours", "do not disturb": "ms-settings:quiethours",
    "battery": "ms-settings:batterysaver", "battery saver": "ms-settings:batterysaver",
    "power": "ms-settings:powersleep", "sleep": "ms-settings:powersleep", "power and sleep": "ms-settings:powersleep",
    "storage": "ms-settings:storagesense", "disk": "ms-settings:storagesense",
    "apps": "ms-settings:appsfeatures", "installed apps": "ms-settings:appsfeatures",
    "default apps": "ms-settings:defaultapps", "startup": "ms-settings:startupapps", "startup apps": "ms-settings:startupapps",
    "personalization": "ms-settings:personalization", "background": "ms-settings:personalization-background",
    "wallpaper": "ms-settings:personalization-background", "colors": "ms-settings:colors",
    "theme": "ms-settings:themes", "themes": "ms-settings:themes", "dark mode": "ms-settings:colors",
    "lock screen": "ms-settings:lockscreen", "taskbar": "ms-settings:taskbar", "start": "ms-settings:personalization-start",
    "fonts": "ms-settings:fonts",
    "accounts": "ms-settings:yourinfo", "account": "ms-settings:yourinfo", "sign in": "ms-settings:signinoptions",
    "sign-in options": "ms-settings:signinoptions", "email accounts": "ms-settings:emailandaccounts",
    "time": "ms-settings:dateandtime", "date": "ms-settings:dateandtime", "date and time": "ms-settings:dateandtime",
    "language": "ms-settings:regionlanguage", "region": "ms-settings:regionformatting", "keyboard": "ms-settings:typing",
    "typing": "ms-settings:typing", "speech": "ms-settings:speech",
    "gaming": "ms-settings:gaming-gamebar", "game mode": "ms-settings:gaming-gamemode",
    "accessibility": "ms-settings:easeofaccess", "narrator": "ms-settings:easeofaccess-narrator",
    "privacy": "ms-settings:privacy", "security": "windowsdefender:", "windows security": "windowsdefender:",
    "update": "ms-settings:windowsupdate", "windows update": "ms-settings:windowsupdate", "updates": "ms-settings:windowsupdate",
    "about": "ms-settings:about", "about this pc": "ms-settings:about", "system info": "ms-settings:about",
    "recovery": "ms-settings:recovery", "activation": "ms-settings:activation", "clipboard": "ms-settings:clipboard",
    "multitasking": "ms-settings:multitasking", "projecting": "ms-settings:project", "remote desktop": "ms-settings:remotedesktop",
}


def open_settings(page: str) -> Result:
    key = page.lower().strip()
    key = key.replace("wi-fi", "wifi").replace("windows ", "") if key not in SETTINGS_PAGES else key
    uri = SETTINGS_PAGES.get(key)
    if uri is None:
        for k, v in SETTINGS_PAGES.items():
            if k in key or key in k:
                uri = v
                break
    if uri is None:
        return failed(f"I don't know a Windows settings page called {page}.")
    os.startfile(uri)
    title = "Settings" if uri == "ms-settings:" else f"{page} settings"
    return opened(f"Opening {title}.")


def radio(page: str, on: bool) -> Result:
    """Windows doesn't let apps switch radios without admin rights; open the right page."""
    open_settings(page)
    return opened(f"Windows only lets you switch {page} yourself. I've opened {page} settings — "
                  f"flip the switch to turn it {'on' if on else 'off'}.")


# ======================================================================
# Volume
# ======================================================================

def _endpoint():
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    speakers = AudioUtilities.GetSpeakers()
    ep = getattr(speakers, "EndpointVolume", None)
    if ep is not None:
        return ep
    from comtypes import CLSCTX_ALL, cast, POINTER
    iface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


def volume(value: int | None = None, delta: int | None = None, mute: bool | None = None) -> Result:
    try:
        import comtypes
        comtypes.CoInitialize()
        ep = _endpoint()
        if mute is not None:
            ep.SetMute(1 if mute else 0, None)
            return done("Muted." if ep.GetMute() else "Sound is on.")
        current = round(ep.GetMasterVolumeLevelScalar() * 100)
        if value is None and delta is None:
            return info(f"Volume is at {current} percent{' and muted' if ep.GetMute() else ''}.")
        target = max(0, min(100, value if value is not None else current + delta))
        ep.SetMute(0, None)
        ep.SetMasterVolumeLevelScalar(target / 100, None)
        now = round(ep.GetMasterVolumeLevelScalar() * 100)
        return done(f"Volume set to {now} percent.")
    except Exception as e:
        log.exception("volume")
        return failed(f"I couldn't change the volume: {e}")


def media_key(key: str) -> Result:
    vk = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2}[key]
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, 2, 0)
    label = {"play_pause": "Play/pause", "next": "Next track", "previous": "Previous track", "stop": "Stop"}[key]
    return done(f"{label}.", spoken="Done.")


# ======================================================================
# Brightness
# ======================================================================

def brightness(value: int | None = None, delta: int | None = None) -> Result:
    try:
        import screen_brightness_control as sbc
        current = sbc.get_brightness(display=0)[0]
        if value is None and delta is None:
            return info(f"Brightness is at {current} percent.")
        target = max(0, min(100, value if value is not None else current + delta))
        sbc.set_brightness(target, display=0)
        now = sbc.get_brightness(display=0)[0]
        if abs(now - target) <= 2:
            return done(f"Brightness set to {now} percent.")
        return failed(f"I asked for {target} percent but the display reports {now}.")
    except Exception as e:
        log.info("Brightness not supported: %s", e)
        open_settings("display")
        return Result(Outcome.NOT_SUPPORTED, "This display doesn't accept brightness changes from apps "
                      "(external monitors often don't). I've opened Display settings.")


# ======================================================================
# Power
# ======================================================================

def lock() -> Result:
    ok = user32.LockWorkStation()
    return done("Locking your laptop.") if ok else failed("Windows refused to lock.")


def _shutdown(args: list[str]) -> bool:
    return subprocess.run(["shutdown", *args], creationflags=CREATE_NO_WINDOW).returncode == 0


def sleep() -> Result:
    def go():
        ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
        return done("Going to sleep.")
    return confirm("Put the laptop to sleep now?", go)


def restart() -> Result:
    def go():
        return done("Restarting in 15 seconds. Say cancel shutdown to stop it.") if _shutdown(["/r", "/t", "15"]) \
            else failed("Windows refused to restart.")
    return confirm("This will restart your laptop and close all apps. Unsaved work may be lost. Should I continue?", go)


def shutdown() -> Result:
    def go():
        return done("Shutting down in 15 seconds. Say cancel shutdown to stop it.") if _shutdown(["/s", "/t", "15"]) \
            else failed("Windows refused to shut down.")
    return confirm("This will shut down your laptop and close all apps. Unsaved work may be lost. Should I continue?", go)


def signout() -> Result:
    return confirm("Sign out of Windows? Open apps will close.",
                   lambda: done("Signing out.") if _shutdown(["/l"]) else failed("Sign-out failed."))


def cancel_shutdown() -> Result:
    return done("Shutdown cancelled.") if _shutdown(["/a"]) else info("There was no shutdown scheduled.")


# ======================================================================
# Information
# ======================================================================

def battery() -> Result:
    b = psutil.sensors_battery()
    if b is None:
        return info("This computer doesn't report a battery — it's running on mains power.")
    state = "charging" if b.power_plugged else "on battery"
    msg = f"Battery is at {round(b.percent)} percent, {state}"
    if not b.power_plugged and b.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) and b.secsleft > 0:
        h, m = divmod(b.secsleft // 60, 60)
        msg += f", about {h} hours {m} minutes left" if h else f", about {m} minutes left"
    return info(msg + ".", percent=b.percent, plugged=b.power_plugged)


def performance() -> Result:
    cpu = psutil.cpu_percent(interval=0.4)
    mem = psutil.virtual_memory()
    procs = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            procs.append((p.info["memory_info"].rss, p.info["name"]))
        except Exception:
            pass
    agg: dict[str, int] = {}
    for rss, name in procs:
        agg[name] = agg.get(name, 0) + rss
    top = sorted(agg.items(), key=lambda kv: -kv[1])[:3]
    top_s = ", ".join(f"{n.replace('.exe', '')} {v / 1e9:.1f} GB" for n, v in top)
    return info(f"CPU is at {cpu:.0f} percent. Memory is {mem.percent:.0f} percent used, "
                f"{mem.used / 1e9:.1f} of {mem.total / 1e9:.0f} GB. Biggest: {top_s}.",
                spoken=f"CPU is at {cpu:.0f} percent, and memory is {mem.percent:.0f} percent used. "
                       f"The biggest user is {top[0][0].replace('.exe', '')}." if top else None,
                cpu=cpu, mem=mem.percent)


def storage() -> Result:
    parts = []
    spoken = []
    for p in psutil.disk_partitions(all=False):
        if "cdrom" in p.opts or not p.fstype:
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except Exception:
            continue
        parts.append(f"{p.device.rstrip(os.sep)} {u.free / 1e9:.0f} GB free of {u.total / 1e9:.0f} GB ({u.percent:.0f}% used)")
        spoken.append(f"{p.device[0]} drive has {u.free / 1e9:.0f} gigabytes free")
    return info("; ".join(parts) + ".", spoken=", ".join(spoken) + ".")


def status_snapshot() -> dict:
    b = psutil.sensors_battery()
    mem = psutil.virtual_memory()
    sys_drive = os.environ.get("SystemDrive", "C:") + "\\"
    d = psutil.disk_usage(sys_drive)
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "mem": mem.percent,
        "battery": round(b.percent) if b else None,
        "charging": bool(b.power_plugged) if b else None,
        "disk_free_gb": round(d.free / 1e9, 1),
        "disk_percent": d.percent,
    }


# ======================================================================
# Screenshot, theme, clipboard
# ======================================================================

def screenshot() -> Result:
    import mss
    import mss.tools
    folder = Path.home() / "Pictures" / "Screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"Freakyyy_{dt.datetime.now():%Y-%m-%d_%H-%M-%S}.png"
    with mss.mss() as s:
        shot = s.grab(s.monitors[0])
        mss.tools.to_png(shot.rgb, shot.size, output=str(path))
    if path.exists() and path.stat().st_size > 0:
        return done(f"Screenshot saved to {path}.", spoken="Screenshot saved in your Pictures, Screenshots folder.", path=str(path))
    return failed("The screenshot couldn't be saved.")


def dark_mode(on: bool) -> Result:
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    value = 0 if on else 1
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ) as k:
        winreg.SetValueEx(k, "AppsUseLightTheme", 0, winreg.REG_DWORD, value)
        winreg.SetValueEx(k, "SystemUsesLightTheme", 0, winreg.REG_DWORD, value)
        now = winreg.QueryValueEx(k, "AppsUseLightTheme")[0]
    # Tell running apps the theme changed.
    HWND_BROADCAST, WM_SETTINGCHANGE = 0xFFFF, 0x001A
    user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "ImmersiveColorSet", 0x0002, 1000, None)
    if now == value:
        return done("Dark mode is on." if on else "Light mode is on.")
    return failed("Windows didn't apply the theme change.")


def clipboard_get() -> str:
    import win32clipboard
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(13):        # CF_UNICODETEXT
            return win32clipboard.GetClipboardData(13)
        return ""
    finally:
        win32clipboard.CloseClipboard()


def clipboard_set(text: str) -> None:
    import win32clipboard
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, 13)
    finally:
        win32clipboard.CloseClipboard()


def send_keys(*vks: int) -> None:
    """Press a key combination, e.g. send_keys(VK_CONTROL, ord('D'))."""
    for vk in vks:
        user32.keybd_event(vk, 0, 0, 0)
    for vk in reversed(vks):
        user32.keybd_event(vk, 0, 2, 0)


VK_CONTROL, VK_MENU, VK_NEXT, VK_PRIOR, VK_LEFT, VK_RIGHT, VK_RETURN, VK_F5 = 0x11, 0x12, 0x22, 0x21, 0x25, 0x27, 0x0D, 0x74
VK_LWIN, VK_D = 0x5B, 0x44
