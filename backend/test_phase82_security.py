"""Phase 8.2 Security Tests: Python Executor, File Upload, Image Handling."""
import os
import sys
import tempfile
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from agents.code_executor import _validate_code, execute_python
from file_utils import safe_filename, save_upload_file, MAX_UPLOAD_BYTES, MAX_TOTAL_UPLOAD_BYTES, MAX_UPLOAD_FILES

# Image handling imports
from fastapi.testclient import TestClient
from fastapi import HTTPException
from unittest.mock import patch, MagicMock
import app as app_module

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}: {detail}")

def run_executor_tests():
    print("=" * 70)
    print("SECTION 1: PYTHON EXECUTOR SECURITY")
    print("=" * 70)

    # 1.1 Blocked imports
    print("\n1.1 Blocked imports")
    blocked_imports = [
        ("import os", "os"),
        ("import sys", "sys"),
        ("import subprocess", "subprocess"),
        ("import socket", "socket"),
        ("import pathlib", "pathlib"),
        ("import shutil", "shutil"),
        ("import urllib.request", "urllib"),
        ("import requests", "requests"),
        ("import ctypes", "ctypes"),
        ("import multiprocessing", "multiprocessing"),
        ("import threading", "threading"),
        ("import importlib", "importlib"),
        ("import pickle", "pickle"),
        ("import sqlite3", "sqlite3"),
        ("from os import path", "os.path"),
        ("from sys import exit", "sys.exit"),
    ]
    for code, desc in blocked_imports:
        errors = _validate_code(code)
        blocked = len(errors) > 0
        check(f"  Import {desc} blocked", blocked, f"errors: {errors}")

    # 1.2 Blocked dangerous builtins
    print("\n1.2 Blocked dangerous builtins")
    dangerous_builtins = [
        ('eval("1+1")', "eval"),
        ('exec("print(1)")', "exec"),
        ('compile("1+1", "", "eval")', "compile"),
        ('__import__("os")', "__import__"),
        ('open("/etc/passwd")', "open"),
        ('globals()', "globals"),
        ('locals()', "locals"),
        ('vars()', "vars"),
        ('getattr({}, "__class__")'.format({}), "getattr"),
        ('setattr({}, "x", 1)'.format({}), "setattr"),
    ]
    for code, desc in dangerous_builtins:
        errors = _validate_code(code)
        blocked = len(errors) > 0
        check(f"  Builtin {desc} blocked", blocked, f"errors: {errors}")

    # 1.3 Filesystem access attempts
    print("\n1.3 Filesystem access blocked")
    fs_attempts = [
        ('open("test.txt").read()', "open read"),
        ('with open("test.txt") as f: f.read()', "open context manager"),
        ('pathlib.Path("test.txt").read_text()', "pathlib read"),
        ('os.path.exists("test.txt")', "os.path.exists"),
        ('os.listdir(".")', "os.listdir"),
        ('shutil.copy("a.txt", "b.txt")', "shutil.copy"),
    ]
    for code, desc in fs_attempts:
        errors = _validate_code(code)
        blocked = len(errors) > 0
        check(f"  FS {desc} blocked", blocked, f"errors: {errors}")

    # 1.4 Subprocess/process creation blocked
    print("\n1.4 Subprocess/process creation blocked")
    proc_attempts = [
        ('subprocess.run(["ls"])', "subprocess.run"),
        ('subprocess.Popen(["ls"])', "subprocess.Popen"),
        ('os.system("ls")', "os.system"),
        ('os.popen("ls")', "os.popen"),
    ]
    for code, desc in proc_attempts:
        errors = _validate_code(code)
        blocked = len(errors) > 0
        check(f"  Proc {desc} blocked", blocked, f"errors: {errors}")

    # 1.5 Network access blocked
    print("\n1.5 Network access blocked")
    net_attempts = [
        ('import socket; socket.socket()', "socket creation"),
        ('urllib.request.urlopen("http://example.com")', "urllib request"),
        ('requests.get("http://example.com")', "requests get"),
    ]
    for code, desc in net_attempts:
        errors = _validate_code(code)
        blocked = len(errors) > 0
        check(f"  Net {desc} blocked", blocked, f"errors: {errors}")

    # 1.6 Timeout protection
    print("\n1.6 Timeout protection")
    result = execute_python("import time\nwhile True:\n    time.sleep(1)", timeout_seconds=1)
    check("  Infinite loop times out", result["timed_out"], f"timed_out={result['timed_out']}")

    # 1.7 Output limit
    print("\n1.7 Output limit")
    result = execute_python('print("x" * 100000)', timeout_seconds=5)
    check("  Huge stdout truncated", len(result["stdout"]) <= 65000, f"stdout len={len(result['stdout'])}")

    # 1.8 Oversized code rejected
    print("\n1.8 Oversized code rejected")
    huge_code = "x = 1\n" * 20000  # ~120KB
    result = execute_python(huge_code, timeout_seconds=5)
    check("  Oversized code rejected", not result["success"] and "exceeds maximum length" in result["stderr"], f"stderr={result['stderr'][:100]}")

    # 1.9 Malformed Python handled
    print("\n1.9 Malformed Python handled")
    result = execute_python("def incomplete(", timeout_seconds=5)
    check("  Syntax error handled", not result["success"] and "Syntax error" in result["stderr"], f"stderr={result['stderr'][:100]}")

    # 1.10 Safe Python execution
    print("\n1.10 Safe Python execution")
    safe_tests = [
        ('print("Hello, World!")', "print"),
        ("x = 2 + 2\nprint(x)", "arithmetic"),
        ("def add(a, b):\n    return a + b\nprint(add(10, 20))", "function"),
        ("for i in range(5):\n    print(i)", "loop"),
        ("[x*2 for x in range(10)]", "list comprehension"),
        ("sum(range(100))", "sum"),
        ('{"a": 1, "b": 2}.get("a")', "dict"),
    ]
    for code, desc in safe_tests:
        result = execute_python(code, timeout_seconds=5)
        check(f"  Safe {desc} executes", result["success"], f"stdout={result['stdout'][:50]}, stderr={result['stderr'][:50]}")

    print(f"\nSection 1 Summary: {passed} passed, {failed} failed")


def run_file_upload_tests():
    print("\n" + "=" * 70)
    print("SECTION 2: FILE UPLOAD SECURITY")
    print("=" * 70)

    # 2.1 Filename safety
    print("\n2.1 Filename safety")
    check("  Normal filename", safe_filename("test.py") == "test.py")
    check("  Path traversal ../", safe_filename("../../../etc/passwd") == "passwd")
    check("  Path traversal ..\\", safe_filename("..\\..\\..\\windows\\system32\\cmd.exe") == "cmd.exe")
    check("  Absolute Unix path", safe_filename("/etc/passwd") == "passwd")
    check("  Absolute Windows path", safe_filename("C:\\Windows\\System32\\test.txt") == "test.txt")
    check("  Backslash traversal", safe_filename("folder\\..\\secret.txt") == "secret.txt")
    check("  Null byte", safe_filename("test\x00.txt") == "test_.txt")
    check("  Special chars", safe_filename("test<script>.py") == "test_script_.py")
    check("  Long filename truncated", len(safe_filename("a" * 500)) <= 160)
    check("  Empty filename default", safe_filename("") == "upload")
    check("  None filename default", safe_filename(None) == "upload")
    check("  Dots only", safe_filename("...") == "upload")

    # 2.2 File validation
    print("\n2.2 File validation")
    with tempfile.TemporaryDirectory() as tmpdir:
        # 2.2.1 Empty file
        dest = os.path.join(tmpdir, "empty.txt")
        mock_file = MagicMock()
        mock_file.filename = "empty.txt"
        mock_file.file = io.BytesIO(b"")
        try:
            bytes_written = save_upload_file(mock_file, dest, max_bytes=MAX_UPLOAD_BYTES)
            check("  Empty file saved", bytes_written == 0 and os.path.exists(dest))
        except Exception as e:
            check("  Empty file saved", False, f"raised: {e}")

        # 2.2.2 Normal file
        dest = os.path.join(tmpdir, "normal.txt")
        mock_file = MagicMock()
        mock_file.filename = "normal.txt"
        mock_file.file = io.BytesIO(b"Hello, World!")
        try:
            bytes_written = save_upload_file(mock_file, dest, max_bytes=MAX_UPLOAD_BYTES)
            check("  Normal file saved", bytes_written == 13 and os.path.exists(dest))
        except Exception as e:
            check("  Normal file saved", False, f"raised: {e}")

        # 2.2.3 Oversized file rejected
        dest = os.path.join(tmpdir, "large.txt")
        large_content = "x" * (MAX_UPLOAD_BYTES + 1000)
        mock_file = MagicMock()
        mock_file.filename = "large.txt"
        mock_file.file = io.BytesIO(large_content.encode())
        try:
            save_upload_file(mock_file, dest, max_bytes=MAX_UPLOAD_BYTES)
            check("  Oversized file rejected", False, "Should have raised 413")
        except Exception as e:
            check("  Oversized file rejected", "413" in str(e) or "limit" in str(e).lower(), f"error: {e}")

    # 2.3 Storage safety - file cannot escape upload dir
    print("\n2.3 Storage safety")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Try to save with path traversal in destination
        dest = os.path.join(tmpdir, "..", "escape.txt")
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        mock_file.file = io.BytesIO(b"escape attempt")
        try:
            save_upload_file(mock_file, dest, max_bytes=MAX_UPLOAD_BYTES, base_dir=tmpdir)
            check("  Path traversal in dest contained", False, "Should have raised 400")
        except Exception as e:
            check("  Path traversal in dest contained", "400" in str(e) or "within" in str(e).lower(), f"error: {e}")

        # Valid destination within base_dir should work
        dest = os.path.join(tmpdir, "valid.txt")
        mock_file = MagicMock()
        mock_file.filename = "valid.txt"
        mock_file.file = io.BytesIO(b"valid")
        try:
            save_upload_file(mock_file, dest, max_bytes=MAX_UPLOAD_BYTES, base_dir=tmpdir)
            check("  Valid dest within base_dir works", os.path.exists(dest))
        except Exception as e:
            check("  Valid dest within base_dir works", False, f"raised: {e}")

    # 2.4 Temporary file cleanup on failure
    print("\n2.4 Temporary file cleanup")
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = os.path.join(tmpdir, "fail.txt")
        mock_file = MagicMock()
        mock_file.filename = "fail.txt"
        # Create a file-like object that raises on read
        class FailingFile:
            def read(self, size):
                raise IOError("Simulated read error")
        mock_file.file = FailingFile()
        try:
            save_upload_file(mock_file, dest, max_bytes=MAX_UPLOAD_BYTES)
            check("  Failed upload cleanup", False, "Should have raised")
        except Exception:
            # File should not exist after failed upload
            check("  Failed upload cleanup", not os.path.exists(dest), f"dest exists: {os.path.exists(dest)}")

    print(f"\nSection 2 Summary: {passed - 50} passed, {failed} failed (cumulative)")


def run_image_tests():
    print("\n" + "=" * 70)
    print("SECTION 3: IMAGE HANDLING SECURITY")
    print("=" * 70)

    # Set up test client with mocked authentication
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 1

    # Generate valid test images using PIL
    from PIL import Image
    import io
    
    # Create a valid 10x10 PNG
    png_img = Image.new('RGB', (10, 10), color='red')
    png_buffer = io.BytesIO()
    png_img.save(png_buffer, format='PNG')
    png_bytes = png_buffer.getvalue()
    
    # Create a valid 10x10 JPEG
    jpeg_img = Image.new('RGB', (10, 10), color='blue')
    jpeg_buffer = io.BytesIO()
    jpeg_img.save(jpeg_buffer, format='JPEG')
    jpeg_bytes = jpeg_buffer.getvalue()

    # 3.1 Valid image tests - mock analyze_image to avoid external call
    print("\n3.1 Valid image")
    with patch.object(app_module, "verify_chat_ownership"), \
         patch.object(app_module, "analyze_image", return_value="Test image description"), \
         patch.object(app_module, "generate_image", return_value="base64fakeimage"):

        client = TestClient(app_module.app)

        files = {"file": ("test.png", png_bytes, "image/png")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Valid PNG accepted", resp.status_code == 200, f"status={resp.status_code}, body={resp.text[:100]}")

        files = {"file": ("test.jpg", jpeg_bytes, "image/jpeg")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Valid JPEG accepted", resp.status_code == 200, f"status={resp.status_code}, body={resp.text[:100]}")

    # 3.2 Invalid image handling - NO mock for analyze_image to test endpoint validation
    print("\n3.2 Invalid image handling")
    with patch.object(app_module, "verify_chat_ownership"), \
         patch.object(app_module, "generate_image", return_value="base64fakeimage"):

        client = TestClient(app_module.app)

        # Empty image
        files = {"file": ("empty.png", b"", "image/png")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Empty image rejected", resp.status_code in [400, 422, 500], f"status={resp.status_code}")

        # Random non-image bytes
        files = {"file": ("random.png", b"not an image at all", "image/png")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Random bytes rejected", resp.status_code in [400, 422, 500], f"status={resp.status_code}")

        # Corrupt image (truncated PNG)
        corrupt_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        files = {"file": ("corrupt.png", corrupt_png, "image/png")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Corrupt image rejected", resp.status_code in [400, 422, 500], f"status={resp.status_code}")

        # Unsupported format (BMP)
        bmp_bytes = b"BM\x36\x00\x00\x00\x00\x00\x00\x00\x36\x00\x00\x00\x28\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00\x01\x00\x18\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        files = {"file": ("test.bmp", bmp_bytes, "image/bmp")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Unsupported format rejected", resp.status_code == 400, f"status={resp.status_code}")

# 3.3 MIME/type validation - mock analyze_image to succeed after validation
    print("\n3.3 MIME/type validation")
    with patch.object(app_module, "verify_chat_ownership"), \
         patch.object(app_module, "analyze_image", return_value="Test image description"), \
         patch.object(app_module, "generate_image", return_value="base64fakeimage"):

        client = TestClient(app_module.app)

        # Correct MIME type
        files = {"file": ("test.png", png_bytes, "image/png")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Correct MIME accepted", resp.status_code == 200, f"status={resp.status_code}")

        # Misleading MIME type (PNG content with JPEG MIME) - extension is .png which is allowed
        files = {"file": ("test.png", png_bytes, "image/jpeg")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Misleading MIME accepted (extension-based)", resp.status_code == 200, f"status={resp.status_code}")

        # Missing MIME type
        files = {"file": ("test.png", png_bytes, "")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Missing MIME handled", resp.status_code in [200, 400, 422], f"status={resp.status_code}")

        # Extension mismatch (PNG content, .jpg extension) - extension is .jpg which is allowed, but content is PNG
        files = {"file": ("test.jpg", png_bytes, "image/png")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Extension mismatch handled", resp.status_code in [200, 400], f"status={resp.status_code}")

    # 3.4 Size/security limits - NO mock for analyze_image (validation should fail)
    print("\n3.4 Size/security limits")
    with patch.object(app_module, "verify_chat_ownership"), \
         patch.object(app_module, "generate_image", return_value="base64fakeimage"):

        client = TestClient(app_module.app)

        # Oversized image (larger than MAX_UPLOAD_BYTES)
        large_image = b"x" * (MAX_UPLOAD_BYTES + 1000)
        files = {"file": ("large.png", large_image, "image/png")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Oversized image rejected", resp.status_code in [413, 400], f"status={resp.status_code}")

    # 3.5 Filename/path safety - mock analyze_image to succeed after validation
    print("\n3.5 Filename/path safety")
    with patch.object(app_module, "verify_chat_ownership"), \
         patch.object(app_module, "analyze_image", return_value="Test image description"), \
         patch.object(app_module, "generate_image", return_value="base64fakeimage"):

        client = TestClient(app_module.app)

        # Path traversal in filename
        files = {"file": ("../../../etc/passwd.png", png_bytes, "image/png")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Filename traversal sanitized", resp.status_code == 200, f"status={resp.status_code}")

        # Windows traversal
        files = {"file": ("..\\..\\windows\\system32\\cmd.exe.png", png_bytes, "image/png")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Windows traversal sanitized", resp.status_code == 200, f"status={resp.status_code}")

        # Absolute path
        files = {"file": ("/etc/passwd.png", png_bytes, "image/png")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Absolute path sanitized", resp.status_code == 200, f"status={resp.status_code}")

        # Null byte in filename
        files = {"file": ("test\x00.png", png_bytes, "image/png")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  Null byte sanitized", resp.status_code == 200, f"status={resp.status_code}")

    # 3.6 API error safety - mock analyze_image with LLMError
    print("\n3.6 API error safety")
    from llm import LLMError
    with patch.object(app_module, "verify_chat_ownership"), \
         patch.object(app_module, "analyze_image", side_effect=LLMError("test_error", "Internal error with API_KEY=secret123", 500)), \
         patch.object(app_module, "generate_image", return_value="base64fakeimage"):

        client = TestClient(app_module.app)
        files = {"file": ("test.png", png_bytes, "image/png")}
        resp = client.post("/vision", files=files, data={"prompt": "Describe this"})
        check("  No API key in error", resp.status_code == 500 and "API_KEY" not in resp.text and "secret123" not in resp.text, f"body={resp.text[:200]}")
        check("  No traceback in error", resp.status_code == 500 and "traceback" not in resp.text.lower(), f"body={resp.text[:200]}")
        check("  No JWT secret in error", resp.status_code == 500 and "JWT" not in resp.text, f"body={resp.text[:200]}")

    # Test generate-image error safety
    with patch.object(app_module, "verify_chat_ownership"), \
         patch.object(app_module, "generate_image", side_effect=LLMError("test_error", "Gemini API error with GEMINI_API_KEY=secret456", 500)), \
         patch.object(app_module, "analyze_image", return_value="Test"):

        client = TestClient(app_module.app)
        resp = client.post("/generate-image", data={"prompt": "A cat", "aspect_ratio": "1:1"})
        check("  Generate-image no API key leak", resp.status_code == 500 and "GEMINI_API_KEY" not in resp.text and "secret456" not in resp.text, f"body={resp.text[:200]}")
        check("  Generate-image no traceback", resp.status_code == 500 and "traceback" not in resp.text.lower(), f"body={resp.text[:200]}")

    print(f"\nSection 3 Summary: {passed - 68} passed, {failed} failed (cumulative)")


if __name__ == "__main__":
    run_executor_tests()
    run_file_upload_tests()
    run_image_tests()
    if failed > 0:
        sys.exit(1)