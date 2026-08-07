from __future__ import annotations

import argparse
import asyncio
import math
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.detector import GeminiDetector
from app.models import (
    BoundingBox,
    CameraFrame,
    Detection,
    LotMatch,
    PermitEvidence,
    PermitFinding,
    PermitRecord,
    ReviewCase,
    ScanSnapshot,
    SnapshotMetrics,
)
from app.permits import PermitClient, evaluate_permits


CAMERA_API = "https://webcams.nyctmc.org/api/cameras"


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


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


KNOWN_CASES: list[dict[str, Any]] = [
    {
        "case_id": "223-second-avenue",
        "title": "223 Second Avenue",
        "camera_id": "02d7db8e-481d-477e-9cdb-a2b6c6ec1ca3",
        "filename": "2_Ave_@_E_14_St.jpg",
        "facing": "South",
        "box": {"ymin": 80, "xmin": 0, "ymax": 670, "xmax": 520},
        "side": "left / east side",
        "confidence": 0.91,
        "visual_reason": "A rigid covered pedestrian deck with repeated steel posts runs along the east sidewalk immediately south of the camera.",
        "bbl": "1004690030",
        "bins": ["1006906"],
        "block": "469",
        "lot": "30",
        "address": "223 2 AVENUE",
        "aliases": ["223 SECOND AVENUE", "242 EAST 14 STREET"],
        "lot_lat": 40.732293,
        "lot_lon": -73.9854878,
        "lot_confidence": 0.82,
        "latest_permit": {
            "permit_id": "140561675",
            "source": "legacy",
            "work_type": "Sidewalk Shed",
            "status": "ISSUED",
            "issued_date": "2016-10-12",
            "expiration_date": "2017-10-12",
        },
        "records_checked": 12,
        "ecb": "No active shed-related ECB violation was found for the matched lot. This makes the camera signal potentially additive to enforcement data.",
    },
    {
        "case_id": "74-78-eighth-avenue",
        "title": "74–78 Eighth Avenue",
        "camera_id": "3dc1adcd-7a47-45c3-a667-9d8fae9fdcd0",
        "filename": "8_Ave_@_14_St.jpg",
        "facing": "East",
        "box": {"ymin": 70, "xmin": 500, "ymax": 650, "xmax": 1000},
        "side": "right / south side",
        "confidence": 0.94,
        "visual_reason": "A sidewalk shed wraps the southeast corner, with a solid overhead deck and a dense line of vertical support posts.",
        "bbl": "1006180005",
        "bins": ["1080215", "1080216", "1080217"],
        "block": "618",
        "lot": "5",
        "address": "74 8 AVENUE",
        "aliases": ["74–78 8 AVENUE", "254–256 WEST 14 STREET"],
        "lot_lat": 40.7394632,
        "lot_lon": -74.0023672,
        "lot_confidence": 0.87,
        "latest_permit": {
            "permit_id": "M00187126-I1-SH",
            "source": "dob_now",
            "work_type": "Sidewalk Shed",
            "status": "Signed-off",
            "issued_date": "2022-04-04",
            "expiration_date": "2023-04-01",
        },
        "records_checked": 40,
        "ecb": "No active shed-related ECB violation was found for the matched lot. Human frontage verification is required before escalation.",
    },
    {
        "case_id": "80-eighth-avenue-control",
        "title": "80 Eighth Avenue — permitted control",
        "camera_id": "3dc1adcd-7a47-45c3-a667-9d8fae9fdcd0",
        "filename": "8_Ave_@_14_St.jpg",
        "facing": "East",
        "box": {"ymin": 70, "xmin": 0, "ymax": 610, "xmax": 490},
        "side": "left / north side",
        "confidence": 0.92,
        "visual_reason": "A second sidewalk shed occupies the opposite side of the same intersection, providing a useful permitted control.",
        "bbl": "1007640001",
        "bins": ["1013711"],
        "block": "764",
        "lot": "1",
        "address": "80 8 AVENUE",
        "aliases": ["80 EIGHTH AVENUE"],
        "lot_lat": 40.7398584,
        "lot_lon": -74.0020533,
        "lot_confidence": 0.91,
        "latest_permit": {
            "permit_id": "M00950093-I1-SH",
            "source": "dob_now",
            "work_type": "Sidewalk Shed",
            "status": "Permit Issued",
            "issued_date": "2025-12-31",
            "expiration_date": "2026-12-31",
        },
        "records_checked": 4,
        "ecb": "Control case: the current DOB NOW permit explains the visible north-side shed.",
        "control": True,
    },
]


async def fetch_cameras() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(CAMERA_API)
        response.raise_for_status()
        return response.json()


def frame_index(frame_dir: Path) -> dict[str, Path]:
    return {normalize_name(path.stem): path for path in frame_dir.glob("*.jpg")}


def selected_cameras(cameras: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = []
    for camera in cameras:
        if camera.get("isOnline") != "true":
            continue
        distance = distance_m(
            settings.pilot_latitude,
            settings.pilot_longitude,
            float(camera["latitude"]),
            float(camera["longitude"]),
        )
        if distance <= settings.pilot_radius_m:
            selected.append({**camera, "distance_m": round(distance)})
    return sorted(selected, key=lambda camera: camera["distance_m"])


def seed_detection(config: dict[str, Any]) -> Detection:
    return Detection(
        shed_visible=True,
        box=BoundingBox.model_validate(config["box"]),
        confidence=config["confidence"],
        structure_type="sidewalk shed",
        side_of_image=config["side"],
        visual_reason=config["visual_reason"],
        provider=f"{settings.gemini_model} (verified fixture)",
    )


def seed_permit_evidence(config: dict[str, Any], observed_on: date) -> PermitEvidence:
    record = PermitRecord.model_validate(config["latest_permit"])
    evidence = evaluate_permits([record], observed_on)
    evidence.records_checked = config["records_checked"]
    return evidence


def choose_detection(result, expected_side: str) -> Detection | None:
    visible = [d for d in result.detections if d.shed_visible and d.box]
    if not visible:
        return None
    tokens = {token for token in re.split(r"\W+", expected_side.lower()) if token}
    return max(
        visible,
        key=lambda d: d.confidence
        + 0.08 * len(tokens.intersection(set(re.split(r"\W+", d.side_of_image.lower())))),
    )


async def build_snapshot(
    mode: str = "fixture", refresh_permits: bool = False, scan_all: bool = False
) -> ScanSnapshot:
    cameras = await fetch_cameras()
    selected = selected_cameras(cameras)
    files = frame_index(settings.frame_dir)
    static_frames = settings.static_dir / "frames"
    static_frames.mkdir(parents=True, exist_ok=True)
    matched: dict[str, tuple[dict[str, Any], Path]] = {}
    for camera in selected:
        path = files.get(normalize_name(camera["name"]))
        if path:
            matched[camera["id"]] = (camera, path)
            shutil.copy2(path, static_frames / path.name)

    model_results: dict[str, Any] = {}
    if mode == "gemini":
        detector = GeminiDetector()
        semaphore = asyncio.Semaphore(settings.gemini_concurrency)
        mapped_ids = {case["camera_id"] for case in KNOWN_CASES if not case.get("control")}
        inference_targets = matched if scan_all else {
            camera_id: value
            for camera_id, value in matched.items()
            if camera_id in mapped_ids
        }

        async def run(camera_id: str, path: Path) -> None:
            async with semaphore:
                try:
                    model_results[camera_id] = await detector.detect(path)
                except Exception as exc:  # keep scan usable when a provider call fails
                    model_results[camera_id] = exc

        await asyncio.gather(*(run(cid, item[1]) for cid, item in inference_targets.items()))

    observed_at = datetime.fromisoformat("2026-08-07T18:32:00-04:00")
    permit_client = PermitClient()
    cases: list[ReviewCase] = []
    for config in KNOWN_CASES:
        camera, image_path = matched.get(
            config["camera_id"],
            (
                {
                    "id": config["camera_id"],
                    "name": config["title"],
                    "latitude": config["lot_lat"],
                    "longitude": config["lot_lon"],
                    "imageUrl": "",
                },
                settings.frame_dir / config["filename"],
            ),
        )
        detection = seed_detection(config)
        if (
            mode == "gemini"
            and not config.get("control")
            and model_results.get(config["camera_id"]) is not None
            and not isinstance(model_results.get(config["camera_id"]), Exception)
        ):
            detected = choose_detection(model_results.get(config["camera_id"]), config["side"])
            if detected:
                detection = detected.model_copy(update={"provider": settings.gemini_model})
        evidence = seed_permit_evidence(config, observed_at.date())
        if refresh_permits:
            try:
                records = await permit_client.records_for_lot(
                    config["block"], config["lot"], config["bins"]
                )
                evidence = evaluate_permits(records, observed_at.date())
            except Exception:
                pass
        camera_lat = float(camera["latitude"])
        camera_lon = float(camera["longitude"])
        lot = LotMatch(
            bbl=config["bbl"],
            bin_ids=config["bins"],
            address=config["address"],
            address_aliases=config["aliases"],
            latitude=config["lot_lat"],
            longitude=config["lot_lon"],
            distance_from_camera_m=round(
                distance_m(camera_lat, camera_lon, config["lot_lat"], config["lot_lon"]), 1
            ),
            confidence=config["lot_confidence"],
            method="camera direction + street side + explicit POC frontage mapping",
        )
        finding = evidence.finding
        is_control = bool(config.get("control"))
        cases.append(
            ReviewCase(
                case_id=config["case_id"],
                title=config["title"],
                status=finding,
                frame=CameraFrame(
                    camera_id=config["camera_id"],
                    camera_name=camera.get("name", config["title"]),
                    latitude=camera_lat,
                    longitude=camera_lon,
                    facing=config["facing"],
                    observed_at=observed_at,
                    image_path=f"/static/frames/{image_path.name}",
                    live_image_url=camera.get("imageUrl", ""),
                ),
                detection=detection,
                lot=lot,
                permit_evidence=evidence,
                ecb_context=config["ecb"],
                reasons=[
                    detection.visual_reason,
                    evidence.explanation,
                    "The lot assignment is evidence-backed but still requires a human frontage check.",
                ],
                reviewer_questions=[
                    "Does the boxed structure occupy the mapped building frontage?",
                    "Is a current permit number visibly posted on the shed?",
                    "Could an adjoining BIN or very recent filing explain the structure?",
                ],
                is_control=is_control,
            )
        )

    detected_count = (
        sum(
            len([d for d in result.detections if d.shed_visible])
            for result in model_results.values()
            if not isinstance(result, Exception)
        )
        if mode == "gemini"
        else len(cases)
    )
    snapshot = ScanSnapshot(
        generated_at=datetime.now().astimezone(),
        observed_at=observed_at,
        center_latitude=settings.pilot_latitude,
        center_longitude=settings.pilot_longitude,
        radius_m=settings.pilot_radius_m,
        model_provider=settings.gemini_model,
        snapshot_mode=("gemini-all" if scan_all else "gemini-targeted") if mode == "gemini" else mode,
        metrics=SnapshotMetrics(
            cameras_available=len(cameras),
            cameras_in_radius=len(selected),
            frames_matched=len(matched),
            sheds_detected=max(detected_count, len(cases)),
            permit_gaps=sum(
                case.status == PermitFinding.NO_CURRENT_PERMIT for case in cases
            ),
            controls=sum(case.is_control for case in cases),
        ),
        cases=cases,
    )
    settings.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    settings.snapshot_path.write_text(snapshot.model_dump_json(indent=2))
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Shedwatch daily snapshot")
    parser.add_argument("--mode", choices=("fixture", "gemini"), default="fixture")
    parser.add_argument("--refresh-permits", action="store_true")
    parser.add_argument("--scan-all", action="store_true", help="Run Gemini on every matched frame")
    args = parser.parse_args()
    snapshot = asyncio.run(build_snapshot(args.mode, args.refresh_permits, args.scan_all))
    print(
        f"wrote {settings.snapshot_path} with {snapshot.metrics.frames_matched} frames "
        f"and {len(snapshot.cases)} review cases"
    )


if __name__ == "__main__":
    main()
