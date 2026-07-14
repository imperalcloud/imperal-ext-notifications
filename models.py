"""Notifications · SDL return models."""
from __future__ import annotations

from typing import Any

from imperal_sdk import sdl
from pydantic import model_validator


class NotificationPreferences(sdl.Entity):
    """The user's notification routing matrix + surrounding FACTS.

    enabled/default/apps mirror user_settings.notifications verbatim;
    connected_channels/apps_catalog let the narrator explain what is possible
    without a second tool call."""
    enabled: bool | None = None
    default: list[str] | None = None
    apps: dict[str, Any] | None = None
    connected_channels: list[str] | None = None
    apps_catalog: list[dict] | None = None  # [{app_id, name}]
    changed: dict[str, Any] | None = None   # set_preferences only: the applied delta

    @model_validator(mode="before")
    @classmethod
    def _sdl_canon(cls, data):
        if isinstance(data, dict):
            data.setdefault("id", "notification-preferences")
            data.setdefault("title", "Notification preferences")
        return data
