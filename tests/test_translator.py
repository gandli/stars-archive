"""tests/test_translator.py — TDD tests for translator.py"""

import json
import sys
import os
import time
import re
import threading
from unittest.mock import patch, mock_open, MagicMock
from pathlib import Path

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from translator import (
    truncate,
    is_chinese,
    translate_single,
    load_existing,
    save_results,
    RateLimiter,
    translate_single_with_limiter,
    ENRICHED_FILE,
    OUTPUT_FILE,
    META_FILE,
    MAX_RETRIES,
)


class TestTruncate:
    """Tests for text truncation"""

    def test_truncate_empty(self):
        assert truncate("") == ""

    def test_truncate_long_text(self):
        text = "a" * 1000
        result = truncate(text, 500)
        assert len(result) == 500
        assert result.endswith("...")

    def test_truncate_short_text(self):
        text = "short"
        result = truncate(text, 500)
        assert result == "short"

    def test_truncate_exact_max(self):
        text = "a" * 500
        result = truncate(text, 500)
        assert result == text
        assert len(result) == 500


class TestIsChinese:
    """Tests for Chinese character detection"""

    def test_english_only(self):
        assert is_chinese("Hello World") is False

    def test_chinese_only(self):
        assert is_chinese("你好世界") is True

    def test_mixed(self):
        assert is_chinese("Hello 你好") is True

    def test_empty(self):
        assert is_chinese("") is False

    def test_special_chars(self):
        assert is_chinese("!@#$%^&*()") is False

    def test_numbers_only(self):
        assert is_chinese("12345") is False

    def test_emoji(self):
        assert is_chinese("😊🎉") is False


class TestTranslateSingle:
    """Tests for single-text translation (network-dependent, mock urlopen)"""

    @patch("translator.urlopen")
    def test_skip_short_text(self, mock_urlopen):
        """Texts < 10 chars should be skipped"""
        result = translate_single("short")
        assert result == ""
        mock_urlopen.assert_not_called()

    @patch("translator.urlopen")
    def test_skip_chinese(self, mock_urlopen):
        """Chinese text should be returned as-is (if long enough)"""
        result = translate_single("这是一个足够长的中文描述文本用于测试")
        assert result == "这是一个足够长的中文描述文本用于测试"
        mock_urlopen.assert_not_called()

    @patch("translator.urlopen")
    def test_skip_empty(self, mock_urlopen):
        """Empty text should return empty"""
        result = translate_single("")
        assert result == ""
        mock_urlopen.assert_not_called()

    @patch("translator.urlopen")
    def test_successful_translation(self, mock_urlopen):
        """Mock successful API response"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "responseData": {"translatedText": "成功翻译"}
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = translate_single("Successful translation")
        assert result == "成功翻译"

    @patch("translator.urlopen")
    def test_retry_on_429(self, mock_urlopen):
        """Retry with backoff on 429"""
        from urllib.error import HTTPError

        fail_response = MagicMock()
        fail_response.read.return_value = b""
        fail_response.__enter__ = MagicMock(return_value=fail_response)
        fail_response.__exit__ = MagicMock(return_value=False)

        success_response = MagicMock()
        success_response.read.return_value = json.dumps({
            "responseData": {"translatedText": "重试成功"}
        }).encode()
        success_response.__enter__ = MagicMock(return_value=success_response)
        success_response.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [
            HTTPError("http://test", 429, "Rate limited", {}, None),
            success_response,
        ]

        result = translate_single("Retry after 429")
        assert result == "重试成功"
        assert mock_urlopen.call_count == 2

    @patch("translator.urlopen")
    def test_skip_duplicate_response(self, mock_urlopen):
        """If API returns original text (failed translation), return empty"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "responseData": {"translatedText": "Same input text"}
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = translate_single("Same input text")
        assert result == ""


class TestRateLimiter:
    """Tests for RateLimiter class"""

    def test_smoke(self):
        limiter = RateLimiter(0.1)
        limiter.wait()
        limiter.wait()

    def test_thread_safety(self):
        limiter = RateLimiter(0.05)
        errors = []

        def worker():
            try:
                limiter.wait()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

    def test_interval_enforced(self):
        """Ensure minimum interval between calls"""
        limiter = RateLimiter(0.1)
        start = time.time()
        limiter.wait()
        limiter.wait()
        elapsed = time.time() - start
        # Two waits with 0.1 interval should take at least 0.1s
        assert elapsed >= 0.09


class TestFileOps:
    """Tests for load/save file operations"""

    def test_load_existing_missing_file(self, tmp_path):
        test_output = tmp_path / "desc-cn.json"
        with patch("translator.OUTPUT_FILE", test_output):
            result = load_existing()
            assert result == {}

    def test_load_existing_file(self, tmp_path):
        mock_data = {"1": "翻译一", "2": "翻译二"}
        test_output = tmp_path / "desc-cn.json"
        test_output.write_text(json.dumps(mock_data))
        with patch("translator.OUTPUT_FILE", test_output):
            result = load_existing()
            assert result == mock_data

    def test_save_results_with_meta(self, tmp_path):
        test_output = tmp_path / "desc-cn.json"
        test_meta = tmp_path / "translation-meta.json"
        test_data = {"1": "翻译"}
        meta_data = {"total": 1}

        with patch("translator.OUTPUT_FILE", test_output):
            with patch("translator.META_FILE", test_meta):
                save_results(test_data, meta_data)

        assert json.loads(test_output.read_text()) == test_data
        assert json.loads(test_meta.read_text()) == meta_data

    def test_save_results_without_meta(self, tmp_path):
        test_output = tmp_path / "desc-cn.json"
        test_data = {"key": "value"}

        with patch("translator.OUTPUT_FILE", test_output):
            save_results(test_data)

        assert json.loads(test_output.read_text()) == test_data


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

