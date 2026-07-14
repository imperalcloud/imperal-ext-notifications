"""Tests for notifications get_preferences / set_preferences.

Gateway is mocked with the gw_mock fixture (httpx.MockTransport under the
hood, see tests/conftest.py) — no real network, no respx. Every test drives
the real handler functions in handlers.py against app.AUTH_GW.
"""
import json

import httpx
import pytest

import handlers as h

# make_ctx / gw_mock are pytest fixtures (see tests/conftest.py) — auto-injected
# by name into any test function below that declares them as parameters. No
# cross-module import needed, so collection is portable regardless of pytest
# rootdir.

UID = "imp_u_TEST"

SETTINGS_PATH = f"/v1/internal/users/{UID}/settings"
EXTENSIONS_PATH = f"/v1/users/{UID}/extensions"
SURFACES_PATH = f"/v1/internal/surfaces/{UID}"

DEFAULT_SETTINGS = {"settings": {"notifications": {"enabled": True, "default": ["bell"], "apps": {}}}}
DEFAULT_EXTENSIONS = {"extensions": [
    {"app_id": "mail", "name": "Mail", "has_access": True, "enabled": True},
    {"app_id": "sharelock-v2", "name": "Sharelock", "has_access": True, "enabled": True},
]}
SURFACES_NO_TELEGRAM = {"surfaces": ["panel", "email"]}
SURFACES_WITH_TELEGRAM = {"surfaces": ["panel", "email", "telegram"]}


def _mock_reads(gw_mock, settings=None, extensions=None, surfaces=None):
    gw_mock.get(SETTINGS_PATH, json=settings or DEFAULT_SETTINGS)
    gw_mock.get(EXTENSIONS_PATH, json=extensions or DEFAULT_EXTENSIONS)
    gw_mock.get(SURFACES_PATH, json=surfaces or SURFACES_NO_TELEGRAM)


# ─── get_preferences ──────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_get_preferences_returns_matrix_catalog_and_connected(make_ctx, gw_mock):
    _mock_reads(gw_mock)

    res = await h.fn_get_preferences(make_ctx(), h.EmptyParams())

    assert res.status == "success"
    assert res.data.enabled is True
    assert res.data.default == ["bell"]
    assert res.data.apps == {}
    assert res.data.connected_channels == ["bell", "email"]
    assert {c["app_id"] for c in res.data.apps_catalog} == {"mail", "sharelock-v2"}


@pytest.mark.asyncio
async def test_get_preferences_reports_telegram_connected_when_surface_linked(make_ctx, gw_mock):
    _mock_reads(gw_mock, surfaces=SURFACES_WITH_TELEGRAM)

    res = await h.fn_get_preferences(make_ctx(), h.EmptyParams())

    assert res.status == "success"
    assert res.data.connected_channels == ["bell", "email", "telegram"]


@pytest.mark.asyncio
async def test_get_preferences_uses_ctx_user_id_only_never_a_param(make_ctx, gw_mock):
    """No user_id can be smuggled in — the handler reads ctx.user.imperal_id and
    calls the gateway for THAT id, regardless of anything in params."""
    other_uid = "imp_u_OTHER"
    gw_mock.get(f"/v1/internal/users/{other_uid}/settings", json=DEFAULT_SETTINGS)
    gw_mock.get(f"/v1/users/{other_uid}/extensions", json=DEFAULT_EXTENSIONS)
    gw_mock.get(f"/v1/internal/surfaces/{other_uid}", json=SURFACES_NO_TELEGRAM)

    res = await h.fn_get_preferences(make_ctx(imperal_id=other_uid), h.EmptyParams())
    assert res.status == "success"


# ─── set_preferences ──────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_set_preferences_app_id_channels_patches_the_full_dict(make_ctx, gw_mock):
    _mock_reads(gw_mock)
    saved = {"enabled": True, "default": ["bell"], "apps": {"mail": ["email"]}}
    gw_mock.patch(SETTINGS_PATH, json={"settings": {"notifications": saved}})

    params = h.SetPreferencesParams(app_id="mail", channels=["email"])
    res = await h.fn_set_preferences(make_ctx(), params)

    assert res.status == "success"
    assert gw_mock.was_called("PATCH", SETTINGS_PATH)
    body = json.loads(gw_mock.last_request("PATCH", SETTINGS_PATH).content)
    # Full dict, not a partial patch: enabled + default + apps all present.
    assert body == {"notifications": {"enabled": True, "default": ["bell"], "apps": {"mail": ["email"]}}}
    assert res.data.apps == {"mail": ["email"]}
    assert res.data.changed == {"mail": ["email"]}


@pytest.mark.asyncio
async def test_set_preferences_empty_channels_mutes_the_app(make_ctx, gw_mock):
    _mock_reads(gw_mock)
    saved = {"enabled": True, "default": ["bell"], "apps": {"mail": []}}
    gw_mock.patch(SETTINGS_PATH, json={"settings": {"notifications": saved}})

    params = h.SetPreferencesParams(app_id="mail", channels=[])
    res = await h.fn_set_preferences(make_ctx(), params)

    assert res.status == "success"
    body = json.loads(gw_mock.last_request("PATCH", SETTINGS_PATH).content)
    assert body["notifications"]["apps"]["mail"] == []
    assert res.data.apps == {"mail": []}


@pytest.mark.asyncio
async def test_set_preferences_unknown_app_id_errors_and_lists_known_ids(make_ctx, gw_mock):
    _mock_reads(gw_mock)
    # No PATCH route registered — an unknown app_id must be rejected before any write.
    params = h.SetPreferencesParams(app_id="not-a-real-app", channels=["bell"])
    res = await h.fn_set_preferences(make_ctx(), params)

    assert res.status == "error"
    assert "unknown app" in res.error
    assert "mail" in res.error
    assert "sharelock-v2" in res.error
    assert "system" in res.error


@pytest.mark.asyncio
async def test_set_preferences_gateway_422_surfaces_as_error(make_ctx, gw_mock):
    _mock_reads(gw_mock)
    gw_mock.patch(SETTINGS_PATH, json={"detail": "invalid channel 'sms'"}, status=422)

    params = h.SetPreferencesParams(app_id="mail", channels=["sms"])
    res = await h.fn_set_preferences(make_ctx(), params)

    assert res.status == "error"
    assert "422" in res.error
    assert "invalid channel" in res.error


@pytest.mark.asyncio
async def test_set_preferences_telegram_not_linked_is_a_fact_not_a_block(make_ctx, gw_mock):
    _mock_reads(gw_mock, surfaces=SURFACES_NO_TELEGRAM)
    saved = {"enabled": True, "default": ["bell", "telegram"], "apps": {}}
    gw_mock.patch(SETTINGS_PATH, json={"settings": {"notifications": saved}})

    params = h.SetPreferencesParams(default_channels=["bell", "telegram"])
    res = await h.fn_set_preferences(make_ctx(), params)

    assert res.status == "success"  # saved regardless — routing to telegram is not a hard error
    assert res.data.changed["telegram_linked"] is False


@pytest.mark.asyncio
async def test_set_preferences_telegram_linked_no_warning_fact(make_ctx, gw_mock):
    _mock_reads(gw_mock, surfaces=SURFACES_WITH_TELEGRAM)
    saved = {"enabled": True, "default": ["bell", "telegram"], "apps": {}}
    gw_mock.patch(SETTINGS_PATH, json={"settings": {"notifications": saved}})

    params = h.SetPreferencesParams(default_channels=["bell", "telegram"])
    res = await h.fn_set_preferences(make_ctx(), params)

    assert res.status == "success"
    assert "telegram_linked" not in res.data.changed


@pytest.mark.asyncio
async def test_set_preferences_app_id_without_channels_errors(make_ctx, gw_mock):
    _mock_reads(gw_mock)
    params = h.SetPreferencesParams(app_id="mail")
    res = await h.fn_set_preferences(make_ctx(), params)

    assert res.status == "error"
    assert "channels is required" in res.error


@pytest.mark.asyncio
async def test_set_preferences_nothing_to_change_errors(make_ctx, gw_mock):
    _mock_reads(gw_mock)
    params = h.SetPreferencesParams()
    res = await h.fn_set_preferences(make_ctx(), params)

    assert res.status == "error"
    assert "nothing to change" in res.error


@pytest.mark.asyncio
async def test_set_preferences_global_switch_only(make_ctx, gw_mock):
    _mock_reads(gw_mock)
    saved = {"enabled": False, "default": ["bell"], "apps": {}}
    gw_mock.patch(SETTINGS_PATH, json={"settings": {"notifications": saved}})

    params = h.SetPreferencesParams(enabled=False)
    res = await h.fn_set_preferences(make_ctx(), params)

    assert res.status == "success"
    body = json.loads(gw_mock.last_request("PATCH", SETTINGS_PATH).content)
    assert body["notifications"]["enabled"] is False
    assert res.data.changed == {"enabled": False}


# ─── Gateway unreachable: never leak the internal URL/IP into the error ─ #

@pytest.mark.asyncio
async def test_get_preferences_gateway_unreachable_error_has_no_internal_url(make_ctx, gw_mock):
    gw_mock.error("GET", SETTINGS_PATH, httpx.ConnectError("boom"))

    res = await h.fn_get_preferences(make_ctx(), h.EmptyParams())

    assert res.status == "error"
    assert "104.224" not in res.error
    assert "http://" not in res.error
    assert "https://" not in res.error
    assert "gateway" in res.error.lower()


@pytest.mark.asyncio
async def test_set_preferences_gateway_unreachable_error_has_no_internal_url(make_ctx, gw_mock):
    _mock_reads(gw_mock)
    gw_mock.error("PATCH", SETTINGS_PATH, httpx.ConnectError("boom"))

    params = h.SetPreferencesParams(app_id="mail", channels=["email"])
    res = await h.fn_set_preferences(make_ctx(), params)

    assert res.status == "error"
    assert "104.224" not in res.error
    assert "http://" not in res.error
    assert "https://" not in res.error
    assert "gateway" in res.error.lower()


# ─── Security: no user_id in the write-surface ───────────────────────── #

def test_params_models_have_no_user_id_field():
    """Tools operate ONLY on ctx.user.imperal_id — a caller must never be able
    to pass a foreign user_id through params."""
    assert "user_id" not in h.EmptyParams.model_fields
    assert "user_id" not in h.SetPreferencesParams.model_fields
