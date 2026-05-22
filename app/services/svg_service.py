from __future__ import annotations

import base64
import html
import textwrap

from PIL import Image

from app.schemas import PrescriptionData, SvgExportMode, SvgExportResponse


def _svg_text(value: str) -> str:
    return html.escape(value, quote=True)


def _wrap_lines(text: str, width: int = 82) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return ["Sem texto extraido."]
    return textwrap.wrap(normalized, width=width) or ["Sem texto extraido."]


def build_embedded_image_svg(
    contents: bytes,
    image: Image.Image,
    content_type: str,
    filename: str = "image.svg",
) -> SvgExportResponse:
    image_base64 = base64.b64encode(contents).decode("utf-8")
    width = image.width
    height = image.height
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">'
        f'<image href="data:{content_type};base64,{image_base64}" width="{width}" height="{height}" />'
        "</svg>"
    )

    return SvgExportResponse(
        filename=filename,
        mode=SvgExportMode.embedded,
        width=width,
        height=height,
        source="image",
        svg=svg,
    )


def build_vectorized_image_svg(
    image: Image.Image,
    filename: str = "vector.svg",
    threshold: int = 180,
    simplify: float = 0.01,
    min_area: int = 24,
    max_paths: int = 600,
) -> SvgExportResponse:
    import cv2
    import numpy as np

    rgb_image = image.convert("RGB")
    width = rgb_image.width
    height = rgb_image.height
    gray = cv2.cvtColor(np.array(rgb_image), cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(blurred, threshold, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    paths: list[str] = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        if len(paths) >= max_paths:
            break
        area = cv2.contourArea(contour)
        if area < min_area:
            continue

        epsilon = max(0.5, simplify * cv2.arcLength(contour, True))
        points = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
        if len(points) < 3:
            continue

        commands = [f"M {int(points[0][0])} {int(points[0][1])}"]
        commands.extend(f"L {int(point[0])} {int(point[1])}" for point in points[1:])
        commands.append("Z")
        paths.append(f'<path d="{" ".join(commands)}"/>')

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <g fill="#111827" stroke="none">
    {"".join(paths)}
  </g>
</svg>"""

    return SvgExportResponse(
        filename=filename,
        mode=SvgExportMode.vector,
        width=width,
        height=height,
        source="vectorized-image",
        svg=svg,
        paths_count=len(paths),
    )


def build_text_card_svg(
    text: str,
    prescription: PrescriptionData | None = None,
    title: str = "Receita oftalmologica",
    filename: str = "ocr-card.svg",
) -> SvgExportResponse:
    width = 960
    lines = _wrap_lines(text)
    metadata_lines = _prescription_summary_lines(prescription)
    height = 190 + (len(metadata_lines) * 28) + (len(lines) * 24)

    text_nodes = []
    y = 150
    for label in metadata_lines:
        text_nodes.append(
            f'<text x="48" y="{y}" font-size="18" fill="#334155">{_svg_text(label)}</text>'
        )
        y += 28

    if metadata_lines:
        y += 12

    for line in lines:
        text_nodes.append(
            f'<text x="48" y="{y}" font-size="17" fill="#475569">{_svg_text(line)}</text>'
        )
        y += 24

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">
  <rect width="100%" height="100%" rx="28" fill="#f8fafc"/>
  <rect x="28" y="28" width="{width - 56}" height="{height - 56}" rx="24" fill="#ffffff" stroke="#e2e8f0"/>
  <rect x="48" y="54" width="64" height="6" rx="3" fill="#0ea5e9"/>
  <text x="48" y="104" font-size="30" font-family="Inter, Arial, sans-serif" font-weight="700" fill="#0f172a">{_svg_text(title)}</text>
  <text x="48" y="130" font-size="15" font-family="Inter, Arial, sans-serif" fill="#64748b">Gerado pelo OptiProcess API</text>
  <g font-family="Inter, Arial, sans-serif">
    {"".join(text_nodes)}
  </g>
</svg>"""

    return SvgExportResponse(
        filename=filename,
        mode=SvgExportMode.card,
        width=width,
        height=height,
        source="ocr" if prescription else "text",
        svg=svg,
        text=text,
        prescription=prescription,
    )


def _prescription_summary_lines(prescription: PrescriptionData | None) -> list[str]:
    if not prescription:
        return []

    lines: list[str] = []
    if prescription.patient_name:
        lines.append(f"Paciente: {prescription.patient_name}")
    if prescription.doctor_name or prescription.crm:
        doctor = " ".join(part for part in [prescription.doctor_name, prescription.crm] if part)
        lines.append(f"Medico: {doctor}")
    if prescription.date:
        lines.append(f"Data: {prescription.date}")

    od = _eye_line("OD", prescription.right_eye.spherical, prescription.right_eye.cylindrical, prescription.right_eye.axis)
    oe = _eye_line("OE", prescription.left_eye.spherical, prescription.left_eye.cylindrical, prescription.left_eye.axis)
    if od:
        lines.append(od)
    if oe:
        lines.append(oe)
    return lines


def _eye_line(label: str, spherical: str | None, cylindrical: str | None, axis: str | None) -> str | None:
    parts = []
    if spherical:
        parts.append(f"Esf {spherical}")
    if cylindrical:
        parts.append(f"Cil {cylindrical}")
    if axis:
        parts.append(f"Eixo {axis}")
    if not parts:
        return None
    return f"{label}: " + " | ".join(parts)
