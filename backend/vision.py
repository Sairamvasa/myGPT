import os
from dotenv import load_dotenv

load_dotenv()

from llm import ask_llm_with_image, LLMError


def analyze_image(image_path, prompt="Describe this image."):

    if not image_path or not os.path.exists(image_path):
        raise LLMError("bad_request", "Invalid image path.", 400)

    try:
        answer = ask_llm_with_image(prompt, image_path)
        return answer
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError("unknown", "Image analysis failed.", 500)
