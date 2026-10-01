"""Device bearer tokens for the Android client. Only SHA-256 hashes are stored on disk."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

from .db import utc_now


def _path(data_dir: Path) -> Path:
    return data_dir / "device_tokens.json"


def _load(data_dir: Path) -> list[dict]:
    p = _path(data_dir)
    return json.loads(p.read_text()) if p.exists() else []


def _save(data_dir: Path, tokens: list[dict]) -> None:
    p = _path(data_dir)
    fd = os.open(p.with_suffix(".tmp"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(tokens, f, indent=1)
    os.replace(p.with_suffix(".tmp"), p)


def create_token(data_dir: Path, name: str) -> str:
    token = "rsk_" + secrets.token_urlsafe(32)
    tokens = _load(data_dir)
    tokens.append({"name": name, "sha256": hashlib.sha256(token.encode()).hexdigest(), "created_at": utc_now(), "revoked_at": None})
    _save(data_dir, tokens)
    return token


def revoke_token(data_dir: Path, name: str) -> int:
    tokens = _load(data_dir)
    n = 0
    for t in tokens:
        if t["name"] == name and not t["revoked_at"]:
            t["revoked_at"] = utc_now()
            n += 1
    _save(data_dir, tokens)
    return n


def verify_token(data_dir: Path, token: str) -> bool:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return any(hmac.compare_digest(t["sha256"], digest) and not t["revoked_at"] for t in _load(data_dir))
