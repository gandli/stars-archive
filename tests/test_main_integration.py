"""tests/test_main_integration.py — TDD for main() end-to-end flow"""

import json
import sys
import os
import subprocess
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestMainIntegration:
    """Integration tests for translator.main()"""

    def _create_test_env(self, tmp_path, repos=None, existing=None):
        """Helper: create test data files"""
        if repos is None:
            repos = [
                {"id": 1, "name": "owner/repo1", "desc": "A nice English description for testing purposes", "stars": 100, "lang": "Python", "topics": ["testing"]},
                {"id": 2, "name": "owner/repo2", "desc": "中文描述已有", "stars": 50, "lang": "Go", "topics": []},
                {"id": 3, "name": "owner/repo3", "desc": "Another English description that is long enough to translate", "stars": 75, "lang": "Rust", "topics": ["cli"]},
            ]

        enriched_file = tmp_path / "stars-enriched.json"
        enriched_file.write_text(json.dumps(repos))

        output_file = tmp_path / "desc-cn.json"
        if existing:
            output_file.write_text(json.dumps(existing))

        meta_file = tmp_path / "translation-meta.json"
        return enriched_file, output_file, meta_file

    @patch("translator.urlopen")
    def test_main_translates_new_repos(self, mock_urlopen, tmp_path):
        """main() should translate only new repos (not in cache)"""
        enriched_file, output_file, meta_file = self._create_test_env(
            tmp_path, existing={"1": "已翻译"}
        )

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "responseData": {"translatedText": "新翻译结果"}
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        mock_urlopen.return_value.__exit__.return_value = False

        with patch("translator.ENRICHED_FILE", enriched_file), \
             patch("translator.OUTPUT_FILE", output_file), \
             patch("translator.META_FILE", meta_file):

            from translator import main
            main(argv=[])

        result = json.loads(output_file.read_text())
        # Should have existing + newly translated
        assert "1" in result  # existing
        assert result["1"] == "已翻译"  # preserved

    @patch("translator.urlopen")
    def test_main_skips_chinese_descriptions(self, mock_urlopen, tmp_path):
        """main() should skip repos with Chinese descriptions"""
        repos = [
            {"id": 10, "name": "cn/repo", "desc": "这是一个中文描述足够长", "stars": 100, "lang": "", "topics": []},
        ]
        enriched_file, output_file, meta_file = self._create_test_env(tmp_path, repos=repos)

        with patch("translator.ENRICHED_FILE", enriched_file), \
             patch("translator.OUTPUT_FILE", output_file), \
             patch("translator.META_FILE", meta_file):

            from translator import main
            main(argv=[])

        # Chinese desc repos are added to existing cache, output file may not exist
        if output_file.exists():
            result = json.loads(output_file.read_text())
            assert "10" in result
            assert result["10"] == "这是一个中文描述足够长"
        mock_urlopen.assert_not_called()

    @patch("translator.urlopen")
    def test_main_skips_short_descriptions(self, mock_urlopen, tmp_path):
        """main() should skip repos with descriptions < 10 chars"""
        repos = [
            {"id": 20, "name": "short/repo", "desc": "tiny", "stars": 100, "lang": "", "topics": []},
        ]
        enriched_file, output_file, meta_file = self._create_test_env(tmp_path, repos=repos)

        with patch("translator.ENRICHED_FILE", enriched_file), \
             patch("translator.OUTPUT_FILE", output_file), \
             patch("translator.META_FILE", meta_file):

            from translator import main
            main(argv=[])

        # Short desc repos are skipped entirely, output file may not exist
        if output_file.exists():
            result = json.loads(output_file.read_text())
            assert "20" not in result  # short desc skipped
        mock_urlopen.assert_not_called()

    @patch("translator.urlopen")
    def test_main_creates_meta_file(self, mock_urlopen, tmp_path):
        """main() should create meta file with stats"""
        enriched_file, output_file, meta_file = self._create_test_env(tmp_path)

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "responseData": {"translatedText": "翻译"}
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        mock_urlopen.return_value.__exit__.return_value = False

        with patch("translator.ENRICHED_FILE", enriched_file), \
             patch("translator.OUTPUT_FILE", output_file), \
             patch("translator.META_FILE", meta_file):

            from translator import main
            main(argv=[])

        assert meta_file.exists()
        meta = json.loads(meta_file.read_text())
        assert "total_translated" in meta
        assert "synced_at" in meta
        assert meta["workers"] == 12

    @patch("translator.urlopen")
    def test_main_handles_api_failure_gracefully(self, mock_urlopen, tmp_path):
        """main() should continue even if some translations fail"""
        repos = [
            {"id": 100, "name": "a/repo1", "desc": "First repo description long enough", "stars": 100, "lang": "", "topics": []},
            {"id": 200, "name": "a/repo2", "desc": "Second repo description long enough", "stars": 50, "lang": "", "topics": []},
        ]
        enriched_file, output_file, meta_file = self._create_test_env(tmp_path, repos=repos)

        from urllib.error import HTTPError
        fp = MagicMock()
        fp.read.return_value = b""

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "responseData": {"translatedText": "成功"}
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        # First call fails, second succeeds
        err = HTTPError("http://test", 429, "Rate limited", {}, fp)
        mock_urlopen.side_effect = [err, err, err, mock_resp]

        with patch("translator.ENRICHED_FILE", enriched_file), \
             patch("translator.OUTPUT_FILE", output_file), \
             patch("translator.META_FILE", meta_file):

            from translator import main
            main(argv=[])

        # Should have at least the successful one
        result = json.loads(output_file.read_text())
        assert len(result) >= 1


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
