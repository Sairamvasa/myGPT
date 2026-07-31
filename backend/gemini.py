import os
import base64
import cv2
from datetime import datetime
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=api_key
)


def ask_gemini(question, context=None):

    # Current date and time
    now = datetime.now()

    current_datetime = now.strftime(
        "%A, %d %B %Y, %I:%M %p"
    )

    # Main system prompt
    system_prompt = f"""
You are MyGPT, a helpful AI assistant.

Current date and time:
{current_datetime}

Important instructions:
- Use the current date and time above for date/time questions.
- Never invent the current date.
- Answer clearly and naturally.
- If live information is required and no live data source is available,
  do not make up information.
"""

    # PDF / RAG instructions
    if context:
        system_prompt += f"""

The user has uploaded a document.

Use the following retrieved document context when it is relevant
to the user's question.

DOCUMENT CONTEXT:
-----------------
{context}
-----------------

Instructions for document questions:
- Answer using the provided document context.
- Do not invent information that is not supported by the context.
- If the answer cannot be found in the provided context, say that
  the information was not found in the uploaded document.
- The context contains SOURCE and PAGE information.
- When answering from the document, cite the source filename and page number.
- Add a "Sources" section at the end of the answer.
- Do not cite a source unless that source appears in the retrieved context.
- Do not invent page numbers or filenames.
"""

    # Response formatting instructions
    system_prompt += """
Response formatting instructions:

- Give answers in a clean, structured and easy-to-read format.
- Start with a short introduction.
- Use clear headings and subheadings.
- Explain one topic at a time.
- Use numbered lists for multiple topics.
- Use bullet points for key points.
- Keep paragraphs short.
- Add simple examples whenever useful.
- For technical topics, explain the concept first in simple words,
  then provide the technical explanation.
- Do not write everything as one large paragraph.
- Use Markdown formatting.
- Use **bold** only for important terms.
- If explaining an uploaded document, organize the answer according
  to the topics found in the document.
"""

    # Ask Gemini
    response = llm.invoke([
        ("system", system_prompt),
        ("human", question)
    ])

    return response.content


def preprocess_image(image_path):

    image = cv2.imread(image_path)

    if image is None:
        raise ValueError("Unable to read image")

    # Resize very large images
    height, width = image.shape[:2]

    max_width = 1600

    if width > max_width:
        scale = max_width / width

        image = cv2.resize(
            image,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA
        )

    # Reduce noise
    processed = cv2.bilateralFilter(
        image,
        5,
        50,
        50
    )

    # Slight sharpening
    blurred = cv2.GaussianBlur(
        processed,
        (0, 0),
        1.0
    )

    processed = cv2.addWeighted(
        processed,
        1.4,
        blurred,
        -0.4,
        0
    )

    # Create processed images folder
    os.makedirs(
        "processed_images",
        exist_ok=True
    )

    filename = os.path.basename(image_path)
    name, _ = os.path.splitext(filename)

    processed_path = os.path.join(
        "processed_images",
        f"{name}_processed.jpg"
    )

    # Save processed image
    success = cv2.imwrite(
        processed_path,
        processed
    )

    if not success:
        raise ValueError(
            "Unable to save processed image"
        )

    return processed_path


def analyze_image(image_path, question="Analyze this image"):

    # OpenCV preprocessing
    processed_path = preprocess_image(
        image_path
    )

    with open(processed_path, "rb") as image_file:
        image_bytes = image_file.read()

    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    extension = os.path.splitext(
    processed_path
    )[1].lower()

    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }

    mime_type = mime_types.get(extension, "image/jpeg")

    message = {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": question
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_base64}"
                }
            }
        ]
    }

    response = llm.invoke([message])

    return response.content