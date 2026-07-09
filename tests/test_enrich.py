"""tests/test_enrich.py — TDD tests for enrich.py"""

import json
import sys
import os
import re
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# Import after path setup
from enrich import (
    get_lang_category,
    extract_auto_tags,
    is_chinese,
    LANG_CATEGORIES,
    TECH_KEYWORDS,
    HAS_UNIFIED_TRANSLATOR,
)


class TestGetLangCategory:
    """Tests for language category classification"""

    def test_ai_ml_keyword_in_name(self):
        cat = get_lang_category("super-llm-tool", "AI tool", [], "")
        assert cat == "🤖 AI/ML"

    def test_ai_ml_keyword_in_desc(self):
        cat = get_lang_category("tool", "Machine learning library", [], "")
        assert cat == "🤖 AI/ML"

    def test_python_language_match(self):
        cat = get_lang_category("django", "Web framework", [], "Python")
        assert cat == "Python"

    def test_no_match_falls_back_to_github_lang(self):
        cat = get_lang_category("unknown-repo", "Something", [], "Haskell")
        assert cat == "Haskell"

    def test_no_lang_returns_other(self):
        cat = get_lang_category("unknown-repo", "Something", [], "")
        assert cat == "Other"

    def test_stable_diffusion_detected(self):
        cat = get_lang_category("stable-diffusion-webui", "Image generation", [], "Python")
        assert cat == "🤖 AI/ML"

    def test_keyword_from_topics(self):
        cat = get_lang_category("myrepo", "", ["pytorch"], "")
        assert cat == "Python"


class TestExtractAutoTags:
    """Tests for auto tag extraction"""

    def test_framework_detected(self):
        tags = extract_auto_tags("cool-framework", "A new framework", [], "")
        assert "Framework" in tags

    def test_ai_detected(self):
        tags = extract_auto_tags("ai-tool", "AI-powered tool", [], "")
        assert "AI" in tags

    def test_tags_from_topics(self):
        tags = extract_auto_tags("unknown", "desc", ["python"], "")
        assert "python" in tags

    def test_max_10_tags(self):
        topics = [f"topic-{i}" for i in range(15)]
        tags = extract_auto_tags("repo", "description", topics, "")
        assert len(tags) <= 10

    def test_empty_repo(self):
        tags = extract_auto_tags("", "", [], "")
        assert tags == []


class TestIsChineseInEnrich:
    """Tests that is_chinese is available in enrich.py"""

    def test_importable(self):
        assert callable(is_chinese)

    def test_basic_chinese(self):
        assert is_chinese("中文") is True

    def test_english(self):
        assert is_chinese("English") is False


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
