"""Smoke-test legacy gemini._get_client + model generation.
Standalone script — run directly with ``python test_model.py``.
"""
from dotenv import load_dotenv
import os


def main():
    load_dotenv()
    from gemini import _get_client
    try:
        client = _get_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Say Hello"
        )
        print(response.text)
    except RuntimeError as e:
        print(f"Gemini not configured: {e}")
    except Exception as e:
        print(f"Gemini error: {e}")


if __name__ == "__main__":
    main()
