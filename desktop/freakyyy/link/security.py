"""TLS identity and HMAC helpers for Freakyyy Link."""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import ssl
import uuid
from pathlib import Path

from ..config import DATA_DIR

LINK_DIR = DATA_DIR / "link"
LINK_DIR.mkdir(exist_ok=True)
CERT, KEY, IDENTITY = LINK_DIR / "cert.pem", LINK_DIR / "key.pem", LINK_DIR / "server.json"


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hmac_b64(secret: bytes, message: str) -> str:
    return b64(hmac.new(secret, message.encode(), hashlib.sha256).digest())


def verify(secret: bytes, message: str, proof: str) -> bool:
    return hmac.compare_digest(hmac_b64(secret, message), proof or "")


def pairing_code(token: str, device_id: str) -> str:
    digest = hmac.new(unb64(token), device_id.encode(), hashlib.sha256).digest()
    return f"{int.from_bytes(digest[:4], 'big') % 1_000_000:06d}"


def server_identity() -> dict:
    if IDENTITY.exists():
        return json.loads(IDENTITY.read_text())
    ident = {"server_id": str(uuid.uuid4()), "name": socket.gethostname()}
    IDENTITY.write_text(json.dumps(ident))
    return ident


def local_ips() -> list[str]:
    ips = []
    try:
        import psutil
        for name, addrs in psutil.net_if_addrs().items():
            stats = psutil.net_if_stats().get(name)
            if stats and not stats.isup:
                continue
            for a in addrs:
                if a.family == socket.AF_INET:
                    ip = ipaddress.ip_address(a.address)
                    if ip.is_private and not ip.is_loopback and not str(ip).startswith("169.254"):
                        ips.append(a.address)
    except Exception:
        pass
    # The interface with the default route first.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        primary = s.getsockname()[0]
        s.close()
        if primary in ips:
            ips.remove(primary)
        ips.insert(0, primary)
    except Exception:
        pass
    return list(dict.fromkeys(ips))


def ensure_certificate() -> None:
    if CERT.exists() and KEY.exists():
        return
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Freakyyy Desktop")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("freakyyy.local"), x509.DNSName("localhost")]), False)
            .sign(key, hashes.SHA256()))
    KEY.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    try:
        os.chmod(KEY, 0o600)
    except Exception:
        pass


def fingerprint() -> str:
    der = ssl.PEM_cert_to_DER_cert(CERT.read_text())
    return hashlib.sha256(der).hexdigest()


def ssl_context() -> ssl.SSLContext:
    ensure_certificate()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(CERT, KEY)
    return ctx


def new_token() -> str:
    return b64(secrets.token_bytes(32))


def new_secret() -> bytes:
    return secrets.token_bytes(32)


def is_allowed_peer(addr: str, allow_public: bool) -> bool:
    try:
        ip = ipaddress.ip_address(addr.split("%")[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return allow_public or ip.is_private or ip.is_loopback or ip.is_link_local
