from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@dataclass(frozen=True)
class Settings:
    project_root: Path = Path(__file__).resolve().parents[1]
    frame_dir: Path = Path(
        os.getenv("FRAME_DIR", "/Users/kevinshah/Downloads/frames-rain")
    )
    snapshot_path: Path = Path(
        os.getenv(
            "SNAPSHOT_PATH",
            Path(__file__).resolve().parent / "data" / "scan-snapshot.json",
        )
    )
    static_dir: Path = Path(__file__).resolve().parent / "static"
    evidence_dir: Path = Path(
        os.getenv(
            "EVIDENCE_DIR",
            Path(__file__).resolve().parent / "static" / "frames",
        )
    )
    checkpoint_dir: Path = Path(
        os.getenv(
            "CHECKPOINT_DIR",
            Path(__file__).resolve().parent / "data",
        )
    )
    pilot_latitude: float = float(os.getenv("PILOT_LATITUDE", "40.734717"))
    pilot_longitude: float = float(os.getenv("PILOT_LONGITUDE", "-73.990696"))
    pilot_radius_m: int = int(os.getenv("PILOT_RADIUS_M", "1609"))
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    gemini_concurrency: int = int(os.getenv("GEMINI_CONCURRENCY", "4"))


settings = Settings()
