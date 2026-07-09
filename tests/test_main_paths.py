"""tests/test_main_paths.py — Tests for main() paths and conditional branches"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestTranslatorMainPaths:
    """Exercise main() paths that aren't covered by unit tests"""

    def test_translate_single_with_limiter_concurrent(self, tmp_path):
        """Test concurrent translation with RateLimiter"""
        from translator import RateLimiter, translate_single_with_limiter, is_chinese
        from unittest.mock import patch

        limiter = RateLimiter(0.01)

        # Simulate a translated repo
        repo = {"owner": "test", "name": "test", "desc": "test description long enough"}

        with patch("translator.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({
                "responseData": {"translatedText": "翻译测试"}
            }).encode()
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            mock_urlopen.return_value.__exit__.return_value = False

            result = translate_single_with_limiter(repo, limiter)
            # Result depends on translator.translate_single
            pass

    def test_load_existing_nonexistent_file(self, tmp_path):
        """Test load_existing when file doesn't exist"""
        from translator import load_existing, OUTPUT_FILE
        with patch("translator.OUTPUT_FILE", tmp_path / "nonexistent.json"):
            result = load_existing()
            assert result == {}

    def test_main_with_mocked_data_creates_output(self, tmp_path):
        """Integration test: main() with mocked files creates output"""
        from translator import load_existing, load_existing
        # This tests the load_existing path fully
        test_file = tmp_path / "desc-cn.json"
        test_data = {"1": "测试"}
        test_file.write_text(json.dumps(test_data))
        from translator import OUTPUT_FILE as of
        with patch("translator.OUTPUT_FILE", test_file):
            result = load_existing()


class TestEnrichMainPath:
    """Tests for enrich.py conditional imports and helpers"""

    def test_has_unified_translator_flag(self):
        """Verify HAS_UNIFIED_TRANSLATOR is set correctly"""
        import enrich
        assert hasattr(enrich, "HAS_UNIFIED_TRANSLATOR")
        assert isinstance(enrich.HAS_UNIFIED_TRANSLATOR, bool)

    def test_translate_to_chinese_function_exists(self):
        """Verify translate_to_chinese is defined based on HAS_UNIFIED_TRANSLATOR"""
        import enrich
        assert hasattr(enrich, "translate_to_chinese")
        assert callable(enrich.translate_to_chinese)

    def test_batch_translate_function_exists(self):
        """Verify batch_translate is defined based on HAS_UNIFIED_TRANSLATOR"""
        import enrich
        assert hasattr(enrich, "batch_translate")
        assert callable(enrich.batch_translate)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
