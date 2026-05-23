from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ImageSource(str, Enum):
    ocr = "ocr"
    llm = "llm"


class PrescriptionEyeData(BaseModel):
    spherical: Optional[str] = None
    cylindrical: Optional[str] = None
    axis: Optional[str] = None
    addition: Optional[str] = None
    dnp: Optional[str] = None
    height: Optional[str] = None
    spherical_value: Optional[float] = None
    cylindrical_value: Optional[float] = None
    axis_value: Optional[int] = None
    addition_value: Optional[float] = None
    dnp_value: Optional[float] = None
    height_value: Optional[float] = None


class PrescriptionData(BaseModel):
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    crm: Optional[str] = None
    date: Optional[str] = None
    right_eye: PrescriptionEyeData = Field(default_factory=PrescriptionEyeData)
    left_eye: PrescriptionEyeData = Field(default_factory=PrescriptionEyeData)
    contact_lens_base_curve: Optional[str] = None
    contact_lens_diameter: Optional[str] = None
    contact_lens_replacement: Optional[str] = None
    contact_lens_quantity: Optional[str] = None
    contact_lens_dominant_eye: Optional[str] = None
    notes: List[str] = Field(default_factory=list)
    validation_issues: List[str] = Field(default_factory=list)


class ImageProcessResponse(BaseModel):
    text: str
    source: ImageSource
    confidence: float
    message: str
    prescription: Optional[PrescriptionData] = None
    extracted_data: Dict[str, str] = Field(default_factory=dict)
    field_confidence: Dict[str, float] = Field(default_factory=dict)


class ImageOutputFormat(str, Enum):
    jpeg = "jpeg"
    png = "png"
    webp = "webp"


class ImageOptimizationResponse(BaseModel):
    filename: str
    content_type: str
    width: int
    height: int
    original_size_bytes: int
    optimized_size_bytes: int
    image_base64: str


class ImagePreprocessMode(str, Enum):
    document = "document"
    ocr = "ocr"
    clean = "clean"


class ImagePreprocessResponse(BaseModel):
    filename: str
    content_type: str
    width: int
    height: int
    operations: List[str]
    image_base64: str


class SvgExportMode(str, Enum):
    embedded = "embedded"
    card = "card"
    vector = "vector"


class SvgExportResponse(BaseModel):
    filename: str
    mode: SvgExportMode
    width: int
    height: int
    source: str
    svg: str
    text: Optional[str] = None
    prescription: Optional[PrescriptionData] = None
    paths_count: Optional[int] = None


class BatchImageResult(BaseModel):
    filename: str
    ok: bool
    result: Optional[ImageProcessResponse] = None
    error: Optional[str] = None


class BatchImageProcessResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    results: List[BatchImageResult]


class NormalizedCustomer(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    cpf: Optional[str] = None
    birth_date: Optional[str] = None
    address: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)


class CustomerImportSummary(BaseModel):
    total_rows: int
    imported_rows: int
    skipped_rows: int
    columns: List[str]
    mapped_columns: Dict[str, str]
    warnings: List[str] = Field(default_factory=list)


class CustomerImportResponse(BaseModel):
    summary: CustomerImportSummary
    customers: List[NormalizedCustomer]


class HealthResponse(BaseModel):
    status: str
    name: str
    version: str


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class JobAcceptedResponse(BaseModel):
    job_id: str
    status: JobStatus
    type: str
    created_at: datetime
    callback_url: Optional[str] = None


class JobRecord(BaseModel):
    job_id: str
    type: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    callback_url: Optional[str] = None
    tenant_id: Optional[str] = None
    correlation_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class JobWebhookEvent(BaseModel):
    event: str
    event_id: str
    occurred_at: datetime
    source: str = "opti-data-api"
    job_id: str
    type: str
    status: JobStatus
    tenant_id: Optional[str] = None
    correlation_id: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
