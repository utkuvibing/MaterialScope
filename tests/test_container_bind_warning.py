"""Track C (PR-5): bind-warning helper cases."""

from __future__ import annotations

import pytest

from backend.app import non_loopback_bind_warning

EXPECTED = (
    "MaterialScope is listening on 0.0.0.0 without an API token; it may be "
    "reachable from other hosts depending on the deployment network. "
    "Restart with --token to require X-TA-Token."
)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_loopback_binds_stay_quiet(host: str) -> None:
    assert non_loopback_bind_warning(host=host, api_token=None) is None


def test_non_loopback_bind_without_token_warns() -> None:
    assert non_loopback_bind_warning(host="0.0.0.0", api_token=None) == EXPECTED


def test_token_silences_warning() -> None:
    assert non_loopback_bind_warning(host="0.0.0.0", api_token="secret") is None


@pytest.mark.parametrize("host", ["", "example.com"])
def test_unparseable_or_remote_host_warns(host: str) -> None:
    warning = non_loopback_bind_warning(host=host, api_token=None)
    assert warning is not None
    assert "without an API token" in warning


def test_none_host_warns() -> None:
    assert non_loopback_bind_warning(host=None, api_token=None) is not None
