"""tests/test_sync_token_validation.py — Regression tests for P0-02 fixes"""

import json
import os
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestValidateToken:
    """P0-02: Token pre-flight validation"""

    def test_missing_token_raises_token_error(self):
        from sync import validate_token, TokenError
        with patch("sync.get_env_token", return_value=""):
            try:
                validate_token()
                assert False, "Should have raised TokenError"
            except TokenError as e:
                assert "No GitHub token found" in str(e)

    def test_invalid_token_raises_token_error(self):
        from sync import validate_token, TokenError
        fp = MagicMock()
        fp.read.return_value = b""
        err = urllib.error.HTTPError("http://test", 401, "Unauthorized", {}, fp)
        with patch("sync.get_env_token", return_value="invalid"):
            with patch("urllib.request.urlopen", side_effect=err):
                try:
                    validate_token()
                    assert False
                except TokenError as e:
                    assert "invalid or expired" in str(e).lower() or "401" in str(e)

    def test_valid_token_passes(self):
        from sync import validate_token
        mock_ok = MagicMock()
        mock_ok.read.return_value = json.dumps({"login": "gandli"}).encode()
        mock_ok.__enter__ = MagicMock(return_value=mock_ok)
        mock_ok.__exit__ = MagicMock(return_value=False)
        with patch("sync.get_env_token", return_value="valid"):
            with patch("urllib.request.urlopen", return_value=mock_ok):
                validate_token()


class TestApiRequestRetry:
    """P0-02: 5xx retry logic"""

    def test_500_retries_once(self):
        from sync import api_request
        mock_ok = MagicMock()
        mock_ok.read.return_value = json.dumps({"ok": True}).encode()
        mock_ok.__enter__ = MagicMock(return_value=mock_ok)
        mock_ok.__exit__ = MagicMock(return_value=False)
        fp = MagicMock()
        fp.read.return_value = b""
        err = urllib.error.HTTPError("http://test", 500, "Server Error", {}, fp)
        with patch("sync.get_env_token", return_value="token"):
            with patch("urllib.request.urlopen", side_effect=[err, mock_ok]):
                with patch("time.sleep"):
                    result = api_request("http://test", retry_count=1)
                    assert result == {"ok": True}

    def test_401_raises_token_error(self):
        from sync import api_request, TokenError
        fp = MagicMock()
        fp.read.return_value = b'{"message": "Bad credentials"}'
        err = urllib.error.HTTPError("http://test", 401, "Unauthorized", {}, fp)
        with patch("sync.get_env_token", return_value="bad"):
            with patch("urllib.request.urlopen", side_effect=err):
                try:
                    api_request("http://test")
                    assert False
                except TokenError as e:
                    assert "401" in str(e) or "Invalid" in str(e)

    def test_403_rate_limit_raises_rate_limit_error(self):
        from sync import api_request, RateLimitError
        fp = MagicMock()
        fp.read.return_value = b'{"message": "API rate limit exceeded"}'
        err = urllib.error.HTTPError("http://test", 403, "Forbidden", {}, fp)
        with patch("sync.get_env_token", return_value="token"):
            with patch("urllib.request.urlopen", side_effect=err):
                try:
                    api_request("http://test")
                    assert False
                except RateLimitError as e:
                    assert "rate limit" in str(e).lower()


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
