import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(
    api_key=GEMINI_API_KEY
)


class GeminiError(Exception):
    """Typed Gemini API failure, ready for HTTP status mapping."""

    def __init__(self, kind, user_message, status_code=500, retry_after=None):
        super().__init__(user_message)
        self.kind = kind
        self.user_message = user_message
        self.status_code = status_code
        self.retry_after = retry_after


def _extract_status(e):
    """Best-effort extraction of an HTTP status code from a Gemini exception."""
    for obj in (e, getattr(e, "__cause__", None), getattr(e, "__context__", None)):
        if obj is None:
            continue
        sc = getattr(obj, "status_code", None)
        if sc is None:
            resp = getattr(obj, "response", None)
            if resp is not None:
                sc = getattr(resp, "status_code", None)
        if sc is not None:
            try:
                return int(sc)
            except (TypeError, ValueError):
                return None
    return None


def _classify_gemini_error(e):
    """Map a raw Gemini/network exception to a GeminiError."""

    status = _extract_status(e)

    text = (
        f"{type(e).__name__} "
        f"{getattr(e, '__cause__', None)} "
        f"{str(e)}"
    ).lower()

    # Timeout should be checked first, even if provider returns 503
    if any(k in text for k in ("timeout", "timed out", "deadline exceeded")):
        return GeminiError(
            "timeout",
            "The AI service took too long to respond. Please try again.",
            504,
        )

    if status == 429 or "resource_exhausted" in text or "quota" in text:
        return GeminiError(
            "quota_exceeded",
            "The AI service quota has been reached. Please try again in a moment.",
            429,
            retry_after=30,
        )

    if status in (401, 403):
        return GeminiError(
            "auth_error",
            "The AI service is not configured correctly. Please contact support.",
            401,
        )

    if status == 400:
        return GeminiError(
            "bad_request",
            "The request could not be processed by the AI service.",
            400,
        )

    if status is not None and 500 <= status < 600:
        return GeminiError(
            "server_error",
            "The AI service is temporarily unavailable. Please try again later.",
            502,
        )

    if any(
        k in text
        for k in (
            "connection",
            "connect",
            "network",
            "resolve",
            "socket",
            "name or service not known",
        )
    ):
        return GeminiError(
            "network_error",
            "Unable to reach the AI service. Check your connection and try again.",
            502,
        )

    return GeminiError(
        "unknown",
        "Something went wrong with the AI service. Please try again.",
        500,
    )


# ===========================
# IMAGE PREPROCESSING
# ===========================

def preprocess_image(image_path):
    # Lazy import: only load cv2 when actually processing an image.
    # Prevents startup crash on Railway if opencv is not installed.
    import cv2

    image = cv2.imread(image_path)

    if image is None:
        raise ValueError("Unable to read image")

    h, w = image.shape[:2]

    if w > 1600:

        scale = 1600 / w

        image = cv2.resize(
            image,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA
        )

    image = cv2.bilateralFilter(
        image,
        5,
        50,
        50
    )

    blur = cv2.GaussianBlur(
        image,
        (0, 0),
        1
    )

    image = cv2.addWeighted(
        image,
        1.4,
        blur,
        -0.4,
        0
    )

    os.makedirs(
        "processed_images",
        exist_ok=True
    )

    filename = os.path.basename(image_path)

    name, ext = os.path.splitext(filename)

    processed_path = os.path.join(
        "processed_images",
        f"{name}_processed.jpg"
    )

    cv2.imwrite(
        processed_path,
        image
    )

    return processed_path


# ===========================
# GEMINI VISION
# ===========================

def analyze_image(
    image_path,
    question="Explain this image."
):

    try:

        processed = preprocess_image(
            image_path
        )

        with open(processed, "rb") as f:

            image_bytes = f.read()

        response = client.models.generate_content(

            model="gemini-2.5-flash",

            contents=[

                types.Part.from_text(
                    text=question
                ),

                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg"
                )

            ]

        )

        text = getattr(response, "text", None)
        if text is None:
            raise GeminiError(
                "unknown",
                "The AI service returned an empty response. Please try again.",
                502,
            )
        return text

    except GeminiError:
        raise
    except Exception as e:

        raise _classify_gemini_error(e)


# ===========================
# STREAMING (used by /stream)
# ===========================

def stream_gemini(prompt):
    """
    Stream a response from Gemini using Chat.send_message_stream
    to avoid the AFC deprecation warning from generate_content_stream.
    Falls back gracefully on any error.
    """
    try:
        print("Using streaming model: gemini-2.5-flash")

        chat = client.chats.create(model="gemini-2.5-flash")

        for chunk in chat.send_message_stream(prompt):
            if chunk.text:
                yield chunk.text

    except GeminiError:
        raise
    except Exception as e:
        raise _classify_gemini_error(e)