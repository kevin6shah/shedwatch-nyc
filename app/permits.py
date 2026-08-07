from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx

from app.models import PermitEvidence, PermitFinding, PermitRecord


DOB_NOW_URL = "https://data.cityofnewyork.us/resource/rbx6-tga4.json"
LEGACY_URL = "https://data.cityofnewyork.us/resource/ipu4-2q9a.json"
ECB_URL = "https://data.cityofnewyork.us/resource/6bgk-3dad.json"


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for pattern in ("%Y-%m-%dT%H:%M:%S.%f", "%m/%d/%Y", "%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def is_current(record: PermitRecord, observed_on: date) -> bool:
    invalid_statuses = {"signed-off", "expired", "revoked", "withdrawn"}
    return bool(
        record.expiration_date
        and record.expiration_date >= observed_on
        and record.status.strip().lower() not in invalid_statuses
    )


def evaluate_permits(records: list[PermitRecord], observed_on: date) -> PermitEvidence:
    ordered = sorted(
        records,
        key=lambda row: (row.issued_date or date.min, row.expiration_date or date.min),
        reverse=True,
    )
    current = next((row for row in ordered if is_current(row, observed_on)), None)
    latest = ordered[0] if ordered else None
    if current:
        explanation = (
            f"Current {current.work_type} permit {current.permit_id} remains valid "
            f"through {current.expiration_date.isoformat()}."
        )
        finding = PermitFinding.VALID_PERMIT
    elif latest and latest.expiration_date:
        explanation = (
            f"No current shed permit found. The newest matching record "
            f"({latest.permit_id}) expired {latest.expiration_date.isoformat()} "
            f"and is marked {latest.status}."
        )
        finding = PermitFinding.NO_CURRENT_PERMIT
    else:
        explanation = "No sidewalk-shed or supported-scaffold permit was found in either permit dataset."
        finding = PermitFinding.NO_CURRENT_PERMIT
    return PermitEvidence(
        checked_on=observed_on,
        finding=finding,
        latest_record=latest,
        current_permit=current,
        records_checked=len(records),
        sources=["DOB NOW Build Approved Permits", "DOB Permit Issuance"],
        explanation=explanation,
    )


class PermitClient:
    def __init__(self, timeout: float = 20) -> None:
        self.timeout = timeout

    async def records_for_lot(
        self, block: str, lot: str, bin_ids: list[str]
    ) -> list[PermitRecord]:
        modern_where = (
            f'borough="MANHATTAN" and block="{int(block)}" and lot="{int(lot)}" '
            'and work_type in("Sidewalk Shed","Supported Scaffold")'
        )
        quoted_bins = ",".join(f'"{value}"' for value in bin_ids)
        legacy_where = (
            f"bin__ in({quoted_bins}) and upper(permit_subtype) in(\"SH\",\"SF\")"
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            modern_response, legacy_response = await asyncio_gather_responses(
                client,
                (DOB_NOW_URL, {"$where": modern_where, "$limit": "5000"}),
                (LEGACY_URL, {"$where": legacy_where, "$limit": "5000"}),
            )
        records: list[PermitRecord] = []
        for row in modern_response.json():
            records.append(_modern_record(row))
        for row in legacy_response.json():
            records.append(_legacy_record(row))
        return records


async def asyncio_gather_responses(
    client: httpx.AsyncClient,
    first: tuple[str, dict[str, str]],
    second: tuple[str, dict[str, str]],
) -> tuple[httpx.Response, httpx.Response]:
    import asyncio

    responses = await asyncio.gather(
        client.get(first[0], params=first[1]),
        client.get(second[0], params=second[1]),
    )
    for response in responses:
        response.raise_for_status()
    return responses[0], responses[1]


def _modern_record(row: dict[str, Any]) -> PermitRecord:
    return PermitRecord(
        permit_id=row.get("work_permit") or row.get("job_filing_number") or "unknown",
        source="dob_now",
        work_type=row.get("work_type", "Sidewalk Shed"),
        status=row.get("permit_status", "unknown"),
        issued_date=parse_date(row.get("issued_date")),
        expiration_date=parse_date(row.get("expired_date")),
    )


def _legacy_record(row: dict[str, Any]) -> PermitRecord:
    return PermitRecord(
        permit_id=row.get("job__", "unknown"),
        source="legacy",
        work_type={"SH": "Sidewalk Shed", "SF": "Supported Scaffold"}.get(
            row.get("permit_subtype"), row.get("permit_subtype", "unknown")
        ),
        status=row.get("permit_status", "unknown"),
        issued_date=parse_date(row.get("issuance_date")),
        expiration_date=parse_date(row.get("expiration_date")),
    )
