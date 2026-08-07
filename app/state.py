from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock

from app.models import DecisionRequest, DecisionResponse, ReviewDecision, ScanSnapshot


class SnapshotStore:
    def __init__(self, snapshot_path: Path) -> None:
        self.snapshot_path = snapshot_path
        self._snapshot = self._load()
        self._decisions: dict[str, DecisionResponse] = {}
        self._lock = Lock()

    def _load(self) -> ScanSnapshot:
        return ScanSnapshot.model_validate_json(self.snapshot_path.read_text())

    def get_snapshot(self) -> ScanSnapshot:
        with self._lock:
            snapshot = self._snapshot.model_copy(deep=True)
            for case in snapshot.cases:
                decision = self._decisions.get(case.case_id)
                if decision:
                    case.decision = decision.decision
                    case.review_note = decision.note
                    case.reviewed_at = decision.reviewed_at
            return snapshot

    def get_case(self, case_id: str):
        snapshot = self.get_snapshot()
        return next((case for case in snapshot.cases if case.case_id == case_id), None)

    def decide(self, case_id: str, request: DecisionRequest) -> DecisionResponse:
        if not any(case.case_id == case_id for case in self._snapshot.cases):
            raise KeyError(case_id)
        response = DecisionResponse(
            case_id=case_id,
            decision=ReviewDecision(request.decision),
            note=request.note,
            reviewed_at=datetime.now().astimezone(),
        )
        with self._lock:
            self._decisions[case_id] = response
        return response
