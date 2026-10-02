"""Smoke-test ask_llm_with_image against Ollama.
Standalone script — run directly with ``python test_ollama.py``.
"""
import sys
import traceback
from dotenv import load_dotenv


def main():
    load_dotenv()
    from llm import ask_llm_with_image
    try:
        print(ask_llm_with_image("test prompt", "../test_image.jpg", model="llama3.2:1b"))
    except Exception as e:
        traceback.print_exc()


if __name__ == "__main__":
    main()
