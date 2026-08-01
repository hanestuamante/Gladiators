"""Search provider selection — ultimate solution §16 P12.

Before this wiring the record/replay layer existed and nothing selected it:
``mode=record`` looked configured and recorded nothing. That is the same
dark-component failure the shadow wiring fixed for routing, and just as
invisible — the config read correctly, the tests passed, and no cassette was
ever written by the running system.
"""
from __future__ import annotations

import pytest

from gladiators.external.record_replay import (
    RecordingSearchProvider,
    ReplaySearchProvider,
)
from gladiators.external.settings import LiveSearchSettings
from gladiators.runtime_factory import _search_provider


def settings(mode: str, tmp_path=None) -> LiveSearchSettings:
    payload = {"enabled": True, "mode": mode}
    if tmp_path is not None:
        payload["cassette_dir"] = str(tmp_path)
    return LiveSearchSettings.model_validate(payload)


def test_replay_mode_selects_the_replay_provider(tmp_path):
    provider = _search_provider(settings("replay", tmp_path))
    assert isinstance(provider, ReplaySearchProvider)


def test_replay_mode_constructs_no_live_provider(tmp_path):
    """Structural: with nothing to fall back to, a miss cannot reach out."""
    provider = _search_provider(settings("replay", tmp_path))
    assert not hasattr(provider, "inner")


def test_cache_only_mode_selects_no_provider(tmp_path):
    assert _search_provider(settings("cache_only", tmp_path)) is None


def test_record_mode_wraps_a_live_provider(tmp_path, monkeypatch):
    class StubTavily:
        provider_id = "tavily"

    monkeypatch.setattr("gladiators.runtime_factory.TavilyProvider", StubTavily)
    provider = _search_provider(settings("record", tmp_path))
    assert isinstance(provider, RecordingSearchProvider)
    assert isinstance(provider.inner, StubTavily)


def test_live_mode_uses_the_provider_directly(tmp_path, monkeypatch):
    class StubTavily:
        provider_id = "tavily"

    monkeypatch.setattr("gladiators.runtime_factory.TavilyProvider", StubTavily)
    provider = _search_provider(settings("live", tmp_path))
    assert isinstance(provider, StubTavily)


def test_cassette_dir_from_settings_is_honoured(tmp_path):
    provider = _search_provider(settings("replay", tmp_path))
    assert provider.store.root == tmp_path


def test_replay_is_an_accepted_configuration_value():
    """It has to be a real mode, or a config file naming it fails validation."""
    assert LiveSearchSettings.model_validate({"mode": "replay"}).mode == "replay"


def test_an_unknown_mode_is_rejected_by_the_settings_contract():
    with pytest.raises(Exception):
        LiveSearchSettings.model_validate({"mode": "sometimes"})
