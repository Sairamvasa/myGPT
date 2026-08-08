import os
import cv2

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(
    api_key=GEMINI_API_KEY
)

# ===========================
# TEXT CHAT
# ===========================

def ask_gemini(prompt):

    try:
        print("Using model: gemini-2.5-flash")

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        return response.text

    except Exception as e:
        return f"Gemini Error: {str(e)}"


# ===========================
# IMAGE PREPROCESSING
# ===========================

def preprocess_image(image_path):

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

            model="gemini-3.5-flash",

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

        return response.text

    except Exception as e:

        return f"Vision Error: {str(e)}"
    
def stream_gemini(prompt):

    try:

        print("Using streaming model: gemini-2.5-flash")

        response = client.models.generate_content_stream(
            model="gemini-2.5-flash",
            contents=prompt
        )

        for chunk in response:

            if chunk.text:
                yield chunk.text

    except Exception as e:

        yield f"Gemini Error: {str(e)}"