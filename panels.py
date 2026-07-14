"""Notifications · Panel — read-only snapshot of the notification matrix.

v1 is informational only: the write UI for notification preferences lives in
the platform Settings matrix (chat tools get_preferences/set_preferences also
cover writes). This panel exists so the extension has a registered UI surface
per the platform contract — it renders FACTS (global switch, default row,
per-app channels), no controls.

Hidden from the Imperal Panel sidebar tile via manifest `hidden_in_sidebar`
(system-only — see app.py); the panel itself still works, it is just never
offered as a clickable sidebar icon to end users.
"""
from __future__ import annotations

import logging

from imperal_sdk import ui

from app import ext, _user_id
from handlers import _load_state

log = logging.getLogger("notifications")

_CHANNEL_COLOR = {"bell": "blue", "telegram": "green", "email": "yellow"}


def _channel_badges(channels: list[str] | None) -> ui.Stack:
    """Render a channel list as colored badges, or a 'Muted' badge if empty."""
    if not channels:
        return ui.Stack(direction="h", gap=1, children=[ui.Badge(label="Muted", color="gray")])
    return ui.Stack(direction="h", gap=1, children=[
        ui.Badge(label=c.title(), color=_CHANNEL_COLOR.get(c, "gray")) for c in channels
    ])


@ext.panel(
    "preferences", slot="left", title="Notification preferences", icon="Bell",
    refresh="manual",
)
async def notifications_preferences_panel(ctx, **kwargs):
    """Read-only view of the user's notification routing matrix.

    Shows the global on/off switch, connected delivery channels, the default
    row (channels used by apps without their own override), and one row per
    app the user has access to with its effective channels. No write controls
    — preference changes go through the get_preferences/set_preferences chat
    tools or the platform Settings matrix.
    """
    uid = _user_id(ctx)
    try:
        prefs, catalog, connected = await _load_state(uid)
    except Exception as e:
        log.error("preferences panel load error: %s", e)
        return ui.Stack(children=[
            ui.Alert(message="Could not load notification preferences — try again shortly", type="error"),
        ])

    enabled = prefs.get("enabled", True)
    default = prefs.get("default", ["bell"])
    apps = prefs.get("apps", {})

    children = [
        ui.Card(
            title="Global",
            content=ui.Stack(children=[
                ui.Stat(label="Notifications", value="Enabled" if enabled else "Disabled",
                        color="green" if enabled else "red"),
                ui.KeyValue(items=[
                    {"key": "Connected channels", "value": ", ".join(connected) or "none"},
                ]),
            ]),
        ),
        ui.Section(title="Default (apps without an override)",
                   children=[_channel_badges(default)]),
    ]

    if catalog:
        app_rows = [
            ui.ListItem(
                id=entry["app_id"],
                title=entry.get("name") or entry["app_id"],
                subtitle=", ".join(apps.get(entry["app_id"], default)) or "muted",
            )
            for entry in catalog
        ]
        children.append(ui.Section(title="Per-app channels", children=[ui.List(items=app_rows)]))

    return ui.Stack(direction="v", gap=2, children=children)


__all__ = ["notifications_preferences_panel"]
