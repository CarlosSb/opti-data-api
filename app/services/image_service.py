from __future__ import annotations

import base64
import io

from fastapi import UploadFile
from PIL import Image

from app.core.config import Settings
from app.schemas import ImageOptimizationResponse, ImageOutputFormat
from app.services.ocr_service import read_image_upload


CONTENT_TYPES = {
    ImageOutputFormat.jpeg: "image/jpeg",
    ImageOutputFormat.png: "image/png",
    ImageOutputFormat.webp: "image/webp",
}


def _resize_to_max_width(image: Image.Image, max_width: int) -> Image.Image:
    if image.width <= max_width:
        return image

    ratio = max_width / image.width
    next_height = max(1, int(image.height * ratio))
    return image.resize((max_width, next_height), Image.Resampling.LANCZOS)


def encode_image(image: Image.Image, output_format: ImageOutputFormat, quality: int) -> bytes:
    buffer = io.BytesIO()
    save_format = "JPEG" if output_format == ImageOutputFormat.jpeg else output_format.value.upper()
    save_kwargs: dict[str, int | bool] = {}

    if output_format in {ImageOutputFormat.jpeg, ImageOutputFormat.webp}:
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True

    if output_format == ImageOutputFormat.jpeg:
        image = image.convert("RGB")

    image.save(buffer, format=save_format, **save_kwargs)
    return buffer.getvalue()


async def optimize_image_upload(
    file: UploadFile,
    settings: Settings,
    max_width: int,
    quality: int,
    output_format: ImageOutputFormat,
) -> ImageOptimizationResponse:
    contents, image = await read_image_upload(file, settings)
    optimized_image = _resize_to_max_width(image, max_width)
    optimized_bytes = encode_image(optimized_image, output_format, quality)

    base_name = file.filename.rsplit(".", 1)[0] if file.filename else "image"
    filename = f"{base_name}.{output_format.value}"

    return ImageOptimizationResponse(
        filename=filename,
        content_type=CONTENT_TYPES[output_format],
        width=optimized_image.width,
        height=optimized_image.height,
        original_size_bytes=len(contents),
        optimized_size_bytes=len(optimized_bytes),
        image_base64=base64.b64encode(optimized_bytes).decode("utf-8"),
    )
