import io
import re
from typing import Any, Dict, List, Optional
import fitz
from PIL import Image


def clean_text(text: str) -> str:
    text = re.sub(r"^\s*y\s*$", "•", text, flags=re.MULTILINE)

    replacements = {
        "\x07": "•",
        "\uf0b7": "•",
    }
    for symbol, replacement in replacements.items():
        text = text.replace(symbol, replacement)

    return text

# function to extract text and images based on certain rules
def extract_content(file_path: str, output_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Extract text and image data from a PDF without writing to SQLite or folders."""
    try:
        document = fitz.open(file_path)
    except Exception as exc:
        raise RuntimeError(f"Unable to open PDF: {exc}") from exc

    pages: List[Dict[str, Any]] = []

    try:
        for page in document:
            page_text = ""
            blocks = page.get_text("blocks")
            for block in blocks:
                text = clean_text(block[4])
                if text:
                    page_text += text + "\n"

            extracted_images: List[Dict[str, Any]] = []
            for _, image_info in enumerate(page.get_images(), start=1):
                xref = image_info[0]
                image_data = document.extract_image(xref)
                if not image_data:
                    continue

                image_bytes = image_data.get("image")
                if not image_bytes:
                    continue

                width = image_data.get("width", 0)
                height = image_data.get("height", 0)
                extension = image_data.get("ext", "png")
                aspect_ratio = width / height if height > 0 else 0
                if (width < 400 or height < 400) or aspect_ratio > 5 or aspect_ratio < 0.2:
                    continue

                pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                extrema = pil_image.getextrema()
                is_black = all(ch[1] == 0 for ch in extrema)
                is_white = all(ch[0] == 255 for ch in extrema)
                if is_black or is_white:
                    continue

                extracted_images.append({
                    "extension": extension,
                    "bytes": image_bytes,
                })

            pages.append({
                "page_number": page.number,
                "text": page_text.strip(),
                "images": extracted_images,
            })
    finally:
        document.close()

    return pages