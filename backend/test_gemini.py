"""Smoke-test the legacy gemini.analyze_image path.
Standalone script — run directly with ``python test_gemini.py``.
"""
import sys
import traceback
from dotenv import load_dotenv


def main():
    load_dotenv()
    from gemini import analyze_image
    try:
        print(analyze_image("../test_image.jpg", "test prompt"))
    except Exception as e:
        traceback.print_exc()


if __name__ == "__main__":
    main()
