import os
from dotenv import load_dotenv

load_dotenv()

from llm import ask_llm_with_image, LLMError
from PIL import Image


def analyze_image(image_path, prompt="Describe this image."):

    if not image_path or not os.path.exists(image_path):
        raise LLMError("bad_request", "Invalid image path.", 400)

    # Validate image content
    try:
        with Image.open(image_path) as img:
            img.verify()  # Verify it's a valid image
            # Check for reasonable dimensions to prevent resource exhaustion
            if img.width > 8192 or img.height > 8192:
                raise LLMError("bad_request", "Image dimensions too large.", 400)
    except LLMError:
        raise
    except Exception:
        raise LLMError("bad_request", "Invalid or corrupt image file.", 400)

    try:
        answer = ask_llm_with_image(prompt, image_path)
        return answer
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError("unknown", "Image analysis failed.", 500)
