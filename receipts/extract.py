import io
import re
import time
from datetime import date
from pathlib import Path

from google import genai
from google.genai import errors, types
from PIL import Image, ImageOps

from .models import Receipt

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
MAX_SIDE_PX = 2000
JPEG_QUALITY = 85
MAX_ATTEMPTS = 5
RETRYABLE_CODES = {429, 500, 503, 504}

PROMPT = """\
The {count} images above are consecutive photos of ONE long paper receipt, in order from top (part 1) to bottom (part {count}).
Neighbouring photos usually overlap, so the same printed lines can appear at the bottom of one photo and the top of the next.

Read the whole receipt and extract it as a single record:
- Stitch the parts together mentally. Every printed line item must appear exactly once; never duplicate lines that are visible in an overlap.
- Keep line items in printed order. Include discount/coupon lines as items with a negative total_price.
- Copy numbers exactly as printed. Do not compute or invent values that are not on the receipt; use null when something is missing or unreadable.
- List each tax separately in taxes, and put the overall tax amount in tax_total.
- Dates: a two-digit year means 20YY. Canadian card terminals often print YY/MM/DD (e.g. "26/09/02" is 2026-09-02).
  Use the date format that gives a plausible date on or before today ({today}); never substitute the current year for a printed one.
"""


def _natural_key(path: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path.name)]


def list_images(folder: Path) -> list[Path]:
    return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS), key=_natural_key)


def _prepare_image(path: Path) -> bytes:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY)
        return buf.getvalue()


def extract_receipt(client: genai.Client, model: str, images: list[Path]) -> Receipt:
    if not images:
        raise ValueError("No images to extract from.")

    contents: list = []
    for i, path in enumerate(images, start=1):
        contents.append(f"Part {i} of {len(images)}:")
        contents.append(types.Part.from_bytes(data=_prepare_image(path), mime_type="image/jpeg"))
    contents.append(PROMPT.format(count=len(images), today=date.today().isoformat()))

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=Receipt,
        temperature=0,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
            break
        except errors.APIError as exc:
            if exc.code not in RETRYABLE_CODES or attempt == MAX_ATTEMPTS:
                raise
            delay = 5 * 2 ** (attempt - 1)
            print(f"  Gemini error {exc.code}, retrying in {delay}s ({attempt}/{MAX_ATTEMPTS - 1})...")
            time.sleep(delay)

    if isinstance(response.parsed, Receipt):
        return response.parsed
    if not response.text:
        raise RuntimeError(f"Gemini returned no content (finish reason: {response.candidates[0].finish_reason if response.candidates else 'unknown'}).")
    return Receipt.model_validate_json(response.text)
