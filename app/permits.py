from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx

from app.models import EvidenceLink, PermitEvidence, PermitFinding, PermitRecord


DOB_NOW_URL = "https://data.cityofnewyork.us/resource/rbx6-tga4.json"
LEGACY_URL = "https://data.cityofnewyork.us/resource/ipu4-2q9a.json"
ECB_URL = "https://data.cityofnewyork.us/resource/6bgk-3dad.json"
ACTIVE_SHEDS_URL = "https://nycdob.github.io/ActiveShedPermits/data/Active_Sheds2.csv"
ACTIVE_SHEDS_MAP_URL = "https://www.nyc.gov/assets/buildings/html/sidewalk-shed-map.html"
DOB_NOW_DATASET_URL = (
    "https://data.cityofnewyork.us/Housing-Development/"
    "DOB-NOW-Build-Approved-Permits/rbx6-tga4"
)
LEGACY_DATASET_URL = (
    "https://data.cityofnewyork.us/Housing-Development/"
    "DOB-Permit-Issuance/ipu4-2q9a"
)


@dataclass(frozen=True)
class ActiveShedPermit:
    job_number: str
    borough: str
    address: str
    expiration_date: date | None
    bin_id: str
    block: str
    lot: str
    latitude: float
    longitude: float
    applicant: str

    @property
    def bbl(self) -> str:
        borough_digit = {
            "MANHATTAN": "1",
            "BRONX": "2",
            "BROOKLYN": "3",
            "QUEENS": "4",
            "STATEN ISLAND": "5",
        }.get(self.borough.upper(), "")
        if not borough_digit:
            return ""
        return f"{borough_digit}{int(self.block):05d}{int(self.lot):04d}"

    def as_permit_record(self) -> PermitRecord:
        return PermitRecord(
            permit_id=self.job_number,
            job_filing_number=self.job_number,
            source="active_registry",
            work_type="Sidewalk Shed",
            status="Listed in DOB Active Sidewalk Shed Permits",
            expiration_date=self.expiration_date,
            address=self.address,
            borough=self.borough,
            bin_id=self.bin_id,
            bbl=self.bbl or None,
            permittee=self.applicant or None,
            record_url=ACTIVE_SHEDS_MAP_URL,
        )


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
        records=ordered,
    )


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def filtered_url(base_url: str, where: str) -> str:
    return str(httpx.URL(base_url).copy_merge_params({"$where": where, "$limit": "5000"}))


def query_links(modern_where: str, legacy_where: str) -> list[EvidenceLink]:
    return [
        EvidenceLink(
            label="Daily active shed map",
            url=ACTIVE_SHEDS_MAP_URL,
            description="DOB's daily citywide registry of currently active sidewalk shed permits.",
        ),
        EvidenceLink(
            label="Exact DOB NOW query",
            url=filtered_url(DOB_NOW_URL, modern_where),
            description="The exact machine-readable DOB NOW rows checked for the matched BIN.",
        ),
        EvidenceLink(
            label="DOB NOW dataset",
            url=DOB_NOW_DATASET_URL,
            description="Official NYC Open Data source and field definitions.",
        ),
        EvidenceLink(
            label="Exact legacy permit query",
            url=filtered_url(LEGACY_URL, legacy_where),
            description="The exact machine-readable BIS-era shed/scaffold rows checked for the matched BIN.",
        ),
        EvidenceLink(
            label="Legacy permit dataset",
            url=LEGACY_DATASET_URL,
            description="Official NYC Open Data source and field definitions.",
        ),
    ]


class PermitClient:
    def __init__(self, timeout: float = 20) -> None:
        self.timeout = timeout
        self._active_sheds: list[ActiveShedPermit] | None = None

    async def records_for_lot(
        self, block: str, lot: str, bin_ids: list[str], borough: str | None = None
    ) -> list[PermitRecord]:
        quoted_bins = ",".join(f'"{value}"' for value in bin_ids)
        modern_where = (
            f"bin in({quoted_bins}) "
            'and work_type in("Sidewalk Shed","Supported Scaffold")'
        )
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

    async def active_sheds(self) -> list[ActiveShedPermit]:
        if self._active_sheds is not None:
            return self._active_sheds
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(ACTIVE_SHEDS_URL)
            response.raise_for_status()
        rows: list[ActiveShedPermit] = []
        for row in csv.DictReader(io.StringIO(response.text)):
            try:
                rows.append(
                    ActiveShedPermit(
                        job_number=row["Job Number"],
                        borough=row["Borough Name"],
                        address=f'{row["House Number"]} {row["Street Name"]}'.strip(),
                        expiration_date=parse_date(row.get("Permit Expiration Date")),
                        bin_id=row["BIN Number"],
                        block=row["Block"],
                        lot=row["Lot"],
                        latitude=float(row["Latitude Point"]),
                        longitude=float(row["Longitude Point"]),
                        applicant=row.get("Applicant Business Name", ""),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        self._active_sheds = rows
        return rows

    async def nearby_active_sheds(
        self, latitude: float, longitude: float, radius_m: float = 120
    ) -> list[tuple[float, ActiveShedPermit]]:
        matches = [
            (distance_m(latitude, longitude, row.latitude, row.longitude), row)
            for row in await self.active_sheds()
        ]
        return sorted((item for item in matches if item[0] <= radius_m), key=lambda item: item[0])

    async def evidence_for_lot(
        self,
        block: str,
        lot: str,
        bin_ids: list[str],
        observed_on: date,
        borough: str | None = None,
    ) -> PermitEvidence:
        records = await self.records_for_lot(block, lot, bin_ids, borough)
        evidence = evaluate_permits(records, observed_on)
        active_matches = [row for row in await self.active_sheds() if row.bin_id in bin_ids]
        quoted_bins = ",".join(f'"{value}"' for value in bin_ids)
        modern_where = (
            f"bin in({quoted_bins}) "
            'and work_type in("Sidewalk Shed","Supported Scaffold")'
        )
        legacy_where = (
            f"bin__ in({quoted_bins}) and upper(permit_subtype) in(\"SH\",\"SF\")"
        )
        evidence.source_links = query_links(modern_where, legacy_where)
        evidence.active_registry_checked = True
        evidence.active_registry_matches = len(active_matches)
        evidence.sources.insert(0, "DOB Active Sidewalk Shed Permits (daily)")
        if active_matches:
            registry_records = [row.as_permit_record() for row in active_matches]
            evidence.records = registry_records + evidence.records
            evidence.records_checked += len(registry_records)
            if not evidence.current_permit:
                evidence.current_permit = registry_records[0]
                evidence.finding = PermitFinding.VALID_PERMIT
            active = registry_records[0]
            evidence.explanation = (
                f"Active DOB registry match {active.permit_id} at {active.address}; "
                f"registry expiration {active.expiration_date or 'not supplied'}. "
                f"{evidence.explanation}"
            )
        else:
            evidence.explanation = (
                "No matching BIN appears in DOB's daily Active Sidewalk Shed Permits registry. "
                f"{evidence.explanation}"
            )
        return evidence


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
    permit_id = row.get("work_permit") or row.get("job_filing_number") or "unknown"
    issued = row.get("issued_date")
    exact_where = f'work_permit="{permit_id}"'
    if issued:
        exact_where += f' and issued_date="{issued}"'
    return PermitRecord(
        permit_id=permit_id,
        source="dob_now",
        work_type=row.get("work_type", "Sidewalk Shed"),
        status=row.get("permit_status", "unknown"),
        issued_date=parse_date(row.get("issued_date")),
        expiration_date=parse_date(row.get("expired_date")),
        job_filing_number=row.get("job_filing_number"),
        address=f'{row.get("house_no", "")} {row.get("street_name", "")}'.strip() or None,
        borough=row.get("borough"),
        bin_id=row.get("bin"),
        bbl=row.get("bbl"),
        permittee=row.get("applicant_business_name"),
        record_url=filtered_url(DOB_NOW_URL, exact_where),
    )


def _legacy_record(row: dict[str, Any]) -> PermitRecord:
    permit_id = row.get("job__", "unknown")
    exact_where = f'job__="{permit_id}" and permit_subtype="{row.get("permit_subtype", "SH")}"'
    return PermitRecord(
        permit_id=permit_id,
        source="legacy",
        work_type={"SH": "Sidewalk Shed", "SF": "Supported Scaffold"}.get(
            row.get("permit_subtype"), row.get("permit_subtype", "unknown")
        ),
        status=row.get("permit_status", "unknown"),
        issued_date=parse_date(row.get("issuance_date")),
        expiration_date=parse_date(row.get("expiration_date")),
        job_filing_number=permit_id,
        address=f'{row.get("house__", "")} {row.get("street_name", "")}'.strip() or None,
        borough=row.get("borough"),
        bin_id=row.get("bin__"),
        bbl=row.get("bbl"),
        permittee=row.get("permittee_s_business_name"),
        record_url=filtered_url(LEGACY_URL, exact_where),
    )
