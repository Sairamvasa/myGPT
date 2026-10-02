"""NVIDIA-only image analysis for MyGPT."""

import os
import base64

from dotenv import load_dotenv
from PIL import Image

load_dotenv()

from llm import LLMError
from providers.registry import configure_providers_from_env


def analyze_image(
    image_path: str,
    prompt: str = "Describe this image.",
) -> str:
    """Analyze an image using NVIDIA's multimodal model."""

    if not image_path or not os.path.exists(image_path):
        raise LLMError(
            "bad_request",
            "Invalid image path.",
            400,
        )

    # Validate the image.
    try:
        with Image.open(image_path) as img:
            img.verify()

            if img.width > 8192 or img.height > 8192:
                raise LLMError(
                    "bad_request",
                    "Image dimensions too large.",
                    400,
                )

    except LLMError:
        raise

    except Exception as exc:
        raise LLMError(
            "bad_request",
            "Invalid or corrupt image file.",
            400,
        ) from exc

    try:
        with open(image_path, "rb") as file:
            image_b64 = base64.b64encode(
                file.read()
            ).decode("utf-8")

    except Exception as exc:
        raise LLMError(
            "bad_request",
            "Unable to read the image file.",
            400,
        ) from exc

    extension = (
        os.path.splitext(image_path)[1]
        .lower()
    )

    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }

    mime_type = mime_map.get(
        extension,
        "image/jpeg",
    )

    try:
        registry = configure_providers_from_env()
        provider = registry.get_primary()

        if provider is None:
            raise LLMError(
                "provider_not_configured",
                "NVIDIA provider is not configured.",
                503,
            )

        return provider.generate_with_image(
            prompt=prompt,
            image_base64=image_b64,
            image_mime_type=mime_type,
            num_predict=2048,
            temperature=1.0,
            top_p=0.95,
        )

    except LLMError:
        raise

    except Exception as exc:
        raise LLMError(
            "vision_error",
            "NVIDIA image analysis failed.",
            503,
        ) from exc
