"""Deterministic, offline intent parser for Freakyyy Desktop.

text -> normalise -> device selection -> ordered rules -> Intent

Anything no rule recognises becomes `ai.ask`, which the optional Claude brain
answers (email triage, research, open questions). Core automation never
depends on the AI layer.
"""
from __future__ import annotations

import re

from .actions import Device, Intent

_LEADING = sorted([
    "hey freakyyy", "hi freakyyy", "hello freakyyy", "ok freakyyy", "okay freakyyy", "yo freakyyy", "wake up freakyyy", "wake up", "freakyyy",
    "please", "kindly", "can you", "could you", "would you", "will you", "can u",
    "i want you to", "i want to", "i would like to", "i'd like to", "i need you to", "i need to",
    "just", "now", "also", "and", "then",
], key=len, reverse=True)
_TRAILING = ["please", "for me", "now", "right now", "thanks", "thank you", "da", "pa", "bro", "freakyyy"]

# Tanglish action suffixes: "chrome open pannu", "youtube thiranthu"
_TANGLISH_OPEN = re.compile(
    r"^(?P<target>.+?)\s+(open|launch|start)?\s*(pannunga|pannu|pannuda|panni vidu|thira|thiranthu( vidu)?|kaatu|kattu|podu)$")

_WORD_NUMBERS = {
    "zero": 0, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "half": 50, "full": 100,
}


# Spoken forms of the assistant's name (Whisper writes "Freaky", "Freaky's", "Freakie"...).
_NAME = re.compile(r"\b(freak(y+|ie|ey|i|ee)|freeky|freaky's|frikki|friki)\b")


def normalize(text: str) -> str:
    t = text.lower().replace("’", "'")
    t = _NAME.sub("freakyyy", t)
    t = re.sub(r"[!?,;:\"]+", " ", t)
    t = re.sub(r"(?<!\d)\.(?!\d)", " ", t)          # keep 1.5 / file.txt dots
    t = t.replace("wi-fi", "wifi").replace("wi fi", "wifi").replace("vs code", "vscode")
    t = t.replace("visual studio code", "vscode").replace("v s code", "vscode")
    t = re.sub(r"\s+", " ", t).strip()
    changed = True
    while changed:
        changed = False
        for f in _LEADING:
            if t == f:
                return "hello" if "freakyyy" in f else ""
            if t.startswith(f + " "):
                t = t[len(f) + 1:].strip()
                changed = True
        for f in _TRAILING:
            # "exit freakyyy" / "restart freakyyy" name the assistant itself: keep the name.
            if f == "freakyyy" and re.fullmatch(r"(exit|quit|close|shut ?down|goodbye|restart|reload|reboot|show|hide|minimi[sz]e)( the)? freakyyy", t):
                continue
            if t.endswith(" " + f):
                t = t[: -len(f) - 1].strip()
                changed = True
    return t


def percent(t: str) -> int | None:
    m = re.search(r"(\d{1,3})\s*(%|percent|per cent)?", t)
    if m:
        return max(0, min(100, int(m.group(1))))
    for w, v in _WORD_NUMBERS.items():
        if re.search(rf"\b{w}\b", t):
            return v
    return None


def on_off(t: str) -> bool | None:
    if re.search(r"\b(off|disable|deactivate|turn off|switch off|stop|kill)\b", t):
        return False
    if re.search(r"\b(on|enable|activate|turn on|switch on|start)\b", t):
        return True
    return None


_PHONE = re.compile(r"\b(on|in|from|at) (my |the )?(phone|mobile|android|cell ?phone|vivo)\b|\bmy (phone|mobile)('s)?\b|\bphone's\b")
_LAPTOP = re.compile(r"\b(on|in|from) (my |the )?(laptop|computer|pc|desktop|windows|system)\b|\bmy (laptop|computer|pc)('s)?\b|\blaptop's\b")
_BOTH = re.compile(r"\b(on|in|for) both( devices| my devices| phone and laptop| laptop and phone)?\b|\bboth devices\b|\beverywhere\b|\bon all (my )?devices\b")


_PHONE_TAIL = re.compile(r"\s(on|in|from|at|using) (my |the )?(phone|mobile|android|cell ?phone|vivo)( instead| too| as well)?$")
_LAPTOP_TAIL = re.compile(r"\s(on|in|from|using) (my |the )?(laptop|computer|pc|desktop|windows|system)( instead| too| as well)?$")
_PHONE_POSS = re.compile(r"\b(my |the )?(phone|mobile)('s)?\b|\bphone's\b")
_LAPTOP_POSS = re.compile(r"\b(my |the )?(laptop|computer|pc)('s)?\b")


def _strip_device(t: str) -> tuple[str, Device | None]:
    def clean(x: str) -> str:
        return re.sub(r"\s+", " ", x).strip()
    if _BOTH.search(t):
        return clean(_BOTH.sub(" ", t)), Device.BOTH
    # "open bluetooth settings on my phone" (trailing) before "turn on my phone flashlight" (possessive)
    if _PHONE_TAIL.search(t):
        return clean(_PHONE_TAIL.sub(" ", t)), Device.PHONE
    if _LAPTOP_TAIL.search(t):
        return clean(_LAPTOP_TAIL.sub(" ", t)), Device.LAPTOP
    if _PHONE.search(t):
        return clean(_PHONE_POSS.sub(" ", t, count=1)), Device.PHONE
    if _LAPTOP.search(t):
        return clean(_LAPTOP_POSS.sub(" ", t, count=1)), Device.LAPTOP
    return t, None


_CHAIN = re.compile(r"\s(?:and then|and|then)\s(?=(?:open|load|search|start|run|play|go to|show|set|turn|take|check|create|send|lock|launch|mute)\b)")


def _phone_text(rest: str) -> str:
    """Rephrase common queries the way the phone's parser expects them."""
    if re.search(r"\bbattery\b", rest):
        return "battery status"
    if re.search(r"\bnotifications?\b", rest) and not re.search(r"settings|turn|disable|mute|block", rest):
        return "how many notifications do i have"
    if re.search(r"\b(storage|space)\b", rest) and not re.search(r"settings", rest):
        return "how much storage is free"
    if re.fullmatch(r"(show |check )?(status|everything)", rest):
        return "battery status"
    return rest


def parse(raw: str) -> Intent:
    t = normalize(raw)
    if not t:
        return Intent("assistant.greeting", text=t)

    # Memory first: "remember my phone's PIN is…" mustn't be split into a chain or sent to the phone.
    intent = _memory(t)
    if intent:
        intent.text = t
        return intent

    parts = _CHAIN.split(t)
    if len(parts) > 1 and all(p.strip() for p in parts):
        return Intent("chain", {"parts": [p.strip() for p in parts]}, Device.LAPTOP, t)

    # Corrections and transfers mention a device as a destination, not a target.
    for rule in (_corrections, _transfer_rules):
        intent = rule(t)
        if intent:
            intent.text = t
            return intent

    rest, device = _strip_device(t)
    if device in (Device.PHONE, Device.BOTH):
        m = re.fullmatch(r"(start|run|begin|activate)( my| the)? (.+?)( routine| mode)?", rest)
        if device == Device.BOTH and m:
            return Intent("routine.run", {"name": m.group(3)}, Device.BOTH, rest)
        if re.fullmatch(r"(find|locate|ring|where is)( it)?", rest) or not rest:
            return Intent("link.ring", {}, Device.PHONE, rest)
        if re.fullmatch(r"(show |check |get )?(status|stats)", rest) or re.search(r"\bstatus\b", rest):
            return Intent("link.status", {}, Device.PHONE, rest)
        return Intent("remote.command", {"text": _phone_text(rest)}, device, rest)

    for rule in _RULES:
        intent = rule(rest)
        if intent:
            intent.text = rest
            if device:
                intent.device = device
            return intent
    return Intent("ai.ask", {"text": raw.strip()}, Device.LAPTOP, rest)


# ======================================================================
# RULES (order matters: most specific first)
# ======================================================================

def _assistant(t: str) -> Intent | None:
    if re.fullmatch(r"(stop|cancel|abort|halt|enough|quiet|be quiet|shut up|silence|never ?mind|forget it|cancel that|stop that|stop it|stop talking|nothing)", t):
        return Intent("assistant.stop")
    if re.fullmatch(r"(stop|cancel|end)( all)?( current| running)? (automation|automations|routines?|tasks?|everything)", t):
        return Intent("assistant.stop", {"all": True})
    if re.fullmatch(r"go to sleep|sleep now|that's all|thats all|that will be all|you can rest|standby|stand by", t):
        return Intent("assistant.idle")
    m = re.fullmatch(r"(show|hide|open|close|enable|disable)( the)?( dynamic| freakyyy)? (island|notch)", t)
    if m:
        return Intent("assistant.island", {"show": m.group(1) in ("show", "open", "enable")})
    if re.fullmatch(r"(stop|pause|disable|turn off) (listening|the microphone|microphone|mic|wake word)|mute( the)? (microphone|mic)|mute yourself", t):
        return Intent("assistant.stop_listening")
    if re.fullmatch(r"(start|resume|enable|turn on) (listening|the microphone|microphone|mic|wake word)", t):
        return Intent("assistant.start_listening")
    if re.fullmatch(r"(exit|quit|close) (freakyyy|yourself|the assistant)|shut ?down freakyyy|goodbye freakyyy", t):
        return Intent("assistant.exit")
    if re.fullmatch(r"(restart|reload|reboot) (freakyyy|yourself|the assistant)", t):
        return Intent("assistant.restart")
    if re.fullmatch(r"(say (that|it) again|repeat( that)?|what did you say|come again)", t):
        return Intent("assistant.repeat")
    if re.fullmatch(r"(show|open|hide|minimi[sz]e)( the)? (freakyyy|your window|window|interface|dashboard)", t):
        return Intent("assistant.window", {"show": not t.startswith(("hide", "minimi"))})
    if re.fullmatch(r"(open|show)( the| freakyyy)? (settings|preferences|options) of freakyyy|freakyyy settings|your settings", t):
        return Intent("assistant.settings")
    if re.fullmatch(r"(pair|connect|add|link)( a| my| new)? (phone|device|mobile)|add device", t):
        return Intent("link.pair")
    if re.fullmatch(r"(hi|hello|hey|yo|good (morning|afternoon|evening)|vanakkam|namaste)( there)?", t):
        return Intent("assistant.greeting")
    if re.search(r"\b(what('s| is)? the time|what time is it|current time|time now)\b", t):
        return Intent("info.time")
    if re.search(r"\b(what('s| is)? (the |today's )?date|what day is (it|today)|today's date)\b", t):
        return Intent("info.date")
    if re.fullmatch(r"(who are you|what('s| is) your name|introduce yourself)", t):
        return Intent("assistant.identity")
    if re.fullmatch(r"(help|what can you do|what do you do|commands|what can i say|show commands)", t):
        return Intent("assistant.help")
    if re.fullmatch(r"(thank you|thanks|thanks a lot|great|awesome|nice|cool|perfect|good job)( freakyyy)?", t):
        return Intent("assistant.thanks")
    return None


_MEM_ADD = re.compile(r"(?:please )?(?:remember|note|keep in mind|don't forget|do not forget|save (?:this|that)(?: to memory)?|memori[sz]e)(?: that| this)?[:,]? (?P<x>.{3,})", re.I)


def _memory(t: str) -> Intent | None:
    if re.fullmatch(r"(forget|clear|erase|delete|wipe) (everything|all)( you know| you remember)?( about me)?|(clear|erase|delete|wipe|reset) (your|my|all|the)( long term)? memor(y|ies)", t):
        return Intent("memory.forget_all")
    if re.fullmatch(r"what (do|did) you (remember|know)( about me)?|what have you (remembered|saved)( about me)?|(show|list|read)( me)? (your|my|the)( saved)? memor(y|ies)|what('s| is) in your memory", t):
        return Intent("memory.list")
    m = re.fullmatch(r"(what do you (remember|know)|what did i (tell|say to) you|what have i told you|do you remember)( anything)? about (?P<q>.+)", t)
    if m:
        return Intent("memory.recall", {"query": m.group("q")})
    m = (re.fullmatch(r"forget( that| about| the fact that| what i said about)? (?P<q>.+?)( from (your )?memory)?", t)
         or re.fullmatch(r"(delete|erase|remove)( that| the fact that| what i said about)? (?P<q>.+?) from (your |my )?memory", t))
    if (m and m.group("q") not in ("it", "that", "this", "about it", "all that", "it all")
            and not re.search(r"\bprofile\b", t) and not re.search(r"\b(file|folder|email|mail|message|photo|app)s?\b", t)):
        return Intent("memory.forget", {"query": m.group("q")})
    m = _MEM_ADD.fullmatch(t)
    if m and not t.startswith(("remember me ", "note down ")) and not re.match(r"(note|save this|save that)\b.*\b(notepad|file|folder)\b", t):
        return Intent("memory.add", {"text": m.group("x")})
    return None


def _corrections(t: str) -> Intent | None:
    if re.fullmatch(r"(no |nope )?(use|do (that|it)|try)( it)? (on )?(my |the )?(phone|mobile)( instead)?|(do|run) (that|it) on (my |the )?phone( instead)?", t):
        return Intent("context.redo", {"device": "phone"})
    if re.fullmatch(r"(no |nope )?(use|do (that|it)|try)( it)? (on )?(my |the )?(laptop|computer|pc)( instead)?|(do|run) (that|it) on (my |the )?(laptop|computer|pc)( instead)?", t):
        return Intent("context.redo", {"device": "laptop"})
    if re.fullmatch(r"(no |nope )?(,? )?(open |use |pick |choose )?the other( one| project| folder| file| app)?", t):
        return Intent("context.other")
    return None


def _transfer_rules(t: str) -> Intent | None:
    m = re.fullmatch(r"(send|share|transfer|push|copy) (this|that|the|my)? ?(file|pdf|document|image|photo|picture|video|selected file|selection)?( called | named )?(?P<name>.*?) ?to (my |the )?(phone|mobile|android)", t)
    if m:
        name = (m.group("name") or "").strip()
        if re.fullmatch(r"(my )?clipboard|(the )?(text|copied text)", name):
            return Intent("link.clipboard_push", {}, Device.PHONE)
        if re.fullmatch(r"(this |that |the )?(page|website|link|url|tab)", name):
            return Intent("link.send_page", {}, Device.PHONE)
        return Intent("link.send_file", {"name": name}, Device.PHONE)
    if re.fullmatch(r"(send|share|push|copy) (my |the )?clipboard to (my |the )?(phone|mobile)", t):
        return Intent("link.clipboard_push", {}, Device.PHONE)
    if re.fullmatch(r"(get|read|pull|paste|show|fetch) (my |the )?(phone'?s? |mobile )?clipboard( from (my |the )?(phone|mobile))?", t) and "phone" in t:
        return Intent("link.clipboard_pull", {}, Device.PHONE)
    if re.fullmatch(r"(find|locate|ring|where is|where's) (my |the )?(phone|mobile)", t):
        return Intent("link.ring", {}, Device.PHONE)
    if re.fullmatch(r"(open|send|show) (this|that|the) (page|website|site|link|tab) on (my |the )?(phone|mobile)", t):
        return Intent("link.send_page", {}, Device.PHONE)
    if re.fullmatch(r"(show|check|get) (my )?(phone|mobile) status|how is my phone", t):
        return Intent("link.status", {}, Device.PHONE)
    return None


def _routines(t: str) -> Intent | None:
    m = re.fullmatch(r"(start|run|begin|activate|launch|enable|switch to|enter)( my| the)? (?P<n>.+?) (routine|mode)", t) \
        or re.fullmatch(r"(start|run|begin|activate)( my| the)? (?P<n>study|work|sleep|focus|morning|night|gym|coding|gaming)( time)?", t)
    if m and m.group("n") not in ("dark", "light", "airplane", "flight", "sleep mode off", "battery saver", "focus assist", "power saving"):
        return Intent("routine.run", {"name": m.group("n")})
    if re.fullmatch(r"(show|open|list)( my)? routines", t):
        return Intent("assistant.routines")
    return None


def _system(t: str) -> Intent | None:
    # power
    if re.fullmatch(r"lock( my| the)?( laptop| computer| pc| screen| system| device)?", t):
        return Intent("sys.lock")
    if re.fullmatch(r"(put )?(my |the )?(laptop|computer|pc|system)? ?(to )?sleep|sleep( my| the)? (laptop|computer|pc|system)|hibernate.*", t) and "listening" not in t:
        return Intent("sys.sleep")
    if re.fullmatch(r"(restart|reboot)( my| the)?( laptop| computer| pc| system| windows)?", t):
        return Intent("sys.restart")
    if re.fullmatch(r"(shut ?down|power off|turn off)( my| the)? (laptop|computer|pc|system|windows)|shut ?down", t):
        return Intent("sys.shutdown")
    if re.fullmatch(r"(cancel|abort|stop) (the )?(shut ?down|restart|reboot)", t):
        return Intent("sys.cancel_shutdown")
    if re.fullmatch(r"(sign|log) ?out( of windows)?", t):
        return Intent("sys.signout")
    # screenshot
    if re.search(r"\b(take|capture|grab)( a)? (screen ?shot|snapshot|screen capture)\b|^screen ?shot$|\bcapture (the )?screen\b", t):
        return Intent("sys.screenshot")
    if re.search(r"\b(snipping tool|snip)\b", t):
        return Intent("app.open", {"name": "snipping tool"})
    # task manager / running apps
    if re.search(r"\btask manager\b", t):
        return Intent("app.open", {"name": "task manager"})
    if re.fullmatch(r"(show|list|what are)( the| my| all)? (running|open) (apps|applications|programs|windows)( are there)?", t):
        return Intent("app.list_running")
    # performance and info
    if re.fullmatch(r"(show |check |get |what's |what is )?(my |the )?(system )?(status|stats|overview|health|everything)( report)?", t):
        return Intent("sys.status")
    if re.search(r"\b(cpu|processor|ram|memory usage|memory|performance)\b", t) and not re.search(r"\bsettings?\b", t):
        return Intent("sys.performance")
    if re.search(r"\bbattery\b", t) and not re.search(r"\b(saver|settings?)\b", t):
        return Intent("sys.battery")
    if re.search(r"\b(disk|storage|drive) (space|usage|left|free|status)\b|\bhow much (disk |storage )?space\b|\bavailable (disk )?space\b|\bfree space\b", t):
        return Intent("sys.storage")
    if re.search(r"\b(large|big|biggest|largest|huge) files\b", t):
        return Intent("file.large")
    # volume / media
    if re.search(r"\b(un ?mute)\b", t) and not re.search(r"notifications?", t):
        return Intent("sys.volume", {"mute": False})
    if re.fullmatch(r"mute( the)?( volume| sound| audio| laptop| computer| speakers)?", t):
        return Intent("sys.volume", {"mute": True})
    if re.search(r"\b(volume|louder|quieter|softer)\b", t) and not re.search(r"settings?$", t):
        return Intent("sys.volume", _level(t, "louder", "quieter|softer"))
    if re.fullmatch(r"(play|pause|resume)( the)?( music| song| media| video| playback)?|(play|pause) music", t):
        return Intent("media.key", {"key": "play_pause"})
    if re.fullmatch(r"(next|skip)( the)?( song| track| video)?|play next( song)?", t):
        return Intent("media.key", {"key": "next"})
    if re.fullmatch(r"(previous|last|go back to the previous)( song| track| video)?|play previous( song)?", t):
        return Intent("media.key", {"key": "previous"})
    # brightness
    if re.search(r"\b(brightness|brighter|dimmer|dim the screen|dim screen)\b", t) and not re.search(r"settings?$", t):
        return Intent("sys.brightness", _level(t, "brighter", "dimmer|dim"))
    # themes
    if re.search(r"\b(dark|night) (mode|theme)\b", t) and not re.search(r"settings?$", t):
        return Intent("sys.dark_mode", {"on": on_off(t) is not False})
    if re.search(r"\blight (mode|theme)\b", t) and not re.search(r"settings?$", t):
        return Intent("sys.dark_mode", {"on": on_off(t) is False})
    if re.search(r"\bnight light\b", t):
        return Intent("sys.settings", {"page": "night light"})
    # radios -> settings pages (Windows apps can't toggle radios silently)
    for word, page in (("wifi", "wifi"), ("bluetooth", "bluetooth"), ("airplane mode", "airplane mode"),
                       ("flight mode", "airplane mode"), ("hotspot", "hotspot"), ("vpn", "vpn")):
        if re.search(rf"\b{word}\b", t) and on_off(t) is not None and not t.endswith("settings"):
            return Intent("sys.radio", {"page": page, "on": on_off(t)})
    if re.fullmatch(r"(empty|clear|clean)( the| my)? recycle ?bin", t):
        return Intent("file.empty_recycle_bin")
    if re.fullmatch(r"(show|go to|minimi[sz]e (all|everything)( windows)?|show the)? ?desktop|minimi[sz]e (all|everything)( windows)?", t):
        return Intent("window.show_desktop")
    # clipboard
    if re.fullmatch(r"(read|what('s| is) (on|in)|show)( my| the)? clipboard", t):
        return Intent("clipboard.read")
    return None


def _settings(t: str) -> Intent | None:
    m = re.fullmatch(r"(?:open|show|go to) (?:the )?settings (?:for|of) (?P<p>.+)", t)
    if m:
        return Intent("sys.settings", {"page": m.group("p")})
    m = re.fullmatch(r"(?:(?:open|show|go to|launch|take me to|bring up)(?: me)? )?(?:the |my )?(?:windows )?(?P<p>.*?) ?(?:settings?|options|preferences|page)", t)
    if m and not re.search(r"\b(freakyyy|your)\b", t):
        page = m.group("p").strip() or "main"
        return Intent("sys.settings", {"page": page})
    if re.fullmatch(r"(open|show|launch)( the)? (control panel|device manager|disk management|services|registry editor|event viewer|system information)", t):
        return Intent("app.open", {"name": re.sub(r"^(open|show|launch)( the)? ", "", t)})
    return None


def _email(t: str) -> Intent | None:
    if not re.search(r"\b(e-?mails?|mails?|inbox|gmail|messages from)\b", t):
        return None
    if re.search(r"\b(send|reply|write|compose|forward|delete)\b", t):
        return Intent("ai.ask", {"text": t})
    m = re.search(r"\b(?:from|about|regarding|for|related to|containing|with) (?P<q>.+)$", t)
    if re.search(r"\b(search|find|look for|any)\b", t) and m and not re.search(r"\b(important|new|unread|latest)\b", m.group("q")):
        return Intent("mail.search", {"query": m.group("q").strip()})
    if re.search(r"\b(latest|last|newest|recent) (e-?mail|mail)\b|\bread (my )?(latest|last) (e-?mail|mail)\b", t):
        return Intent("mail.latest")
    if re.search(r"\b(open|show)\b.*\b(gmail|inbox|email|mail)\b$", t) and not re.search(r"\b(any|new|important|unread)\b", t):
        return Intent("web.open_site", {"site": "gmail"})
    return Intent("mail.check", {"important": bool(re.search(r"\bimportant|urgent|priority\b", t))})


def _dev(t: str) -> Intent | None:
    if re.search(r"\bgit status\b|\b(any|what) (uncommitted )?changes\b|\bwhat changed\b|\bcheck (the )?(git|repo|repository)\b", t):
        return Intent("dev.git_status", {"project": _project_ref(t)})
    m = re.search(r"\bcommit( (all|these|the|my))?( changes)?( with (the )?message (?P<msg>.+))?", t)
    if m and t.startswith(("commit", "git commit", "make a commit")):
        return Intent("dev.git_commit", {"message": (m.group("msg") or "").strip(), "project": None})
    if re.fullmatch(r"(git )?push( (my |the |these )?(changes|commits|code))?( to (github|origin|remote))?", t):
        return Intent("dev.git_push")
    if re.fullmatch(r"(git )?pull( (the )?(latest )?(changes|code))?( from (github|origin|remote))?", t):
        return Intent("dev.git_pull")
    if re.search(r"\b(gradle )?(build|assemble|compile)\b.*\b(succeed\w*|success\w*|pass\w*|fail\w*|status|result|done|finished|complete\w*)\b|\bdid (the |my )?(gradle )?build\b|\bbuild (status|result)\b", t):
        return Intent("dev.build_status")
    if re.search(r"\b(latest |last )?(build )?errors?\b", t) and re.search(r"\b(show|read|what|build|latest|last)\b", t):
        return Intent("dev.build_errors")
    if re.search(r"\b(run|start|do)( a| the)? (gradle )?(build|assemble)\b|\bbuild (the |my |this )?(project|app|apk)\b|\bgradle build\b|\bassemble debug\b", t):
        return Intent("dev.gradle_build", {"project": _project_ref(t)})
    if re.search(r"\bnpm (install|i)\b|\binstall (the )?(node )?(dependencies|packages|modules)\b", t):
        return Intent("dev.npm_install", {"project": _project_ref(t)})
    if re.search(r"\b(start|run|launch)( the| my)? (dev|development|local) server\b|\bnpm (run )?(dev|start)\b", t):
        return Intent("dev.server_start", {"project": _project_ref(t)})
    if re.search(r"\b(stop|kill|shut ?down|end)( the| my)? (dev|development|local) server\b", t):
        return Intent("dev.server_stop")
    m = re.search(r"\b(run|start|launch|execute)( my| the)? (?P<p>.*?)\s*(python|py) (project|app|application|script|program)\b", t) \
        or re.search(r"\b(run|start|launch|execute)( my| the)? (python|py) (project|app|application|script|program)( (called|named) )?(?P<p>.*)$", t)
    if m:
        return Intent("dev.run_python", {"project": (m.group("p") or "").strip() or None})
    if re.search(r"\b(open|launch)( a| the)? (terminal|command prompt|powershell|cmd|shell)( (here|in (this|the|that|my) (folder|project|directory)|in (?P<p>.+)))?$", t):
        m = re.search(r"\bin (?!this|the folder|that|here)(?P<p>.+)$", t)
        here = bool(re.search(r"\b(here|this|that|the) (folder|project|directory)\b|\bhere$", t))
        if here or m:
            return Intent("dev.terminal", {"project": m.group("p") if m else None, "here": here})
    if re.fullmatch(r"(?:open|go to|show|visit)(?: my| the| this)?(?: github)? (?:repo|repository)(?: on github)?", t):
        return Intent("web.open_repo")
    m = re.fullmatch(r"(?:open|load|show|launch|start)(?: up)? (?:my |the |our )?(?P<p>.+?) (?:project|repo|repository|codebase|workspace|app source)(?: (?:in|with|on|using) (?P<ide>vscode|code|android studio|studio|visual studio|explorer|file explorer|terminal|intellij|pycharm))?", t)
    if m:
        proj = m.group("p")
        if proj in ("the", "this", "that", "my", "current", "our", "it"):
            proj = None
        return Intent("dev.open_project", {"project": proj, "ide": m.group("ide")})
    m = re.fullmatch(r"(?:open|load|show) (?:this|that|the|it|my) ?(?:project|folder|repo)? (?:in|with|on|using) (?P<ide>vscode|code|android studio|studio|visual studio|explorer|file explorer|terminal|intellij|pycharm)", t)
    if m:
        return Intent("dev.open_project", {"project": None, "ide": m.group("ide")})
    m = re.fullmatch(r"(?:open|show)(?: my| the)? (?P<p>[\w .-]+?) (?:folder|directory)", t)
    if m and m.group("p") not in ("downloads", "download", "documents", "pictures", "music", "videos", "desktop", "home", "screenshots", "this", "that", "the"):
        return Intent("file.open_folder", {"name": m.group("p")})
    if re.fullmatch(r"(open|show)( my| the)? (project folder|projects|my projects|all projects|project list)", t):
        return Intent("dev.list_projects")
    return None


def _project_ref(t: str) -> str | None:
    m = re.search(r"\b(?:in|for|of|on) (?:my |the )?(?P<p>[\w .-]+?) (?:project|repo|repository|app)\b", t)
    return m.group("p").strip() if m and m.group("p") not in ("this", "that", "the", "current") else None


def _browser(t: str) -> Intent | None:
    if re.fullmatch(r"scroll (down|up)( a bit| more| the page)?|page (down|up)|scroll", t):
        return Intent("web.scroll", {"down": "up" not in t})
    if re.fullmatch(r"(go )?back( to the previous page)?|previous page", t):
        return Intent("web.back")
    if re.fullmatch(r"(go )?forward|next page", t):
        return Intent("web.forward")
    if re.fullmatch(r"(refresh|reload)( the)?( page| tab)?", t):
        return Intent("web.refresh")
    if re.fullmatch(r"(close)( the| this)? (tab|current tab)", t):
        return Intent("web.close_tab")
    if re.fullmatch(r"(open )?(a )?new tab", t):
        return Intent("web.new_tab")
    m = re.fullmatch(r"(click|open|go to|select|show)( on)?( the)? (?P<n>first|second|third|fourth|fifth|top|1st|2nd|3rd|\d)( search)? (result|link|one|option)", t)
    if m:
        order = {"first": 1, "top": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "fifth": 5}
        n = order.get(m.group("n")) or int(m.group("n"))
        return Intent("web.open_result", {"index": n})
    if re.fullmatch(r"(read|read out|read me)( this| the| current| the current)? (page|article|website|site|tab)( for me)?|what('s| is) (on )?(this|the) page( about)?", t):
        return Intent("web.read_page", {"summarize": "about" in t})
    if re.fullmatch(r"(summari[sz]e|give me a summary of|tldr)( this| the| current| the current)? (page|article|website|site|tab|video)", t):
        return Intent("web.read_page", {"summarize": True})
    if re.fullmatch(r"(download|save)( this| the)? (pdf|file|document)( from (this|the) page)?", t):
        return Intent("web.download_pdf")
    if re.fullmatch(r"(bookmark|save)( this| the)? (page|site|website|tab)( to bookmarks)?|add( this| the)? (page|site)? ?to bookmarks|bookmark (this|it)", t):
        return Intent("web.bookmark")
    m = re.fullmatch(r"(?:search|look up|find|play)(?: for)? (?P<q>.+?) on youtube|(?:search )?youtube (?:for )?(?P<q2>.+)|play (?P<q3>.+?) on youtube", t)
    if m:
        return Intent("web.search", {"query": m.group("q") or m.group("q2") or m.group("q3"), "engine": "youtube"})
    m = re.fullmatch(r"(?:find|show me|open|get me|go to|search for)(?: the)? official (?P<q>.+?)(?: documentation| docs| website| site| page)?", t)
    if m:
        return Intent("web.lucky", {"query": f"official {m.group('q')} documentation" if "doc" in t else f"official {m.group('q')}"})
    m = re.fullmatch(r"(?:search|look up|google|find|search the web|search online)(?: for| about)? (?P<q>.+?)(?: on (?:google|the web|the internet|chrome|edge|bing))?", t)
    if m and not re.search(r"\b(file|files|folder|document|documents|pdf|downloads|my documents|email|mail|app|apps|application)\b", t):
        return Intent("web.search", {"query": m.group("q"), "engine": "google"})
    m = re.fullmatch(r"(?:open|go to|visit|browse to|take me to) (?P<u>(?:https?://)?[\w-]+(?:\.[\w-]+)+(?:/\S*)?)", t)
    if m:
        return Intent("web.open_url", {"url": m.group("u")})
    m = re.fullmatch(r"(?:open|go to|visit|take me to|launch) (?P<s>youtube|github|gmail|google|linkedin|stack ?overflow|reddit|twitter|x|instagram|facebook|chatgpt|claude|amazon|flipkart|netflix|google drive|drive|google docs|docs|google sheets|sheets|google calendar|calendar online|maps|google maps|whatsapp web|outlook|leetcode|hacker ?rank|kaggle|hugging ?face|medium|wikipedia|internshala|naukri|indeed|glassdoor|unstop)(?: website| site| dot com)?", t)
    if m:
        return Intent("web.open_site", {"site": m.group("s")})
    return None


def _files(t: str) -> Intent | None:
    known = r"(downloads?|documents?|pictures?|photos|music|videos?|desktop|home|screenshots|recycle ?bin|this pc|onedrive)"
    m = re.fullmatch(rf"(?:open|show|go to|take me to)(?: my| the)? {known}(?: folder)?", t)
    if m:
        return Intent("file.open_known", {"name": m.group(1)})
    if re.fullmatch(r"(find|show|open|what('s| is))( me)?( my| the)? (latest|last|recent|newest|most recent) (download|downloaded file|file i downloaded)", t) \
            or re.fullmatch(r"(find|show)( my)? downloads", t):
        return Intent("file.latest_download", {"open": t.startswith("open")})
    m = re.fullmatch(r"(?:create|make|new)(?: a)?(?: new)? folder(?: (?:called|named))? (?P<n>.+?)(?: (?:in|on|inside|at) (?:my |the )?(?P<loc>.+))?", t)
    if m:
        return Intent("folder.create", {"name": m.group("n"), "location": m.group("loc")})
    m = re.fullmatch(r"(?:create|make|new)(?: a)?(?: new)? folder(?: (?:in|on|inside|at) (?:my |the )?(?P<loc>.+))?", t)
    if m:
        return Intent("folder.create", {"name": None, "location": m.group("loc")})
    m = re.fullmatch(r"rename (?P<f>.+?) (?:to|as) (?P<n>.+)", t)
    if m:
        return Intent("file.rename", {"target": m.group("f"), "new_name": m.group("n")})
    m = re.fullmatch(r"(?P<op>copy|move) (?P<f>.+?) (?:to|into) (?:my |the )?(?P<d>.+)", t)
    if m and "phone" not in t:
        return Intent(f"file.{m.group('op')}", {"target": m.group("f"), "dest": m.group("d")})
    m = re.fullmatch(r"(?P<perm>permanently )?(?:delete|remove|trash|erase) (?:the |my )?(?P<f>.+?)(?: permanently)?", t)
    if m and not re.search(r"\b(notifications?|history|routine|app|application)\b", t):
        return Intent("file.delete", {"target": m.group("f"), "permanent": bool(m.group("perm")) or t.endswith("permanently")})
    m = re.fullmatch(r"(?:search|find|look for|locate|where is|where's)(?: for)?(?: my| the| a)? (?P<q>.+?)(?: (?:file|files|document|documents|pdf|pdfs))?(?: (?:in|on|inside) (?:my |the )?(?P<loc>documents|downloads|desktop|pictures|projects?|computer|laptop|drive|everywhere))?", t)
    if m and (re.search(r"\b(file|files|document|documents|pdf|pdfs|folder|my documents|downloads|resume|photo|image|spreadsheet|presentation)\b", t)
              or m.group("loc")):
        q = re.sub(r"\b(my|the)\b", "", m.group("q")).strip()
        q = re.sub(r"^(documents|downloads) for ", "", q)
        return Intent("file.search", {"query": q, "location": m.group("loc"), "pdf": "pdf" in t})
    m = re.fullmatch(r"(?:search|look) (?:my |the )?(?P<loc>documents|downloads|desktop|projects|computer) for (?P<q>.+)", t)
    if m:
        return Intent("file.search", {"query": m.group("q"), "location": m.group("loc"), "pdf": "pdf" in t})
    m = re.fullmatch(r"open (?:the |my )?(?P<q>.+?)\.(?P<ext>pdf|docx?|xlsx?|pptx?|txt|csv|png|jpe?g|mp4|mp3|zip|py|kt|java|md)", t) \
        or re.fullmatch(r"open (?:the |my )?(?P<q>.+?) (?P<ext>pdf|document|doc|spreadsheet|presentation|file|image|photo)", t)
    if m:
        return Intent("file.open", {"query": m.group("q"), "ext": m.group("ext")})
    return None


def _windows(t: str) -> Intent | None:
    m = re.fullmatch(r"(?:switch|go|change)(?: back)? to (?P<n>.+?)(?: window| app)?", t)
    if m and m.group("n") not in ("dark mode", "light mode", "the desktop", "desktop"):
        return Intent("window.switch", {"name": m.group("n")})
    m = re.fullmatch(r"(?P<op>minimi[sz]e|maximi[sz]e|restore|close|quit|exit|kill|snap left|snap right)(?: the| this| that| current| selected| active)?(?: (?P<n>.+?))?(?: window| app| application| program)?", t)
    if m:
        op = m.group("op")
        name = re.sub(r"^(the |this |that )?(selected|current|active|focused)\b", "", (m.group("n") or "").strip()).strip()
        if name in ("", "it", "this", "that", "window", "app", "application", "program"):
            name = None
        op = {"minimise": "minimize", "maximise": "maximize", "quit": "close", "exit": "close"}.get(op, op)
        if op == "kill":
            return Intent("app.kill", {"name": name})
        return Intent(f"window.{op.replace(' ', '_')}", {"name": name})
    return None


_BROWSER = r"(?P<b>brave|chrome|google chrome|edge|microsoft edge|firefox)( browser)?"


def _browser_profiles(t: str) -> Intent | None:
    any_b = _BROWSER.replace('?P<b>', '')
    if re.fullmatch(rf"(stop|don't|do not|never)( always)?( using| use| open(ing)?)( a| the| any)? profile (for|with|in) {any_b}|"
                    rf"(forget|clear|reset)( the| my)? {any_b} profile|open {any_b} normally|"
                    rf"(always )?open {any_b} (without|with no) (a )?profile", t):
        b = re.search(_BROWSER, t).group("b")
        return Intent("browser.profile_clear", {"browser": b})
    m = re.fullmatch(rf"(?P<always>always |from now on |by default )?(open|launch|start|use)( up)?( the| my)? {_BROWSER} "
                     rf"(with|in|using|on|for)( the| my| a)? (?P<p>.+?)(?P<always2> (always|from now on|by default|every time))?", t) \
        or re.fullmatch(rf"(?P<always>always |from now on |by default )?(open|launch|start|use)( the| my)? (?P<p>.+?) profile (in|on|of|for) {_BROWSER}"
                        rf"(?P<always2> (always|from now on|by default|every time))?", t)
    if m:
        return Intent("browser.profile_open", {"browser": m.group("b"), "profile": m.group("p"),
                                                "always": bool(m.group("always") or m.group("always2"))})
    return None


def _apps(t: str) -> Intent | None:
    m = re.fullmatch(r"(?:search|find|look for)(?: for)?(?: the| an)? (?P<n>.+?) (?:app|application|program)s?(?: installed)?|is (?P<n2>.+?) installed", t)
    if m:
        return Intent("app.search", {"name": m.group("n") or m.group("n2")})
    m = _TANGLISH_OPEN.fullmatch(t)
    if m:
        return Intent("app.open", {"name": m.group("target")})
    m = re.fullmatch(r"(?:open|launch|start|run|fire up|bring up|load)(?: up)?(?: the| my)? (?P<n>.+?)(?: app| application| program)?(?: and (?P<then>.+))?", t)
    if m:
        name = m.group("n")
        then = m.group("then")
        params = {"name": name}
        if then:
            params["then"] = then
        return Intent("app.open", params)
    return None


def _level(t: str, up: str, down: str) -> dict:
    p = percent(t)
    if p is not None and re.search(r"\d|percent|half|full|zero", t):
        if re.search(r"\b(increase|raise|up|by|more|add)\b", t) and re.search(r"\bby\b", t):
            return {"delta": p}
        if re.search(r"\b(decrease|lower|reduce|down)\b", t) and re.search(r"\bby\b", t):
            return {"delta": -p}
        return {"value": p}
    if re.search(rf"\b(max|maximum|full|highest)\b", t):
        return {"value": 100}
    if re.search(rf"\b(min|minimum|lowest)\b", t):
        return {"value": 0}
    if re.search(rf"\b(increase|raise|up|higher|more|turn up|boost|{up})\b", t):
        return {"delta": 10}
    if re.search(rf"\b(decrease|lower|reduce|down|less|turn down|{down})\b", t):
        return {"delta": -10}
    return {}


_RULES = [_assistant, _memory, _corrections, _routines, _email, _system, _dev, _browser_profiles, _files, _browser, _settings, _windows, _apps]
