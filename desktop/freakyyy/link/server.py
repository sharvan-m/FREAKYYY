"""Freakyyy Link server (desktop side). See protocol/FREAKYYY_LINK_PROTOCOL.md."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..config import get_secret, set_secret, settings
from . import security as sec

log = logging.getLogger(__name__)
DEVICES = sec.LINK_DIR / "devices.json"
ACTIONS = {"run_command", "confirm", "get_status", "open_url", "ring", "clipboard_push", "clipboard_pull",
           "notify", "routine_run"}


@dataclass
class Device:
    device_id: str
    name: str
    platform: str = "android"
    paired_at: float = field(default_factory=time.time)
    online: bool = False
    last_seen: float = 0.0
    status: dict = field(default_factory=dict)

    def public(self) -> dict:
        return {"device_id": self.device_id, "name": self.name, "platform": self.platform, "online": self.online,
                "last_seen": self.last_seen, "status": self.status}


@dataclass
class PendingPair:
    token: str
    expires: float
    device_id: str | None = None
    device_name: str | None = None
    code: str | None = None
    phone_confirmed: bool = False
    desktop_decision: bool | None = None
    ws: Any = None


class LinkServer:
    """Runs on its own asyncio loop in a background thread."""

    def __init__(self, handle_request: Callable[[str, dict, Device], dict],
                 on_event: Callable[[str, dict], None]) -> None:
        self.handle_request = handle_request          # called on a worker thread
        self.on_event = on_event
        self.devices: dict[str, Device] = {}
        self._sockets: dict[str, Any] = {}
        self._waiters: dict[str, asyncio.Future] = {}
        self._incoming: dict[str, dict] = {}
        self._outgoing_cancel: set[str] = set()
        self.pending: PendingPair | None = None
        self.loop = asyncio.new_event_loop()
        self.running = False
        self.error = ""
        self.ident = sec.server_identity()
        self._load_devices()

    # ------------------------------------------------------------------ setup
    def _load_devices(self):
        if DEVICES.exists():
            for d in json.loads(DEVICES.read_text()):
                self.devices[d["device_id"]] = Device(d["device_id"], d["name"], d.get("platform", "android"),
                                                      d.get("paired_at", 0))

    def _save_devices(self):
        DEVICES.write_text(json.dumps([{"device_id": d.device_id, "name": d.name, "platform": d.platform,
                                        "paired_at": d.paired_at} for d in self.devices.values()], indent=2))

    def start(self) -> None:
        threading.Thread(target=self._thread, daemon=True, name="freakyyy-link").start()

    def _thread(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._serve())
        except Exception as e:
            log.exception("Link server stopped")
            self.error = str(e)
            self.running = False
            self.on_event("link_error", {"error": str(e)})

    async def _serve(self):
        from websockets.asyncio.server import serve
        port = int(settings.get("link_port"))
        async with serve(self._handler, "0.0.0.0", port, ssl=sec.ssl_context(), max_size=1 << 20,
                         ping_interval=20, ping_timeout=40):
            self.running = True
            log.info("Freakyyy Link listening on %d (fp %s)", port, sec.fingerprint()[:16])
            self.on_event("link_ready", {"port": port})
            await asyncio.Future()

    # ------------------------------------------------------------------ pairing (UI side)
    def create_pairing(self) -> str:
        self.pending = PendingPair(sec.new_token(), time.time() + 300)
        payload = {"v": 1, "name": self.ident["name"], "hosts": sec.local_ips(), "port": int(settings.get("link_port")),
                   "fp": sec.fingerprint(), "token": self.pending.token}
        return "freakyyylink://pair?d=" + sec.b64(json.dumps(payload).encode())

    def decide_pairing(self, accept: bool) -> None:
        p = self.pending
        if p:
            p.desktop_decision = accept
            asyncio.run_coroutine_threadsafe(self._finish_pairing(), self.loop)

    async def _finish_pairing(self):
        p = self.pending
        if not p or not p.ws or p.desktop_decision is None:
            return
        if p.desktop_decision is False:
            await p.ws.send(json.dumps({"type": "pair_reject", "reason": "Declined on the laptop."}))
            self.pending = None
            self.on_event("pair_done", {"ok": False})
            return
        if not p.phone_confirmed:
            return
        secret = sec.new_secret()
        set_secret(f"link:{p.device_id}", sec.b64(secret))
        self.devices[p.device_id] = Device(p.device_id, p.device_name or "Phone")
        self._save_devices()
        await p.ws.send(json.dumps({"type": "pair_ok", "device_secret": sec.b64(secret),
                                    "server_id": self.ident["server_id"], "server_name": self.ident["name"]}))
        self.on_event("pair_done", {"ok": True, "name": p.device_name})
        self.pending = None

    def remove_device(self, device_id: str) -> None:
        self.devices.pop(device_id, None)
        self._save_devices()
        set_secret(f"link:{device_id}", None)
        ws = self._sockets.pop(device_id, None)
        if ws:
            asyncio.run_coroutine_threadsafe(ws.close(4001, "unpaired"), self.loop)
        self.on_event("devices", {})

    # ------------------------------------------------------------------ connection handler
    async def _handler(self, ws):
        peer = ws.remote_address[0] if ws.remote_address else ""
        if not sec.is_allowed_peer(peer, bool(settings.get("link_allow_public_peers"))):
            log.warning("Rejected non-private peer %s", peer)
            await ws.close(4003, "forbidden")
            return
        nonce = sec.b64(secrets.token_bytes(32))
        await ws.send(json.dumps({"type": "challenge", "nonce": nonce, "server_id": self.ident["server_id"]}))
        try:
            first = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        except Exception:
            await ws.close(4000, "timeout")
            return
        if first.get("type") == "pair_request":
            await self._pair_session(ws, first)
            return
        if first.get("type") != "auth":
            await ws.close(4002, "auth required")
            return
        device = self.devices.get(first.get("device_id", ""))
        secret_b64 = get_secret(f"link:{device.device_id}") if device else None
        if not device or not secret_b64:
            await ws.send(json.dumps({"type": "auth_fail", "reason": "not_paired"}))
            await ws.close(4004, "not paired")
            return
        secret = sec.unb64(secret_b64)
        if not sec.verify(secret, f"client|{nonce}|{device.device_id}", first.get("proof", "")):
            log.warning("Bad proof from %s", device.name)
            await ws.send(json.dumps({"type": "auth_fail", "reason": "bad_proof"}))
            await ws.close(4004, "bad proof")
            return
        await ws.send(json.dumps({"type": "auth_ok", "server_name": self.ident["name"],
                                  "proof": sec.hmac_b64(secret, f"server|{first.get('nonce', '')}|{self.ident['server_id']}")}))
        old = self._sockets.get(device.device_id)
        if old:
            await old.close(4005, "replaced")
        self._sockets[device.device_id] = ws
        device.online, device.last_seen = True, time.time()
        self.on_event("device_online", device.public())
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    continue
                device.last_seen = time.time()
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                await self._dispatch(ws, device, msg)
        except Exception as e:
            log.info("Device %s disconnected: %s", device.name, e)
        finally:
            if self._sockets.get(device.device_id) is ws:
                self._sockets.pop(device.device_id, None)
                device.online = False
                self.on_event("device_offline", device.public())

    async def _pair_session(self, ws, msg):
        p = self.pending
        # One-time token: refused once a device has started pairing with it.
        if not p or time.time() > p.expires or msg.get("token") != p.token or p.device_id:
            await ws.send(json.dumps({"type": "pair_reject", "reason": "This pairing code expired. Create a new one on the laptop."}))
            await ws.close()
            return
        p.device_id = str(msg.get("device_id", ""))[:64] or str(uuid.uuid4())
        p.device_name = str(msg.get("device_name", "Phone"))[:60]
        p.code = sec.pairing_code(p.token, p.device_id)
        p.ws = ws
        self.on_event("pair_request", {"name": p.device_name, "code": p.code})
        await ws.send(json.dumps({"type": "pair_code", "code": p.code, "server_name": self.ident["name"]}))
        try:
            async for raw in ws:
                m = json.loads(raw)
                if m.get("type") == "pair_confirm":
                    p.phone_confirmed = True
                    await self._finish_pairing()
                elif m.get("type") == "pair_reject":
                    self.pending = None
                    self.on_event("pair_done", {"ok": False})
                    return
                if self.pending is None:
                    return
        except Exception:
            pass

    async def _dispatch(self, ws, device: Device, msg: dict):
        t = msg.get("type")
        if t == "ping":
            await ws.send('{"type":"pong"}')
        elif t == "status":
            device.status = msg.get("data") or {}
            self.on_event("device_status", device.public())
        elif t == "response":
            fut = self._waiters.pop(msg.get("id", ""), None)
            if fut and not fut.done():
                fut.set_result(msg)
        elif t == "request":
            asyncio.create_task(self._serve_request(ws, device, msg))
        elif t in ("file_offer", "file_chunk", "file_end", "file_cancel"):
            await self._receive_file(ws, device, msg)
        elif t in ("file_accept", "file_reject", "file_done"):
            key = f"{'done' if t == 'file_done' else 'answer'}:{msg.get('id')}"
            fut = self._waiters.pop(key, None)
            if fut and not fut.done():
                fut.set_result(msg)

    async def _serve_request(self, ws, device: Device, msg: dict):
        action = msg.get("action")
        params = msg.get("params") or {}
        if action not in ACTIONS:
            result = {"outcome": "NOT_SUPPORTED", "message": f"Unknown action {action}."}
        else:
            result = await self.loop.run_in_executor(None, self.handle_request, action, params, device)
        await ws.send(json.dumps({"type": "response", "id": msg.get("id"), **result}))

    # ------------------------------------------------------------------ file receive
    async def _receive_file(self, ws, device: Device, msg: dict):
        t, fid = msg["type"], msg.get("id", "")
        if t == "file_offer":
            name = Path(str(msg.get("name", ""))).name.strip()
            size = int(msg.get("size", 0))
            limit = int(settings.get("max_receive_mb")) * 1_000_000
            if not name or name in (".", "..") or size <= 0 or size > limit:
                await ws.send(json.dumps({"type": "file_reject", "id": fid, "reason": "Invalid name or too large."}))
                return
            folder = Path(settings.get("receive_dir"))
            folder.mkdir(parents=True, exist_ok=True)
            tmp = folder / f".{fid}.part"
            self._incoming[fid] = {"name": name, "size": size, "sha": msg.get("sha256", ""), "tmp": tmp,
                                   "fh": open(tmp, "wb"), "hash": hashlib.sha256(), "got": 0, "folder": folder}
            await ws.send(json.dumps({"type": "file_accept", "id": fid}))
            self.on_event("file_progress", {"id": fid, "name": name, "direction": "in", "done": 0, "size": size, "device": device.name})
        elif t == "file_chunk" and fid in self._incoming:
            st = self._incoming[fid]
            data = base64.b64decode(msg.get("data", ""))
            st["fh"].write(data)
            st["hash"].update(data)
            st["got"] += len(data)
            if st["got"] > st["size"]:
                await self._abort_in(ws, fid, "More data than offered.")
                return
            self.on_event("file_progress", {"id": fid, "name": st["name"], "direction": "in", "done": st["got"], "size": st["size"], "device": device.name})
        elif t == "file_end" and fid in self._incoming:
            st = self._incoming.pop(fid)
            st["fh"].close()
            if st["hash"].hexdigest() != st["sha"] or st["got"] != st["size"]:
                st["tmp"].unlink(missing_ok=True)
                await ws.send(json.dumps({"type": "file_done", "id": fid, "ok": False, "reason": "Integrity check failed."}))
                self.on_event("file_done", {"id": fid, "ok": False, "name": st["name"], "direction": "in"})
                return
            target = st["folder"] / st["name"]
            i = 1
            while target.exists():
                target = st["folder"] / f"{Path(st['name']).stem} ({i}){Path(st['name']).suffix}"
                i += 1
            st["tmp"].replace(target)
            await ws.send(json.dumps({"type": "file_done", "id": fid, "ok": True, "path": str(target)}))
            self.on_event("file_done", {"id": fid, "ok": True, "name": target.name, "path": str(target), "direction": "in", "device": device.name})
        elif t == "file_cancel" and fid in self._incoming:
            await self._abort_in(ws, fid, "Cancelled.")

    async def _abort_in(self, ws, fid, reason):
        st = self._incoming.pop(fid, None)
        if st:
            st["fh"].close()
            st["tmp"].unlink(missing_ok=True)
            self.on_event("file_done", {"id": fid, "ok": False, "name": st["name"], "direction": "in", "reason": reason})

    # ------------------------------------------------------------------ outgoing (called from other threads)
    def phone(self) -> Device | None:
        online = [d for d in self.devices.values() if d.online]
        return online[0] if online else (next(iter(self.devices.values()), None))

    def request(self, action: str, params: dict, device: Device | None = None, timeout: float = 20) -> dict:
        device = device or self.phone()
        if not device:
            return {"outcome": "DEVICE_OFFLINE", "message": "No phone is paired yet. Say pair my phone to connect one."}
        ws = self._sockets.get(device.device_id)
        if not ws:
            return {"outcome": "DEVICE_OFFLINE", "message": f"Your {device.name} isn't connected right now. Open Freakyyy on the phone, on the same Wi-Fi."}
        fut = asyncio.run_coroutine_threadsafe(self._request(ws, action, params, timeout), self.loop)
        try:
            return fut.result(timeout + 2)
        except Exception:
            return {"outcome": "FAILED", "message": f"{device.name} didn't answer in time."}

    async def _request(self, ws, action, params, timeout):
        rid = str(uuid.uuid4())
        fut = self.loop.create_future()
        self._waiters[rid] = fut
        await ws.send(json.dumps({"type": "request", "id": rid, "action": action, "params": params}))
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._waiters.pop(rid, None)

    def send_file(self, path: Path, device: Device | None = None) -> dict:
        device = device or self.phone()
        ws = self._sockets.get(device.device_id) if device else None
        if not ws:
            return {"outcome": "DEVICE_OFFLINE", "message": "Your phone isn't connected."}
        fut = asyncio.run_coroutine_threadsafe(self._send_file(ws, device, path), self.loop)
        try:
            return fut.result(3600)
        except Exception as e:
            return {"outcome": "FAILED", "message": f"Transfer failed: {e}"}

    async def _send_file(self, ws, device, path: Path) -> dict:
        size = path.stat().st_size
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(1 << 20):
                h.update(chunk)
        fid = str(uuid.uuid4())
        answer = self.loop.create_future()
        done = self.loop.create_future()
        self._waiters[f"answer:{fid}"] = answer
        self._waiters[f"done:{fid}"] = done
        import mimetypes
        await ws.send(json.dumps({"type": "file_offer", "id": fid, "name": path.name, "size": size,
                                  "sha256": h.hexdigest(), "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream"}))
        reply = await asyncio.wait_for(answer, 60)
        if reply.get("type") != "file_accept":
            return {"outcome": "FAILED", "message": f"The phone declined the file: {reply.get('reason', '')}"}
        sent = 0
        with open(path, "rb") as f:
            seq = 0
            while chunk := f.read(192 * 1024):
                if fid in self._outgoing_cancel:
                    await ws.send(json.dumps({"type": "file_cancel", "id": fid}))
                    return {"outcome": "FAILED", "message": "Transfer cancelled."}
                await ws.send(json.dumps({"type": "file_chunk", "id": fid, "seq": seq, "data": base64.b64encode(chunk).decode()}))
                sent += len(chunk)
                seq += 1
                self.on_event("file_progress", {"id": fid, "name": path.name, "direction": "out", "done": sent, "size": size, "device": device.name})
        await ws.send(json.dumps({"type": "file_end", "id": fid}))
        result = await asyncio.wait_for(done, 120)
        ok = bool(result.get("ok"))
        self.on_event("file_done", {"id": fid, "ok": ok, "name": path.name, "direction": "out", "device": device.name})
        if ok:
            return {"outcome": "COMPLETED", "message": f"Sent {path.name} to your {device.name}. It's in Download/Freakyyy."}
        return {"outcome": "FAILED", "message": f"The phone rejected {path.name}: {result.get('reason', 'integrity check failed')}"}
