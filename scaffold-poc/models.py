from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ReviewDisposition(StrEnum):
    REJECTED = "rejected"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    HUMAN_CONFIRMED = "human_confirmed"


class CameraObservation(BaseModel):
    camera_id: str
    camera_name: str
    observed_at: datetime
    facing: str
    shed_visible: bool
    confidence: float = Field(ge=0, le=1)
    side_of_view: str
    original_frame_url: str


class LotMatch(BaseModel):
    bbl: str
    bin_ids: list[str]
    address_aliases: list[str]
    distance_from_camera_m: float = Field(ge=0)
    match_confidence: float = Field(ge=0, le=1)


class PermitCheck(BaseModel):
    checked_on: date
    modern_rows_found: int = Field(ge=0)
    latest_shed_permit_id: str | None = None
    latest_expiration: date | None = None
    latest_status: str | None = None
    has_current_permit: bool
    sources: list[str]


class ScaffoldCandidate(BaseModel):
    case_id: str
    observation: CameraObservation
    lot: LotMatch
    permit_check: PermitCheck
    disposition: ReviewDisposition
    reasons: list[str]
    human_review_questions: list[str]


def triage(candidate: ScaffoldCandidate) -> ReviewDisposition:
    """Deterministic guardrail used after the vision/geolocation agents."""
    if not candidate.observation.shed_visible:
        return ReviewDisposition.REJECTED
    if candidate.permit_check.has_current_permit:
        return ReviewDisposition.REJECTED
    return ReviewDisposition.HUMAN_REVIEW_REQUIRED
