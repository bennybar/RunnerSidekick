"""Connecting Garmin from the phone. The runner signs in on Garmin's own page inside the app (password and two-factor
codes go only to Garmin, from the phone's address, so the server never hits Garmin's sign-in limits). Garmin answers
with a one-time service ticket; the app sends just that here, and the server exchanges it for Garmin's long-lived
tokens (renewed without signing in again), stored in the user's own folder. One Garmin account per app user."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

SSO_EMBED = "https://sso.garmin.com/sso/embed"  # the service the app's sign-in page asks a ticket for
TOKEN_FILE = "garmin_tokens.json"
ACCOUNT_FILE = "garmin_account.json"  # which Garmin account these tokens are for (its profile id), never a secret


class LinkError(Exception):
    """A message fit to show the runner."""


def linked(token_dir: Path) -> bool:
    return (token_dir / TOKEN_FILE).exists()


def profile_of(token_dir: Path) -> int | None:
    try:
        return json.loads((token_dir / ACCOUNT_FILE).read_text()).get("profile_id")
    except (OSError, ValueError):
        return None


def users_with(users_root: Path, profile_id: int) -> list[int]:
    """App users whose stored Garmin tokens are for this Garmin account."""
    out = []
    for d in users_root.glob("*/garmin_tokens"):
        if d.parent.name.isdigit() and profile_of(d) == profile_id:
            out.append(int(d.parent.name))
    return out


def link(token_dir: Path, ticket: str, users_root: Path, user_id: int, client_factory=None) -> dict:
    """Exchanges the ticket and stores the tokens for user_id. Refuses a Garmin account already linked to another user.
    Tokens are written to a temporary folder first, so a failed or refused link never replaces a working one."""
    if client_factory is None:
        from garminconnect import Garmin as client_factory
    token_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".garmin-link-", dir=token_dir.parent))  # same disk: the final move is a rename
    try:
        api = client_factory()
        try:
            api.client._exchange_service_ticket(ticket, service_url=SSO_EMBED)
            api.client.dump(str(tmp))
            api = client_factory()
            api.login(tokenstore=str(tmp))  # loads the tokens and reads the profile, as every sync will
        except Exception as e:  # a used or expired ticket, or Garmin unreachable: a message, never the ticket
            name = type(e).__name__
            if "TooManyRequests" in name:
                raise LinkError("Garmin is busy right now. Please try again in a few minutes.") from e
            raise LinkError("Garmin didn't accept this sign-in (it may have expired). Please sign in again.") from e
        pid = getattr(api, "profile_id", None)
        if not isinstance(pid, int):
            raise LinkError("Garmin didn't say which account this is. Please try again.")
        if any(u != user_id for u in users_with(users_root, pid)):
            raise LinkError("This Garmin account is already connected to another Runner Sidekick account.")
        (tmp / ACCOUNT_FILE).write_text(json.dumps({"profile_id": pid, "display_name": getattr(api, "display_name", None)}))
        shutil.rmtree(token_dir, ignore_errors=True)
        tmp.rename(token_dir)
        token_dir.chmod(0o700)
        return {"profile_id": pid, "display_name": getattr(api, "display_name", None)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def unlink(token_dir: Path) -> bool:
    had = token_dir.exists()
    shutil.rmtree(token_dir, ignore_errors=True)
    return had
