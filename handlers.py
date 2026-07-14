"""Notifications · Chat function handlers — FACTS out, narrator phrases (ICNLI)."""
from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from app import ActionResult, chat, gw_get, gw_patch, _safe_err, _user_id
from models import NotificationPreferences

CHANNELS = ("bell", "telegram", "email")


class EmptyParams(BaseModel):
    """No parameters needed."""
    pass


class SetPreferencesParams(BaseModel):
    """Exactly ONE of: enabled (global switch) | default_channels (default row)
    | app_id+channels (one app's row; empty channels = mute that app)."""
    enabled: bool | None = Field(default=None, description="Global notifications switch")
    default_channels: list[str] | None = Field(
        default=None, description="Default row for apps without their own setting (bell/telegram/email)")
    app_id: str = Field(default="", description="App to change (e.g. mail, sharelock-v2, automations, system)")
    channels: list[str] | None = Field(
        default=None, description="Channels for app_id (subset of bell/telegram/email); [] mutes the app")


async def _load_state(uid: str) -> tuple[dict, list[dict], list[str]]:
    settings = (await gw_get(f"/v1/internal/users/{uid}/settings")).get("settings", {})
    prefs = settings.get("notifications") or {"enabled": True, "default": ["bell"], "apps": {}}
    exts = (await gw_get(f"/v1/users/{uid}/extensions")).get("extensions", [])
    catalog = [{"app_id": e["app_id"], "name": e.get("name") or e["app_id"]}
               for e in exts if e.get("has_access") is not False and e.get("enabled") is not False]
    surfaces = (await gw_get(f"/v1/internal/surfaces/{uid}")).get("surfaces", [])
    connected = ["bell", "email"] + (["telegram"] if "telegram" in surfaces else [])
    return prefs, catalog, connected


@chat.function(
    "get_preferences",
    action_type="read",
    description="Show the notification routing matrix: global switch, default row, per-app channels, connected channels.",
    data_model=NotificationPreferences,
)
async def fn_get_preferences(ctx, params: EmptyParams) -> ActionResult:
    """Show the acting user's notification routing matrix.

    No params — always reads the caller's own settings (``ctx.user.imperal_id``).

    Returns FACTS the narrator needs to explain the current setup in one
    call: the global on/off switch (``enabled``), the default channel row
    used by apps without their own override (``default``), any per-app
    overrides (``apps``, empty list = that app is muted), which channels are
    actually connected and can receive deliveries right now
    (``connected_channels`` — bell/email are always connected, telegram only
    once linked), and the user's installed apps for context
    (``apps_catalog``: ``[{app_id, name}]``).
    """
    try:
        uid = _user_id(ctx)
        prefs, catalog, connected = await _load_state(uid)
        return ActionResult.success(
            data=NotificationPreferences(
                enabled=prefs.get("enabled", True), default=prefs.get("default", ["bell"]),
                apps=prefs.get("apps", {}), connected_channels=connected, apps_catalog=catalog),
            summary=f"notifications enabled={prefs.get('enabled', True)}, "
                    f"default={prefs.get('default', ['bell'])}, "
                    f"{len(prefs.get('apps', {}))} app override(s)")
    except httpx.HTTPError:
        return ActionResult.error("Failed to reach the platform gateway — try again shortly")
    except Exception as e:
        return ActionResult.error(f"Failed to load notification preferences: {_safe_err(e)}")


@chat.function(
    "set_preferences",
    action_type="write",
    description="Change notification routing: global on/off, the default row, or one app's channels ([] = mute).",
    data_model=NotificationPreferences,
)
async def fn_set_preferences(ctx, params: SetPreferencesParams) -> ActionResult:
    """Change ONE part of the acting user's notification routing matrix.

    Exactly one of the following per call (mixing is allowed if the caller
    genuinely wants more than one field changed in the same write, but the
    common case is one intent per call):
    - ``enabled``: flip the global notifications switch on/off.
    - ``default_channels``: replace the default row — the channels used by
      apps that have no override of their own (subset of bell/telegram/email).
    - ``app_id`` + ``channels``: set one app's own channel row; ``channels=[]``
      mutes that app specifically (it stops following the default row).

    Always writes for ``ctx.user.imperal_id`` — never a caller-supplied user.
    Returns the same FACTS shape as get_preferences (post-write state) plus
    ``changed`` (the delta actually applied) and, when relevant,
    ``changed["telegram_linked"] = False`` if the save routed something to
    telegram while the user hasn't linked it yet (saved regardless — this is
    a FACT for the narrator, not a hard error).
    """
    try:
        uid = _user_id(ctx)
        prefs, catalog, connected = await _load_state(uid)
        changed: dict = {}
        if params.enabled is not None:
            prefs["enabled"] = params.enabled
            changed["enabled"] = params.enabled
        if params.default_channels is not None:
            prefs["default"] = params.default_channels
            changed["default"] = params.default_channels
        if params.app_id:
            if params.channels is None:
                return ActionResult.error("channels is required when app_id is given ([] mutes the app)")
            known = {c["app_id"] for c in catalog} | {"system"}
            if params.app_id not in known:
                return ActionResult.error(
                    f"unknown app '{params.app_id}'; known: {sorted(known)}")
            prefs.setdefault("apps", {})[params.app_id] = params.channels
            changed[params.app_id] = params.channels
        if not changed:
            return ActionResult.error("nothing to change: give enabled, default_channels, or app_id+channels")
        # Full-dict write — the gateway stores the subtree wholesale (replace_paths),
        # and validates channels/app ids authoritatively (422 -> surfaced below).
        body = {"notifications": {"enabled": prefs.get("enabled", True),
                                  "default": prefs.get("default", ["bell"]),
                                  "apps": prefs.get("apps", {})}}
        res, err = await gw_patch(f"/v1/internal/users/{uid}/settings", body)
        if err:
            return ActionResult.error(f"Preferences not saved: {err}")
        saved = (res.get("settings") or {}).get("notifications", body["notifications"])
        if "telegram" not in connected and any(
                "telegram" in v for v in ([saved.get("default", [])] + list(saved.get("apps", {}).values()))):
            changed["telegram_linked"] = False  # FACT: saved, but delivery needs linking
        return ActionResult.success(
            data=NotificationPreferences(
                enabled=saved.get("enabled", True), default=saved.get("default", ["bell"]),
                apps=saved.get("apps", {}), connected_channels=connected,
                apps_catalog=catalog, changed=changed),
            summary=f"notification preferences updated: {changed}")
    except httpx.HTTPError:
        return ActionResult.error("Preferences not saved: platform gateway unreachable — try again shortly")
    except Exception as e:
        return ActionResult.error(f"Failed to update notification preferences: {_safe_err(e)}")


__all__ = ["fn_get_preferences", "fn_set_preferences"]
