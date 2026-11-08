"""What to tell the runner when a call to OpenAI fails, in words instead of an exception's name."""

from __future__ import annotations


def failure(e: Exception, key_source: str | None = "server") -> str:
    name = type(e).__name__
    whose = "Your OpenAI key" if key_source == "user" else "The server's OpenAI key"
    if name == "AuthenticationError":
        return f"{whose} was rejected (it may have expired, been revoked, or run out of credit)" + (
            ". Update it in Settings." if key_source == "user" else ". The server owner needs to set a new one.")
    if name == "PermissionDeniedError":
        return f"{whose} isn't allowed to use this model."
    if name == "RateLimitError":
        return "OpenAI is limiting requests right now (or the account is out of credit). Try again later."
    if name in ("APITimeoutError", "APIConnectionError", "TimeoutError"):
        return "Couldn't reach OpenAI. Try again in a moment."
    return f"The AI call failed ({name})."
