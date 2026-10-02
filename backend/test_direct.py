"""Smoke-test vision analyze_image (legacy direct path).
Standalone script — run directly with ``python test_direct.py``.
"""
import sys
import traceback
from dotenv import load_dotenv


def main():
    load_dotenv()
    from vision import analyze_image
    try:
        print(analyze_image("../test_image.jpg", "test prompt"))
    except Exception as e:
        traceback.print_exc()


if __name__ == "__main__":
    main()
