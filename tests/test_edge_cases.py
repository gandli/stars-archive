"""tests/test_edge_cases.py — Edge case tests for stars-archive"""

import json
import sys
import os
import time
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from translator import (
    truncate, is_chinese, RateLimiter,
    load_existing, save_results, MAX_RETRIES, MAX_WORKERS, DEFAULT_RATE_LIMIT
)
from enrich import get_lang_category, extract_auto_tags, enrich_repo


class TestEdgeCasesTruncate:
    def test_none_input(self):
        assert truncate(None) == ""

    def test_unicode_truncation(self):
        text = "中" * 1000
        result = truncate(text, 100)
        assert len(result) == 100
        assert result.endswith("...")


class TestEdgeCasesIsChinese:
    def test_japanese_kanji(self):
        assert is_chinese("日本語") is True

    def test_korean(self):
        assert is_chinese("한국어") is False

    def test_single_chinese_char(self):
        assert is_chinese("中") is True


class TestEdgeCasesRateLimiter:
    def test_zero_interval(self):
        limiter = RateLimiter(0)
        start = time.time()
        limiter.wait()
        limiter.wait()
        elapsed = time.time() - start
        assert elapsed < 0.1

    def test_high_concurrency(self):
        limiter = RateLimiter(0.01)
        errors = []

        def worker():
            try:
                for _ in range(5):
                    limiter.wait()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors


class TestEdgeCasesFileOps:
    def test_save_results_empty_dict(self, tmp_path):
        test_output = tmp_path / "desc-cn.json"
        with patch("translator.OUTPUT_FILE", test_output):
            save_results({})
        assert json.loads(test_output.read_text()) == {}

    def test_save_results_unicode(self, tmp_path):
        test_output = tmp_path / "desc-cn.json"
        data = {"1": "中文 🦞 emoji"}
        with patch("translator.OUTPUT_FILE", test_output):
            save_results(data)
        result = json.loads(test_output.read_text())
        assert result == data

    def test_load_corrupted_json(self, tmp_path):
        test_output = tmp_path / "desc-cn.json"
        test_output.write_text("{invalid json")
        with patch("translator.OUTPUT_FILE", test_output):
            try:
                load_existing()
                assert False, "Should have raised"
            except json.JSONDecodeError:
                pass


class TestConstants:
    def test_max_workers_positive(self):
        assert MAX_WORKERS > 0

    def test_rate_limit_non_negative(self):
        assert DEFAULT_RATE_LIMIT >= 0

    def test_max_retries_reasonable(self):
        assert 1 <= MAX_RETRIES <= 5


class TestEnrichRepo:
    """Tests for enrich_repo function"""

    def test_basic_enrichment(self):
        repo = {
            "id": 12345,
            "name": "test/test-repo",
            "desc": "A machine learning framework",
            "stars": 100,
            "lang": "Python",
            "topics": ["pytorch", "deep-learning"],
        }
        enriched = enrich_repo(repo)
        assert enriched["id"] == 12345
        assert enriched["name"] == "test/test-repo"
        assert "lang_category" in enriched
        assert "auto_tags" in enriched

    def test_chinese_desc_preserved(self):
        repo = {
            "id": 999,
            "name": "cn/cn-repo",
            "desc": "中文描述",
            "stars": 50,
            "lang": "",
            "topics": [],
        }
        enriched = enrich_repo(repo)
        assert enriched["desc_cn"] == "中文描述"

    def test_english_desc_pending(self):
        repo = {
            "id": 888,
            "name": "en/en-repo",
            "desc": "An awesome English description",
            "stars": 50,
            "lang": "",
            "topics": [],
        }
        enriched = enrich_repo(repo)
        # English-only descs get None in non-translator path
        assert enriched.get("desc_cn") is None


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
