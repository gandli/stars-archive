"""tests/test_main_guards.py — Cover __main__ guards to reach 100%"""

import sys
import json
import os
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent / "scripts"


def test_translator_main_guard():
    """Cover line 238: if __name__ == "__main__': main()"""
    tmp = tempfile.mkdtemp()
    data_dir = Path(tmp) / "data"
    data_dir.mkdir()
    enriched_file = data_dir / "stars-enriched.json"
    enriched_file.write_text(json.dumps([]))

    # Use exec with __name__ == "__main__" to cover the guard
    translator_file = SCRIPTS / "translator.py"
    source = translator_file.read_text()

    original_argv = sys.argv[:]
    sys.argv = ["translator.py"]
    try:
        ns = {
            "__name__": "__main__",
            "__file__": str(translator_file),
            "__builtins__": __builtins__,
            "sys": sys,
        }
        exec(compile(source, str(translator_file), "exec"), ns)
    finally:
        sys.argv = original_argv


def test_enrich_main_guard():
    """Cover line 284: if __name__ == "__main__': main()"""
    tmp = tempfile.mkdtemp()
    data_dir = Path(tmp) / "data"
    data_dir.mkdir()
    stars_file = data_dir / "stars.json"
    stars_file.write_text(json.dumps([]))

    enrich_file = SCRIPTS / "enrich.py"
    source = enrich_file.read_text()

    original_argv = sys.argv[:]
    original_cwd = os.getcwd()
    sys.argv = ["enrich.py"]
    try:
        os.chdir(tmp)
        ns = {
            "__name__": "__main__",
            "__file__": str(enrich_file),
            "__builtins__": __builtins__,
            "sys": sys,
        }
        exec(compile(source, str(enrich_file), "exec"), ns)
    finally:
        sys.argv = original_argv
        os.chdir(original_cwd)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
