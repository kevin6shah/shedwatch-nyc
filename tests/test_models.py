from datetime import date

import pytest
from pydantic import ValidationError

from app.models import BoundingBox, Detection, PermitFinding, PermitRecord
from app.permits import evaluate_permits


def test_bounding_box_rejects_out_of_range_coordinates():
    with pytest.raises(ValidationError):
        BoundingBox(ymin=0, xmin=0, ymax=1001, xmax=500)


def test_bounding_box_rejects_reversed_coordinates():
    with pytest.raises(ValidationError):
        BoundingBox(ymin=500, xmin=100, ymax=400, xmax=600)


def test_visible_detection_requires_box():
    with pytest.raises(ValidationError):
        Detection(
            shed_visible=True,
            confidence=0.8,
            structure_type="sidewalk shed",
            side_of_image="left",
            visual_reason="posts and deck",
        )


def test_expired_permit_becomes_review_candidate():
    evidence = evaluate_permits(
        [
            PermitRecord(
                permit_id="OLD-SH",
                source="dob_now",
                work_type="Sidewalk Shed",
                status="Permit Issued",
                issued_date=date(2022, 1, 1),
                expiration_date=date(2023, 1, 1),
            )
        ],
        date(2026, 8, 7),
    )
    assert evidence.finding == PermitFinding.NO_CURRENT_PERMIT
    assert evidence.current_permit is None


def test_signed_off_permit_is_not_current_even_with_future_date():
    evidence = evaluate_permits(
        [
            PermitRecord(
                permit_id="SIGNED-OFF",
                source="dob_now",
                work_type="Sidewalk Shed",
                status="Signed-off",
                expiration_date=date(2027, 1, 1),
            )
        ],
        date(2026, 8, 7),
    )
    assert evidence.finding == PermitFinding.NO_CURRENT_PERMIT


def test_current_permit_is_valid_control():
    evidence = evaluate_permits(
        [
            PermitRecord(
                permit_id="CURRENT-SH",
                source="dob_now",
                work_type="Sidewalk Shed",
                status="Permit Issued",
                expiration_date=date(2026, 12, 31),
            )
        ],
        date(2026, 8, 7),
    )
    assert evidence.finding == PermitFinding.VALID_PERMIT
    assert evidence.current_permit is not None
