"""Notifications · Shared state — preference tools for the per-app routing matrix."""
from __future__ import annotations

import logging
import os

import httpx

from imperal_sdk import Extension
from imperal_sdk.chat import ChatExtension, ActionResult  # noqa: F401 (re-exported)

log = logging.getLogger("notifications")

AUTH_GW = os.getenv("IMPERAL_GATEWAY_URL", "http://104.224.88.155:8085")
AUTH_SERVICE_TOKEN = os.getenv("AUTH_SERVICE_TOKEN", "")

ext = Extension(
    "notifications", version="1.0.0", capabilities=[],
    display_name="Notifications",
    description=(
        "Notification preferences — choose where each app's notifications go "
        "(panel bell, Telegram, email), mute apps, or turn notifications off entirely."
    ),
    icon="icon.svg",
    actions_explicit=True,
    system=True,  # Imperal-owned platform app — always accessible, no explicit install.
)
# hidden_in_sidebar: True is set by hand directly in imperal.json (federal
# I-EXT-MANIFEST-HIDDEN-SIDEBAR-SYSTEM-ONLY) — the SDK Extension ctor does not
# expose this flag and `imperal build` does not carry it through the
# marketplace-fields merge, so it must be re-added after every `imperal build`.
# Chat tools/skeleton/lifecycle are unaffected; only the sidebar tile is
# suppressed (kernel's publish_hidden_in_sidebar_apps scan, honoured only
# when system=True — see imperal-ext-web-search/app.py for the same pattern).

chat = ChatExtension(
    ext,
    "tool_notifications_chat",
    description=(
        "Notification preferences — where each app's notifications are delivered: "
        "panel bell, Telegram, or email; per-app mute; global on/off."
    ),
    system_prompt=(
        "Notification preferences module. The user's matrix routes each app's "
        "notifications to channels: bell (panel), telegram (only when their "
        "Telegram is linked), email.\n\n"
        "get_preferences shows the current matrix, the user's apps, and which "
        "channels are actually connected. set_preferences changes ONE thing per "
        "call: the global switch, the default row, or one app's channels "
        "(empty channels list = mute that app).\n\n"
        "If the user routes to telegram while it is not linked, the change is "
        "saved but tell them delivery starts only after they connect Telegram "
        "(panel composer menu -> Connect Telegram)."
    ),
)


def _user_id(ctx) -> str:
    # ALWAYS the acting user — these tools never accept a foreign user_id.
    return ctx.user.imperal_id


def _headers() -> dict:
    return {"X-Service-Token": AUTH_SERVICE_TOKEN}


async def gw_get(path: str) -> dict:
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.get(f"{AUTH_GW}{path}", headers=_headers())
        r.raise_for_status()
        return r.json()


async def gw_patch(path: str, body: dict) -> tuple[dict | None, str | None]:
    """Returns (json, None) on success, (None, readable_error) on 4xx/5xx."""
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.patch(f"{AUTH_GW}{path}", json=body, headers=_headers())
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail") or r.text[:300]
            except Exception:
                detail = r.text[:300] or "(empty body)"
            return None, f"HTTP {r.status_code}: {detail}"
        return r.json(), None


@ext.health_check
async def health(ctx) -> dict:
    return {"status": "ok", "version": ext.version}


def _safe_err(e: Exception) -> str:
    """Never let an internal gateway URL/IP leak into a chat-facing error.

    httpx exceptions (and anything else that happens to embed a URL) get
    collapsed to a generic label; everything else is passed through as-is."""
    s = str(e)
    return "internal error" if "http" in s.lower() and "://" in s else s
