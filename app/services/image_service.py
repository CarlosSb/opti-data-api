from __future__ import annotations

import base64
import io

from fastapi import UploadFile
from PIL import Image

from app.core.config import Settings
from app.schemas import ImageOptimizationResponse, ImageOutputFormat, ImagePreprocessMode, ImagePreprocessResponse
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


async def preprocess_image_upload(
    file: UploadFile,
    settings: Settings,
    mode: ImagePreprocessMode,
    max_width: int,
) -> ImagePreprocessResponse:
    contents, image = await read_image_upload(file, settings)
    processed_image, operations = preprocess_image(image, mode, max_width)
    processed_bytes = encode_image(processed_image, ImageOutputFormat.png, quality=95)

    base_name = file.filename.rsplit(".", 1)[0] if file.filename else "image"
    return ImagePreprocessResponse(
        filename=f"{base_name}-preprocessed.png",
        content_type="image/png",
        width=processed_image.width,
        height=processed_image.height,
        operations=operations,
        image_base64=base64.b64encode(processed_bytes).decode("utf-8"),
    )


def preprocess_image(image: Image.Image, mode: ImagePreprocessMode, max_width: int) -> tuple[Image.Image, list[str]]:
    import cv2
    import numpy as np

    operations = ["rgb"]
    resized = _resize_to_max_width(image.convert("RGB"), max_width)
    if resized.size != image.size:
        operations.append(f"resize:{max_width}")

    array = np.array(resized)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    operations.append("grayscale")

    if mode == ImagePreprocessMode.clean:
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        operations.append("denoise")
        enhanced = cv2.equalizeHist(denoised)
        operations.append("equalize-histogram")
        return Image.fromarray(enhanced).convert("RGB"), operations

    if mode == ImagePreprocessMode.ocr:
        denoised = cv2.fastNlMeansDenoising(gray, h=12)
        operations.append("denoise")
        thresholded = cv2.adaptiveThreshold(
            denoised,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        operations.append("adaptive-threshold")
        return Image.fromarray(thresholded).convert("RGB"), operations

    corrected = _deskew(gray)
    if corrected is not gray:
        operations.append("deskew")

    contrasted = cv2.equalizeHist(corrected)
    operations.append("equalize-histogram")
    return Image.fromarray(contrasted).convert("RGB"), operations


def _deskew(gray_image):
    import cv2
    import numpy as np

    inverted = cv2.bitwise_not(gray_image)
    coords = np.column_stack(np.where(inverted > 0))
    if coords.size == 0:
        return gray_image

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    if abs(angle) < 0.5 or abs(angle) > 15:
        return gray_image

    height, width = gray_image.shape[:2]
    center = (width // 2, height // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(gray_image, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
