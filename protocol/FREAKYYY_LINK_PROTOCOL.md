# Freakyyy Link Protocol v1

Freakyyy Link connects **Freakyyy Desktop** (Windows, server) and **Freakyyy Mobile** (Android, client) on the local network. It is a typed JSON protocol over a TLS WebSocket. There is no cloud relay and no remote shell.

## Transport

| | |
|---|---|
| Server | Freakyyy Desktop, `wss://<lan-ip>:47800/link` (port configurable) |
| TLS | Self-signed ECDSA P-256 certificate created on first run and stored in `%APPDATA%\Freakyyy\link\`. The phone **pins** its SHA-256 fingerprint, which it learns from the QR code. It doesn't use any certificate authority. |
| Bind | The server listens on all private interfaces. It refuses non-private peer addresses (anything other than RFC 1918, link-local or loopback) unless the user changes this in Settings. |
| Frames | Text frames, UTF-8 JSON, one object per frame, max 1 MiB. File data travels in base64 `file_chunk` frames. |

## Pairing (one time)

1. On the desktop, choose **Add device**. The desktop generates a 32-byte random `token`, valid for 5 minutes and usable once, and shows a QR code containing:
   ```
   freakyyylink://pair?d=<base64url(JSON)>
   JSON = {"v":1,"name":"<PC name>","hosts":["192.168.1.20",...],"port":47800,
           "fp":"<sha256 hex of server cert DER>","token":"<base64url>"}
   ```
2. The phone scans the code, or the user pastes the link. It connects to each host in turn, pinning `fp`.
3. The phone sends:
   `{"type":"pair_request","token":"…","device_id":"<uuid>","device_name":"vivo X200 FE","platform":"android"}`
4. Both screens show the same **6-digit code**: `HMAC-SHA256(token, device_id)` → first 4 bytes → mod 1 000 000. Desktop and phone each ask the user to confirm. On desktop, saying "yes" works too.
5. The phone sends `{"type":"pair_confirm"}` once its user accepts. The desktop replies after its own user accepts:
   `{"type":"pair_ok","device_secret":"<base64url 32 bytes>","server_id":"<uuid>","server_name":"…"}`
   Either side can send `{"type":"pair_reject"}` instead.
6. Both sides store `device_secret`: Windows Credential Manager on desktop, Android Keystore-encrypted storage on the phone. The token is then discarded.

## Session authentication (every connection)

```
S → C  {"type":"challenge","nonce":"<b64 32B>","server_id":"…"}
C → S  {"type":"auth","device_id":"…","proof":HMAC(secret,"client|"+nonce+"|"+device_id),"nonce":"<b64 32B>"}
S → C  {"type":"auth_ok","proof":HMAC(secret,"server|"+client_nonce+"|"+server_id),"server_name":"…"}
```

Both sides authenticate each other, on top of the pinned TLS. Until `auth_ok` arrives, every other message is rejected and the socket closes after 10 seconds.

## Requests

```json
{"type":"request","id":"<uuid>","action":"<action>","params":{...}}
{"type":"response","id":"<same>","outcome":"COMPLETED","message":"Flashlight on.","data":{...},"confirm_token":null}
```

`outcome` is one of `COMPLETED`, `OPENED`, `INFO`, `NEEDS_PERMISSION`, `NEEDS_CONFIRMATION`, `NOT_SUPPORTED`, `FAILED`, `DEVICE_OFFLINE`.

### Actions (allow-list; anything else gets `NOT_SUPPORTED`)

| action | params | Executes |
|---|---|---|
| `run_command` | `text` (≤ 300 chars) | The **target's own deterministic command engine**. This is the same engine used for local voice commands. It is never a shell, and the target applies its own permission and confirmation rules. |
| `confirm` | `confirm_token`, `accept: bool` | Answers a `NEEDS_CONFIRMATION` that the target returned earlier. Tokens are single-use and expire after 60 seconds. |
| `get_status` | – | Returns battery, charging, storage and the device's capabilities (desktop also returns CPU, RAM and disk). |
| `open_url` | `url` (http/https only) | Opens the URL in the default browser. |
| `ring` | `seconds` (≤ 30) | Find my device: plays a loud tone and flashes the screen. |
| `clipboard_push` | `text` (≤ 100 kB) | Puts the text on the target's clipboard. This needs "Accept clipboard from paired devices" turned on at the target. |
| `clipboard_pull` | – | Returns the target's clipboard text. This needs "Allow paired devices to read my clipboard" turned on at the target (**off by default**). |
| `notify` | `title`, `text` | Shows a notification on the target. |
| `routine_run` | `name` | Runs the named routine on the target. |

### File transfer

```
offer  {"type":"file_offer","id","name","size","sha256","mime"}
reply  {"type":"file_accept","id"} | {"type":"file_reject","id","reason"}
data   {"type":"file_chunk","id","seq",data:"<b64 ≤ 192 KiB>"}  …  {"type":"file_end","id"}
done   {"type":"file_done","id","ok":true|false,"path":"…","reason":"…"}
cancel {"type":"file_cancel","id"}   (either side, any time)
```

The receiver writes to a temporary file in its download folder (Desktop: `Downloads\Freakyyy`; Phone: `Download/Freakyyy`). It strips any path components from `name` and refuses names that are empty or reserved. It verifies the SHA-256 before renaming the file into place. The size limit is set at the receiver (default 2 GiB).

### Events (no response expected)

`{"type":"status","data":{...}}` is sent every 60 seconds and whenever something changes. Each side also sends `{"type":"ping"}`/`{"type":"pong"}` every 20 seconds, and treats the connection as offline after 2 missed pongs.

## Security properties

- The server never accepts an unauthenticated control message.
- Remote input can only produce allow-listed actions. `run_command` text goes through the same parser as local speech, so it can't do anything a spoken command can't.
- The device where the change happens always asks for confirmation of destructive or sensitive operations. The question goes back to the requester (`NEEDS_CONFIRMATION` + `confirm_token`) and is answered by voice there.
- Either device can remove a pairing at any time. Doing so deletes the secret on that side, and the other side's next login attempt fails.
