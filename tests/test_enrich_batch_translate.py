"""tests/test_enrich_batch_translate.py — Regression tests for P0-04 fix"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestBatchTranslateP004:
    """P0-04: enrich.py batch_translate should return translated text, not original"""

    def test_batch_translate_returns_translated_when_unified(self):
        """When HAS_UNIFIED_TRANSLATOR=True, batch_translate must translate, not return original"""
        # Create a mock translator module that doesn't pollute sys.modules
        mock_translator = MagicMock()
        mock_translator.translate_single = lambda text: f"翻译_{text}"
        
        # Patch the specific import in enrich module
        with patch.dict(sys.modules, {"translator": mock_translator}):
            # Force reimport of enrich to pick up the mock
            if "enrich" in sys.modules:
                del sys.modules["enrich"]
            from enrich import batch_translate
            texts = ["hello", "world", "test"]
            results = batch_translate(texts)
            for original, result in zip(texts, results):
                assert f"翻译_{original}" == result, f"Expected translation of '{original}', got '{result}'"

    def test_batch_translate_returns_same_length(self):
        """batch_translate should return same number of items as input"""
        mock_translator = MagicMock()
        mock_translator.translate_single = lambda text: f"翻译_{text}"
        
        with patch.dict(sys.modules, {"translator": mock_translator}):
            if "enrich" in sys.modules:
                del sys.modules["enrich"]
            from enrich import batch_translate
            texts = ["a", "b", "c", "d", "e"]
            results = batch_translate(texts)
            assert len(results) == len(texts)

    def test_batch_translate_empty_list(self):
        """batch_translate with empty list should return empty list"""
        mock_translator = MagicMock()
        mock_translator.translate_single = lambda text: text
        
        with patch.dict(sys.modules, {"translator": mock_translator}):
            if "enrich" in sys.modules:
                del sys.modules["enrich"]
            from enrich import batch_translate
            assert batch_translate([]) == []


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
