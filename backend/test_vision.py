"""Smoke-test vision analyze_image (standalone debug script).
Run directly with ``python test_vision.py``.
"""
import os


def main():
    print("Current Folder:", os.getcwd())
    print("Image Exists:", os.path.exists("uploads/test.jpg"))
    from vision import analyze_image

    answer = analyze_image(
        "uploads/test.jpg",
        "Explain everything in this image."
    )

    print(answer)


if __name__ == "__main__":
    main()
