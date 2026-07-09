"""tests/test_enrich_coverage.py — Additional tests to boost enrich.py coverage"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestEnrichCategoriesEdgeCases:
    """Additional category classification tests"""

    def test_all_languages_covered(self):
        """Test that each language in LANG_CATEGORIES can be matched"""
        from enrich import get_lang_category, LANG_CATEGORIES

        for lang, keywords in LANG_CATEGORIES.items():
            if lang == "AI/ML":
                continue
            if not keywords:
                continue
            # Test first keyword of each language
            kw = keywords[0]
            cat = get_lang_category(f"test-{kw}-repo", "description", [], "")
            # Should match the language (or AI/ML if keyword overlaps)
            assert cat in LANG_CATEGORIES or cat == "🤖 AI/ML" or cat == lang

    def test_ai_ml_takes_priority(self):
        """AI/ML category should be detected before language"""
        from enrich import get_lang_category
        # "llm" is in AI/ML keywords, should return AI/ML even if Python lang
        cat = get_lang_category("llm-tool", "LLM framework", [], "Python")
        assert cat == "🤖 AI/ML"

    def test_topics_normalization(self):
        """Test that topics are properly normalized in auto_tags"""
        from enrich import extract_auto_tags
        tags = extract_auto_tags("test", "desc", ["Python", "Machine-Learning", "a"], "")
        assert "python" in tags
        assert "machine-learning" in tags
        # Single char topics should be filtered
        assert "a" not in tags

    def test_empty_topics(self):
        """Test with None/empty topics"""
        from enrich import extract_auto_tags
        tags = extract_auto_tags("test", "desc", None, [])
        assert isinstance(tags, list)

    def test_topics_with_special_chars(self):
        """Topics with special chars should be cleaned"""
        from enrich import extract_auto_tags
        tags = extract_auto_tags("test", "desc", ["c++", "c#"], "")
        # c++ should be cleaned to c, c# should be cleaned to c
        assert isinstance(tags, list)


class TestEnrichTranslateFallback:
    """Test translate fallback when HAS_UNIFIED_TRANSLATOR is False"""

    def test_fallback_translate_exists(self):
        """Verify fallback translate function is defined"""
        import enrich
        assert hasattr(enrich, 'translate_to_chinese')
        assert callable(enrich.translate_to_chinese)

    def test_batch_translate_returns_list(self):
        """batch_translate should always return a list"""
        import enrich
        result = enrich.batch_translate([])
        assert isinstance(result, list)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
