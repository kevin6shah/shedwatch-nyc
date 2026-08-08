from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


NormalizedCoordinate = Annotated[int, Field(ge=0, le=1000)]


class PermitFinding(StrEnum):
    VALID_PERMIT = "valid_permit"
    PERMIT_NEARBY_UNVERIFIED = "permit_nearby_unverified"
    NO_CURRENT_PERMIT = "no_current_permit_found"
    LOCATION_UNRESOLVED = "location_unresolved"


class ReviewDecision(StrEnum):
    PENDING = "pending"
    APPROVE = "approve"
    DISMISS = "dismiss"


class BoundingBox(BaseModel):
    ymin: NormalizedCoordinate
    xmin: NormalizedCoordinate
    ymax: NormalizedCoordinate
    xmax: NormalizedCoordinate

    @model_validator(mode="after")
    def validate_order(self) -> "BoundingBox":
        if self.ymax <= self.ymin or self.xmax <= self.xmin:
            raise ValueError("bounding box maximums must exceed minimums")
        return self


class Detection(BaseModel):
    shed_visible: bool
    box: BoundingBox | None = None
    confidence: float = Field(ge=0, le=1)
    structure_type: str
    side_of_image: str
    visual_reason: str
    provider: str = "gemini-3.6-flash"
    verification_passes: int = Field(default=1, ge=1)
    confirmation_confidence: float | None = Field(default=None, ge=0, le=1)
    confirmation_reason: str | None = None

    @model_validator(mode="after")
    def visible_requires_box(self) -> "Detection":
        if self.shed_visible and self.box is None:
            raise ValueError("a visible shed requires a bounding box")
        return self


class GeminiVisionResult(BaseModel):
    detections: list[Detection]


class FrameScreenResult(BaseModel):
    image_index: int = Field(ge=1)
    classification: Literal["likely_shed", "possible_shed", "no_shed"]
    confidence: float = Field(ge=0, le=1)
    reason: str


class BatchScreenResult(BaseModel):
    results: list[FrameScreenResult]


class AdversarialVisionCheck(BaseModel):
    confirmed: bool
    confidence: float = Field(ge=0, le=1)
    visible_overhead_deck: bool
    visible_support_posts: bool
    suitable_street_level_view: bool
    reason: str


class CameraFrame(BaseModel):
    camera_id: str
    camera_name: str
    latitude: float
    longitude: float
    facing: str | None = None
    observed_at: datetime
    image_path: str
    live_image_url: str


class PermitRecord(BaseModel):
    permit_id: str
    source: Literal["dob_now", "legacy", "active_registry"]
    work_type: str
    status: str
    issued_date: date | None = None
    expiration_date: date | None = None
    job_filing_number: str | None = None
    address: str | None = None
    borough: str | None = None
    bin_id: str | None = None
    bbl: str | None = None
    permittee: str | None = None
    record_url: str | None = None


class EvidenceLink(BaseModel):
    label: str
    url: str
    description: str


class PermitEvidence(BaseModel):
    checked_on: date
    finding: PermitFinding
    latest_record: PermitRecord | None = None
    current_permit: PermitRecord | None = None
    records_checked: int = Field(ge=0)
    sources: list[str]
    explanation: str
    records: list[PermitRecord] = Field(default_factory=list)
    source_links: list[EvidenceLink] = Field(default_factory=list)
    active_registry_checked: bool = False
    active_registry_matches: int = Field(default=0, ge=0)
    nearest_active_permit_m: float | None = Field(default=None, ge=0)
    verification_rule: str = (
        "A visible shed is a permit gap only when its frontage is resolved and no "
        "unexpired, non-signed-off shed permit or daily active-registry entry matches that lot."
    )


class LotMatch(BaseModel):
    bbl: str
    bin_ids: list[str]
    address: str
    address_aliases: list[str] = Field(default_factory=list)
    latitude: float
    longitude: float
    distance_from_camera_m: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    method: str


class ReviewCase(BaseModel):
    case_id: str
    title: str
    status: PermitFinding
    frame: CameraFrame
    detection: Detection
    lot: LotMatch
    permit_evidence: PermitEvidence
    ecb_context: str
    reasons: list[str]
    reviewer_questions: list[str]
    decision: ReviewDecision = ReviewDecision.PENDING
    review_note: str | None = None
    reviewed_at: datetime | None = None
    is_control: bool = False


class SnapshotMetrics(BaseModel):
    cameras_available: int = Field(ge=0)
    cameras_in_radius: int = Field(ge=0)
    frames_matched: int = Field(ge=0)
    sheds_detected: int = Field(ge=0)
    permit_gaps: int = Field(ge=0)
    controls: int = Field(ge=0)
    permit_nearby: int = Field(default=0, ge=0)
    unresolved: int = Field(default=0, ge=0)


class ScanSnapshot(BaseModel):
    project_name: str = "Shedwatch NYC"
    generated_at: datetime
    observed_at: datetime
    center_latitude: float
    center_longitude: float
    radius_m: int
    scope: Literal["one_mile", "citywide"] = "one_mile"
    model_provider: str
    snapshot_mode: str
    metrics: SnapshotMetrics
    cases: list[ReviewCase]


class DecisionRequest(BaseModel):
    decision: Literal["approve", "dismiss"]
    note: str | None = Field(default=None, max_length=500)


class DecisionResponse(BaseModel):
    case_id: str
    decision: ReviewDecision
    note: str | None
    reviewed_at: datetime
