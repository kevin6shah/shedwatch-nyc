from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.detector import GeminiDetector
from app.models import (
    BoundingBox,
    CameraFrame,
    Detection,
    EvidenceLink,
    LotMatch,
    PermitEvidence,
    PermitFinding,
    ReviewCase,
)
from app.permits import ACTIVE_SHEDS_MAP_URL, ACTIVE_SHEDS_URL, PermitClient, distance_m
from app.scanner import KNOWN_CASES, build_snapshot, fetch_cameras, frame_index, normalize_name


CHECKPOINT_PATH = settings.checkpoint_dir / "citywide-screen.json"
CONFIRMATION_PATH = settings.checkpoint_dir / "citywide-confirmations.json"
BATCH_SIZE = 8
ACTIVE_SEARCH_RADIUS_M = 120


def load_checkpoint() -> dict[str, dict[str, Any]]:
    if not CHECKPOINT_PATH.exists():
        return {}
    try:
        payload = json.loads(CHECKPOINT_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    if payload.get("model") != settings.gemini_model:
        return {}
    return payload.get("results", {})


def save_checkpoint(results: dict[str, dict[str, Any]]) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(
        json.dumps(
            {
                "model": settings.gemini_model,
                "updated_at": datetime.now().astimezone().isoformat(),
                "results": results,
            },
            indent=2,
        )
    )


async def screen_citywide(
    detector: GeminiDetector,
    matched: dict[str, tuple[dict[str, Any], Path]],
    batch_size: int,
) -> dict[str, dict[str, Any]]:
    results = load_checkpoint()
    known_ids = {case["camera_id"] for case in KNOWN_CASES}
    pending = [
        (camera_id, camera, path)
        for camera_id, (camera, path) in matched.items()
        if camera_id not in results and camera_id not in known_ids
    ]
    batches = [pending[index : index + batch_size] for index in range(0, len(pending), batch_size)]
    semaphore = asyncio.Semaphore(settings.gemini_concurrency)
    lock = asyncio.Lock()
    completed = len(results)
    total = len(matched) - len(known_ids.intersection(matched))

    async def run_batch(batch: list[tuple[str, dict[str, Any], Path]]) -> None:
        nonlocal completed
        error: Exception | None = None
        for attempt in range(3):
            try:
                async with semaphore:
                    response = await detector.screen_batch([item[2] for item in batch])
                by_index = {row.image_index: row for row in response.results}
                async with lock:
                    for image_index, (camera_id, camera, path) in enumerate(batch, 1):
                        row = by_index.get(image_index)
                        if not row:
                            continue
                        results[camera_id] = {
                            "camera_name": camera["name"],
                            "filename": path.name,
                            **row.model_dump(),
                        }
                    completed += len(batch)
                    save_checkpoint(results)
                    print(f"citywide screen: {completed}/{total} frames", flush=True)
                return
            except Exception as exc:  # retry transient model/rate failures
                error = exc
                await asyncio.sleep(2**attempt)
        print(f"batch failed after retries: {error}", flush=True)

    await asyncio.gather(*(run_batch(batch) for batch in batches))
    return results


async def verify_candidates(
    detector: GeminiDetector,
    matched: dict[str, tuple[dict[str, Any], Path]],
    screening: dict[str, dict[str, Any]],
) -> dict[str, Detection]:
    candidates = [
        camera_id
        for camera_id, row in screening.items()
        if row["classification"] != "no_shed" and camera_id in matched
    ]
    semaphore = asyncio.Semaphore(settings.gemini_concurrency)
    verified: dict[str, Detection] = {}
    completed = 0

    async def run(camera_id: str) -> None:
        nonlocal completed
        error: Exception | None = None
        for attempt in range(3):
            try:
                async with semaphore:
                    response = await detector.detect(matched[camera_id][1])
                visible = [row for row in response.detections if row.shed_visible and row.box]
                if visible:
                    verified[camera_id] = max(visible, key=lambda row: row.confidence)
                completed += 1
                if completed % 10 == 0 or completed == len(candidates):
                    print(f"candidate verification: {completed}/{len(candidates)}", flush=True)
                return
            except Exception as exc:
                error = exc
                await asyncio.sleep(2**attempt)
        row = screening[camera_id]
        verified[camera_id] = Detection(
            shed_visible=True,
            box=BoundingBox(ymin=0, xmin=0, ymax=1000, xmax=1000),
            confidence=min(float(row["confidence"]) * 0.5, 0.49),
            structure_type="possible sidewalk shed",
            side_of_image="unresolved",
            visual_reason=f'{row["reason"]} Individual verification failed: {error}',
            provider=f"{settings.gemini_model} batch fallback",
        )

    await asyncio.gather(*(run(camera_id) for camera_id in candidates))
    return verified


def active_registry_links() -> list[EvidenceLink]:
    return [
        EvidenceLink(
            label="DOB active shed map",
            url=ACTIVE_SHEDS_MAP_URL,
            description="Official daily map of actively permitted sidewalk sheds.",
        ),
        EvidenceLink(
            label="Download daily registry CSV",
            url=ACTIVE_SHEDS_URL,
            description="The exact citywide permit registry used for proximity matching.",
        ),
    ]


async def auto_case(
    camera_id: str,
    camera: dict[str, Any],
    path: Path,
    detection: Detection,
    permit_client: PermitClient,
    observed_at: datetime,
    active_count: int,
) -> ReviewCase:
    camera_lat = float(camera["latitude"])
    camera_lon = float(camera["longitude"])
    nearby = await permit_client.nearby_active_sheds(
        camera_lat, camera_lon, ACTIVE_SEARCH_RADIUS_M
    )
    nearest_distance = round(nearby[0][0], 1) if nearby else None
    nearby_records = [row.as_permit_record() for _, row in nearby[:5]]
    if nearby:
        active = nearby[0][1]
        finding = PermitFinding.PERMIT_NEARBY_UNVERIFIED
        title = f"{camera['name']} · permit nearby"
        explanation = (
            f"DOB active permit {active.job_number} at {active.address} is "
            f"{nearest_distance} m from the camera. The image-to-frontage association is not "
            "yet resolved, so this is not treated as a confirmed permit match."
        )
        lot = LotMatch(
            bbl=active.bbl or "unresolved",
            bin_ids=[active.bin_id],
            address=active.address,
            latitude=active.latitude,
            longitude=active.longitude,
            distance_from_camera_m=nearest_distance or 0,
            confidence=0.45 if nearest_distance is not None and nearest_distance <= 35 else 0.25,
            method="nearest daily active-permit record; frontage association pending",
        )
        current = nearby_records[0]
    else:
        finding = PermitFinding.LOCATION_UNRESOLVED
        title = f"{camera['name']} · no active permit nearby"
        explanation = (
            f"No entry in DOB's {active_count:,}-row daily active shed registry is within "
            f"{ACTIVE_SEARCH_RADIUS_M} m of this camera. The building frontage is not yet "
            "resolved, so this is a lead—not a finding of unpermitted work."
        )
        lot = LotMatch(
            bbl="unresolved",
            bin_ids=[],
            address="Frontage attribution pending",
            latitude=camera_lat,
            longitude=camera_lon,
            distance_from_camera_m=0,
            confidence=0,
            method="camera coordinate only; tax lot unresolved",
        )
        current = None
    evidence = PermitEvidence(
        checked_on=observed_at.date(),
        finding=finding,
        latest_record=current,
        current_permit=current,
        records_checked=active_count,
        sources=["DOB Active Sidewalk Shed Permits (daily)"],
        explanation=explanation,
        records=nearby_records,
        source_links=active_registry_links(),
        active_registry_checked=True,
        active_registry_matches=len(nearby),
        nearest_active_permit_m=nearest_distance,
    )
    static_frames = settings.evidence_dir
    static_frames.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, static_frames / path.name)
    return ReviewCase(
        case_id=f"citywide-{camera_id}",
        title=title,
        status=finding,
        frame=CameraFrame(
            camera_id=camera_id,
            camera_name=camera["name"],
            latitude=camera_lat,
            longitude=camera_lon,
            observed_at=observed_at,
            image_path=f"/evidence/{path.name}",
            live_image_url=camera.get("imageUrl", ""),
        ),
        detection=detection.model_copy(update={"provider": settings.gemini_model}),
        lot=lot,
        permit_evidence=evidence,
        ecb_context="ECB violation matching is deferred until the tax lot is resolved.",
        reasons=[detection.visual_reason, explanation],
        reviewer_questions=[
            "Which building frontage owns the boxed structure?",
            "Is a DOB permit number and expiration date posted on the shed?",
            "Does that number match one of the nearby daily registry entries?",
        ],
    )


async def adversarially_confirm(cases: list[ReviewCase]) -> list[ReviewCase]:
    detector = GeminiDetector()
    semaphore = asyncio.Semaphore(settings.gemini_concurrency)
    confirmations: dict[str, dict[str, Any]] = {}
    if CONFIRMATION_PATH.exists():
        try:
            payload = json.loads(CONFIRMATION_PATH.read_text())
            if payload.get("model") == settings.gemini_model:
                confirmations = payload.get("results", {})
        except (json.JSONDecodeError, OSError):
            pass
    automatic = [case for case in cases if case.case_id.startswith("citywide-")]
    completed = 0
    lock = asyncio.Lock()

    async def run(case: ReviewCase) -> None:
        nonlocal completed
        if case.case_id in confirmations:
            completed += 1
            return
        image_path = settings.frame_dir / Path(case.frame.image_path).name
        for attempt in range(3):
            try:
                async with semaphore:
                    check = await detector.confirm(image_path, case.detection)
                async with lock:
                    confirmations[case.case_id] = check.model_dump()
                    CONFIRMATION_PATH.write_text(
                        json.dumps(
                            {
                                "model": settings.gemini_model,
                                "updated_at": datetime.now().astimezone().isoformat(),
                                "results": confirmations,
                            },
                            indent=2,
                        )
                    )
                    completed += 1
                    if completed % 10 == 0 or completed == len(automatic):
                        print(f"adversarial confirmation: {completed}/{len(automatic)}", flush=True)
                return
            except Exception:
                await asyncio.sleep(2**attempt)

    await asyncio.gather(*(run(case) for case in automatic))
    retained: list[ReviewCase] = []
    for case in cases:
        if not case.case_id.startswith("citywide-"):
            retained.append(case)
            continue
        row = confirmations.get(case.case_id)
        if not row:
            continue
        roadway_only_camera = bool(
            re.search(
                r"(^C\d[-_]|\bWBB\b|\bFDR\b|\bBQE\b|\bLIE\b|Gowanus)",
                case.frame.camera_name,
                re.I,
            )
        )
        passes = bool(
            row["confirmed"]
            and row["visible_overhead_deck"]
            and row["visible_support_posts"]
            and row["suitable_street_level_view"]
            and float(row["confidence"]) >= 0.6
            and not roadway_only_camera
        )
        if not passes:
            continue
        case.detection.verification_passes = 2
        case.detection.confirmation_confidence = float(row["confidence"])
        case.detection.confirmation_reason = row["reason"]
        case.detection.confidence = round(
            min(case.detection.confidence, float(row["confidence"])), 2
        )
        retained.append(case)
    return retained


async def build_citywide_snapshot(batch_size: int = BATCH_SIZE):
    base = await build_snapshot(mode="gemini", refresh_permits=True, scan_all=False)
    cameras = await fetch_cameras()
    files = frame_index(settings.frame_dir)
    online = [camera for camera in cameras if camera.get("isOnline") == "true"]
    matched = {
        camera["id"]: (camera, files[normalize_name(camera["name"])])
        for camera in online
        if normalize_name(camera["name"]) in files
    }
    detector = GeminiDetector()
    screening = await screen_citywide(detector, matched, batch_size)
    verified = await verify_candidates(detector, matched, screening)
    known_ids = {case["camera_id"] for case in KNOWN_CASES}
    permit_client = PermitClient()
    active_count = len(await permit_client.active_sheds())
    automatic_cases = await asyncio.gather(
        *(
            auto_case(
                camera_id,
                matched[camera_id][0],
                matched[camera_id][1],
                detection,
                permit_client,
                base.observed_at,
                active_count,
            )
            for camera_id, detection in verified.items()
            if camera_id not in known_ids
        )
    )
    rank = {
        PermitFinding.NO_CURRENT_PERMIT: 0,
        PermitFinding.LOCATION_UNRESOLVED: 1,
        PermitFinding.PERMIT_NEARBY_UNVERIFIED: 2,
        PermitFinding.VALID_PERMIT: 3,
    }
    confirmed_cases = await adversarially_confirm(base.cases + list(automatic_cases))
    base.cases = sorted(confirmed_cases, key=lambda case: rank[case.status])
    base.scope = "citywide"
    base.snapshot_mode = "gemini-citywide"
    base.center_latitude = 40.7128
    base.center_longitude = -74.006
    base.radius_m = 0
    base.generated_at = datetime.now().astimezone()
    base.metrics.cameras_available = len(cameras)
    base.metrics.cameras_in_radius = len(online)
    base.metrics.frames_matched = len(matched)
    base.metrics.sheds_detected = len(base.cases)
    base.metrics.permit_gaps = sum(
        case.status == PermitFinding.NO_CURRENT_PERMIT for case in base.cases
    )
    base.metrics.controls = sum(case.is_control for case in base.cases)
    base.metrics.permit_nearby = sum(
        case.status == PermitFinding.PERMIT_NEARBY_UNVERIFIED for case in base.cases
    )
    base.metrics.unresolved = sum(
        case.status == PermitFinding.LOCATION_UNRESOLVED for case in base.cases
    )
    settings.snapshot_path.write_text(base.model_dump_json(indent=2))
    print(
        f"wrote citywide snapshot: {len(matched)} frames, {len(base.cases)} cases, "
        f"{base.metrics.unresolved} unresolved, {base.metrics.permit_nearby} permit-nearby",
        flush=True,
    )
    return base


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the citywide Shedwatch snapshot")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument(
        "--confirm-existing",
        action="store_true",
        help="Apply the adversarial gate to the existing citywide snapshot only",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Discard prior checkpoints and process every frame in this snapshot",
    )
    args = parser.parse_args()
    if args.fresh:
        for checkpoint in (CHECKPOINT_PATH, CONFIRMATION_PATH):
            checkpoint.unlink(missing_ok=True)
    if args.confirm_existing:
        from app.models import ScanSnapshot

        snapshot = ScanSnapshot.model_validate_json(settings.snapshot_path.read_text())
        snapshot.cases = asyncio.run(adversarially_confirm(snapshot.cases))
        snapshot.metrics.sheds_detected = len(snapshot.cases)
        snapshot.metrics.permit_nearby = sum(
            case.status == PermitFinding.PERMIT_NEARBY_UNVERIFIED for case in snapshot.cases
        )
        snapshot.metrics.unresolved = sum(
            case.status == PermitFinding.LOCATION_UNRESOLVED for case in snapshot.cases
        )
        settings.snapshot_path.write_text(snapshot.model_dump_json(indent=2))
        print(f"retained {len(snapshot.cases)} cases after adversarial confirmation")
    else:
        asyncio.run(build_citywide_snapshot(args.batch_size))


if __name__ == "__main__":
    main()
