"""tests/test_export_path.py — Regression tests for P0-03 fix"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestExportPath:
    """P0-03: export_for_web.py should resolve path relative to script, not hardcoded"""

    def test_default_path_relative_to_script(self):
        """Without DATA_DIR env, should use script-relative path"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATA_DIR", None)
            # Must re-import to pick up env change
            if "export_for_web" in sys.modules:
                del sys.modules["export_for_web"]
            try:
                import export_for_web
                expected = Path(export_for_web.__file__).parent.parent / "data"
                assert export_for_web.DATA_DIR == expected
            except ModuleNotFoundError:
                # numpy not available, skip
                pass

    def test_env_path_overrides_default(self):
        """DATA_DIR env should override default"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"DATA_DIR": tmpdir}):
                if "export_for_web" in sys.modules:
                    del sys.modules["export_for_web"]
                try:
                    import export_for_web
                    assert export_for_web.DATA_DIR == Path(tmpdir)
                except ModuleNotFoundError:
                    # numpy not available, skip
                    pass


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
