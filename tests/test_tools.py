"""Tests for agents.code_executor and agents.tools."""

import pytest
import tempfile
import os
from io import BytesIO
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Code executor validation
# ---------------------------------------------------------------------------

class TestCodeValidation:
    """Test _validate_code blocks dangerous patterns."""

    @pytest.mark.parametrize("code,desc", [
        ("import os", "import os"),
        ("import subprocess", "import subprocess"),
        ("open('/etc/passwd').read()", "open read"),
        ('__import__("os")', "__import__"),
        ('eval("1+1")', "eval"),
        ('exec("print(1)")', "exec"),
        ('import sys', "import sys"),
        ('from os import path', "from os import"),
        ('subprocess.run(["ls"])', "subprocess.run"),
        ('socket.socket()', "socket"),
    ])
    def test_dangerous_code_blocked(self, code, desc):
        from agents.code_executor import _validate_code
        errors = _validate_code(code)
        assert len(errors) > 0, f"Expected {desc} to be blocked but it was allowed"

    @pytest.mark.parametrize("code", [
        "x = 2 + 2",
        "print('Hello World')",
        "result = [i for i in range(10)]",
        "x = 1; y = 2; print(x + y)",
        "name = 'test'; print(f'Hello {name}')",
    ])
    def test_safe_code_allowed(self, code):
        from agents.code_executor import _validate_code
        errors = _validate_code(code)
        assert len(errors) == 0, f"Safe code was rejected: {errors}"

    def test_code_length_limit(self):
        from agents.code_executor import _validate_code
        long_code = "x = 1\n" * 10000  # Very long code
        errors = _validate_code(long_code)
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# execute_python (from agents.tools)
# ---------------------------------------------------------------------------

class TestExecutePython:
    """Test the safe Python execution tool."""

    def test_safe_arithmetic(self):
        from agents.tools import execute_python
        result = execute_python("print(2 + 2)", timeout_seconds=5)
        assert result["success"] is True
        assert "4" in result["stdout"]

    def test_safe_print(self):
        from agents.tools import execute_python
        result = execute_python("print('Hello')", timeout_seconds=5)
        assert result["success"] is True
        assert "Hello" in result["stdout"]

    def test_division_error_handled(self):
        from agents.tools import execute_python
        result = execute_python("x = 1/0", timeout_seconds=5)
        assert "ZeroDivisionError" in (result["stderr"] or "")

    def test_dangerous_code_rejected(self):
        from agents.tools import execute_python
        result = execute_python("import os", timeout_seconds=5)
        assert result["success"] is False
        assert "Safety validation failed" in result["error"]

    def test_timeout(self):
        from agents.tools import execute_python
        result = execute_python(
            "import time\nwhile True:\n    time.sleep(1)",
            timeout_seconds=2,
        )
        assert result["timed_out"] is True

    def test_code_too_long(self):
        from agents.tools import execute_python
        from agents.tools import MAX_CODE_CHARS
        long_code = "x = 1\n" * (MAX_CODE_CHARS // 5)
        result = execute_python(long_code, timeout_seconds=5)
        assert result["success"] is False
        assert "maximum" in result["stderr"].lower()


# ---------------------------------------------------------------------------
# web_search (mocked)
# ---------------------------------------------------------------------------

class TestWebSearch:
    """Test query reformulation and result filtering."""

    def test_reformulate_query_normal(self):
        from agents.tools import _reformulate_query

        q, reformulated, reason = _reformulate_query("what is the capital of France")
        assert reformulated is False
        assert q == "what is the capital of France"

    def test_reformulate_query_false_premise(self):
        from agents.tools import _reformulate_query

        q, reformulated, reason = _reformulate_query("What is the capital of France in Asia?")
        assert reformulated is True
        assert "Asia" not in q
        assert "France" in q

    def test_reformulate_query_planet_disambiguation(self):
        from agents.tools import _reformulate_query

        q, reformulated, reason = _reformulate_query(
            "Who is the president of Mars?"
        )
        assert reformulated is True
        assert "planet" in q.lower()

    def test_filter_low_quality_domains(self):
        from agents.tools import _filter_and_rank_results

        results = [
            {"title": "Test", "body": "test content", "link": "https://wikipedia.org/test", "domain": "wikipedia.org"},
            {"title": "Test2", "body": "content", "link": "https://reddit.com/x", "domain": "reddit.com"},
        ]
        filtered = _filter_and_rank_results(results, "Test", min_score=1)
        assert len(filtered) <= 2
        # High-authority domain should rank first
        if len(filtered) == 2:
            assert "wikipedia" in filtered[0]["link"]

    def test_web_search_handles_exception(self):
        """WebSearch gracefully handles DDGS errors."""
        from agents.tools import web_search

        with patch("agents.tools.DDGS", side_effect=Exception("Network error")):
            result = web_search("test query")
        assert result["results"] == []
        assert result["original_query"] == "test query"
        assert result["returned"] == 0


# ---------------------------------------------------------------------------
# get_current_time
# ---------------------------------------------------------------------------

class TestGetCurrentTime:
    def test_returns_formatted_string(self):
        from agents.tools import get_current_time
        result = get_current_time()
        assert isinstance(result, str)
        assert len(result) > 10  # Should include date and time


# ---------------------------------------------------------------------------
# safe_filename
# ---------------------------------------------------------------------------

class TestSafeFilename:
    def test_normal_filename(self):
        from file_utils import safe_filename
        assert safe_filename("test.py") == "test.py"

    def test_path_traversal(self):
        from file_utils import safe_filename
        assert safe_filename("../../../etc/passwd") == "passwd"

    def test_special_chars_removed(self):
        from file_utils import safe_filename
        result = safe_filename("test<script>.py")
        assert "<" not in result
        assert ">" not in result
        assert "py" in result

    def test_empty_filename(self):
        from file_utils import safe_filename
        assert safe_filename("") == "upload"

    def test_long_filename_truncated(self):
        from file_utils import safe_filename
        result = safe_filename("a" * 200 + ".py")
        assert len(result) <= 160


# ---------------------------------------------------------------------------
# save_upload_file
# ---------------------------------------------------------------------------

class TestSaveUploadFile:
    def test_save_file_success(self, tmp_path):
        from file_utils import save_upload_file
        from fastapi import UploadFile

        file_obj = UploadFile(
            filename="test.txt",
            file=BytesIO(b"test content"),
        )
        dest = str(tmp_path / "test.txt")
        base_dir = str(tmp_path)

        bytes_written = save_upload_file(file_obj, dest, base_dir=base_dir)
        assert bytes_written == len(b"test content")
        assert os.path.exists(dest)

    def test_save_file_size_limit(self, tmp_path):
        from file_utils import save_upload_file
        from fastapi import UploadFile

        file_obj = UploadFile(
            filename="large.txt",
            file=BytesIO(b"x" * 10000),
        )
        dest = str(tmp_path / "large.txt")
        base_dir = str(tmp_path)

        with pytest.raises(Exception):
            save_upload_file(file_obj, dest, max_bytes=100, base_dir=base_dir)

    def test_save_file_path_traversal_blocked(self, tmp_path):
        """save_upload_file rejects destinations outside base_dir."""
        from file_utils import save_upload_file
        from fastapi import UploadFile

        file_obj = UploadFile(
            filename="test.txt",
            file=BytesIO(b"test"),
        )
        base_dir = str(tmp_path)
        # Destination outside base_dir should be rejected
        dest = str(tmp_path.parent / "escape.txt")

        with pytest.raises(Exception):
            save_upload_file(file_obj, dest, base_dir=base_dir)
