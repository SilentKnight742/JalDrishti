from jaldrishti_workers.satellite import _credentials_configured


def test_satellite_credentials_are_absent_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    monkeypatch.delenv("EARTHDATA_USERNAME", raising=False)
    monkeypatch.delenv("EARTHDATA_PASSWORD", raising=False)
    monkeypatch.setenv("NETRC", str(tmp_path / "missing.netrc"))

    assert _credentials_configured() is False


def test_satellite_credentials_accept_token_without_exposing_it(monkeypatch, tmp_path):
    monkeypatch.setenv("EARTHDATA_TOKEN", "secret-token")
    monkeypatch.delenv("EARTHDATA_USERNAME", raising=False)
    monkeypatch.delenv("EARTHDATA_PASSWORD", raising=False)
    monkeypatch.setenv("NETRC", str(tmp_path / "missing.netrc"))

    assert _credentials_configured() is True
