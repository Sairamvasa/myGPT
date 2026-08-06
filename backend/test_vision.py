import os

print("Current Folder:", os.getcwd())
print("Image Exists:", os.path.exists("uploads/test.jpg"))
from vision import analyze_image

answer = analyze_image(
    "uploads/test.jpg",
    "Explain everything in this image."
)

print(answer)
