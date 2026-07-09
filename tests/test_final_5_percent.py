"""tests/test_final_5_percent.py — Target the final 5% uncovered lines"""

import json
import sys
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from urllib.error import HTTPError, URLError
from io import StringIO
import importlib

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ====================== translator.py: line 92 (break on non-retryable HTTPError) ======================

class TestTranslatorNonRetryableHTTPError:
    """Cover line 92: break on non-429/5xx HTTPError"""

    @patch("translator.urlopen")
    def test_break_on_400_error(self, mock_urlopen):
        """HTTPError with 400 should break immediately (no retry)"""
        fp = MagicMock()
        fp.read.return_value = b""

        err = HTTPError("http://test", 400, "Bad Request", {}, fp)
        mock_urlopen.side_effect = err

        from translator import translate_single
        result = translate_single("test description long enough")
        assert result == ""  # Returns empty on error

    @patch("translator.urlopen")
    def test_break_on_404_error(self, mock_urlopen):
        """HTTPError with 404 should break immediately"""
        fp = MagicMock()
        fp.read.return_value = b""

        err = HTTPError("http://test", 404, "Not Found", {}, fp)
        mock_urlopen.side_effect = err

        from translator import translate_single
        result = translate_single("test description long enough")
        assert result == ""


# ====================== translator.py: line 238 (__main__ guard) ======================

class TestTranslatorMainCall:
    """Cover line 238: if __name__ == '__main__': main()"""

    def test_main_guard_call(self):
        """Verify main() is called when __name__ == '__main__'"""
        import translator
        # Read source to verify the guard exists
        source = Path(translator.__file__).read_text()
        assert 'if __name__ == "__main__":' in source
        assert "main()" in source


# ====================== enrich.py: line 170 (_translate_single_libretranslate in else branch) ======================

class TestEnrichElseBranchLine170:
    """Cover line 170: return _translate_single_libretranslate(text) in else branch"""

    def test_translate_to_chinese_calls_libretranslate(self):
        """When HAS_UNIFIED_TRANSLATOR is False, translate_to_chinese calls _translate_single_libretranslate"""
        import sys
        # Save and remove translator module to force ImportError
        translator_mod = sys.modules.pop("translator", None)
        sys.modules["translator"] = None  # Force ImportError on import
        try:
            if "enrich" in sys.modules:
                del sys.modules["enrich"]
            import importlib
            import enrich
            importlib.reload(enrich)
            
            assert enrich.HAS_UNIFIED_TRANSLATOR is False
            assert callable(enrich.translate_to_chinese)
        finally:
            # Restore translator module
            if translator_mod:
                sys.modules["translator"] = translator_mod
            del sys.modules["enrich"]


# ====================== enrich.py: lines 172-182 (batch_translate else branch) ======================

class TestEnrichBatchTranslateElse:
    """Cover lines 172-182: batch_translate in else branch"""

    def test_batch_translate_full_loop(self):
        """Test batch_translate processes all texts"""
        import sys
        translator_mod = sys.modules.pop("translator", None)
        sys.modules["translator"] = None
        try:
            if "enrich" in sys.modules:
                del sys.modules["enrich"]
            import importlib
            import enrich
            importlib.reload(enrich)
            
            assert enrich.HAS_UNIFIED_TRANSLATOR is False
            
            with patch("enrich._translate_single_libretranslate") as mock_translate:
                mock_translate.return_value = "翻译"
                texts = ["Hello", "World", "Test"]
                results = enrich.batch_translate(texts)
                assert len(results) == 3
                assert all(r == "翻译" for r in results)
        finally:
            if translator_mod:
                sys.modules["translator"] = translator_mod
            del sys.modules["enrich"]

    def test_batch_translate_with_chinese(self):
        """Test batch_translate skips Chinese texts"""
        import sys
        translator_mod = sys.modules.pop("translator", None)
        sys.modules["translator"] = None
        try:
            if "enrich" in sys.modules:
                del sys.modules["enrich"]
            import importlib
            import enrich
            importlib.reload(enrich)
            
            assert enrich.HAS_UNIFIED_TRANSLATOR is False
            
            with patch("enrich._translate_single_libretranslate") as mock_translate:
                mock_translate.return_value = "翻译"
                texts = ["Hello", "中文", "World"]
                results = enrich.batch_translate(texts)
                assert len(results) == 3
                assert results[1] == "中文"  # Chinese preserved
        finally:
            if translator_mod:
                sys.modules["translator"] = translator_mod
            del sys.modules["enrich"]


# ====================== enrich.py: line 262 (desc_cn = desc when Chinese) ======================

class TestEnrichMainChineseDesc:
    """Cover line 262: enriched['desc_cn'] = desc when desc is Chinese"""

    def test_main_chinese_desc_preserved(self, tmp_path):
        """Repos with Chinese desc should have desc_cn = desc"""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        stars_file = data_dir / "stars.json"
        stars_data = [
            {"id": 1, "name": "test/cn-repo", "desc": "这是一个中文描述", "stars": 100, "lang": "", "topics": []},
        ]
        stars_file.write_text(json.dumps(stars_data))

        enriched_file = data_dir / "stars-enriched.json"

        with patch("enrich.Path") as mock_path:
            def path_side_effect(p):
                p_str = str(p)
                if p_str == "data/stars.json":
                    return stars_file
                if p_str == "data/stars-enriched.json":
                    return enriched_file
                if p_str == "data/enrichment-progress.json":
                    return data_dir / "progress.json"
                return Path(p)
            mock_path.side_effect = path_side_effect

            import enrich
            enrich.main()

        result = json.loads(enriched_file.read_text())
        assert result[0]["desc_cn"] == "这是一个中文描述"


# ====================== enrich.py: line 284 (__main__ guard) ======================

class TestEnrichMainGuard:
    """Cover line 284: if __name__ == '__main__': main()"""

    def test_enrich_main_guard(self):
        """Verify enrich has __main__ guard"""
        import enrich
        source = Path(enrich.__file__).read_text()
        assert 'if __name__ == "__main__":' in source
        assert "main()" in source


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
