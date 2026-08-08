from __future__ import annotations

import asyncio
import os
from pathlib import Path

from google import genai
from google.genai import types

from app.config import settings
from app.models import AdversarialVisionCheck, BatchScreenResult, Detection, GeminiVisionResult


DETECTION_PROMPT = """
You are inspecting a low-resolution NYC DOT traffic-camera still.

Detect every sidewalk shed: a temporary covered pedestrian walkway made from
vertical construction posts and a rigid overhead deck, usually installed next
to a building. Also detect a supported scaffold only when it clearly occupies
the sidewalk or is built on top of such a shed.

Do not label bus shelters, permanent awnings, outdoor dining structures,
elevated roads, bridge structures, traffic poles, or uncovered façade
scaffolding as sidewalk sheds.

Return normalized bounding boxes in the range 0..1000. Describe where each
structure is in the image and give a conservative confidence. If rain, glare,
distance, or occlusion makes the identification uncertain, lower confidence.
""".strip()

BATCH_SCREEN_PROMPT = """
High-recall screening only. Inspect every numbered NYC traffic-camera frame
for any likely OR possible sidewalk shed: a rigid roof/deck covering a
pedestrian path, generally with vertical construction posts along a building
frontage. Small, distant, rain-obscured, cropped, dark, or ambiguous structures
must be possible_shed, not no_shed. Use no_shed only when you are very sure.
Exclude obvious bus shelters, fabric or permanent awnings, dining sheds,
bridges, elevated roads, and uncovered scaffolding. Return exactly one result
per numbered image.
""".strip()


class GeminiDetector:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.gemini_model
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            self.client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(api_version="v1beta"),
            )
        else:
            self.client = genai.Client(
                vertexai=True,
                project=os.getenv("GOOGLE_CLOUD_PROJECT"),
                location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
                http_options=types.HttpOptions(api_version="v1"),
            )

    async def detect(self, image_path: Path) -> GeminiVisionResult:
        return await self._detect_with_prompt(image_path, DETECTION_PROMPT)

    async def detect_frontage(
        self, image_path: Path, expected_side: str
    ) -> GeminiVisionResult:
        prompt = f"""{DETECTION_PROMPT}

This is a frontage-specific verification call. Inspect only the
{expected_side} frontage. Return a detection only if the required rigid deck
and repeated vertical supports are visibly present on that side. Do not return
a structure from the opposite side and do not infer one from the location.
""".strip()
        return await self._detect_with_prompt(image_path, prompt)

    async def _detect_with_prompt(
        self, image_path: Path, prompt: str
    ) -> GeminiVisionResult:
        image_bytes = await asyncio.to_thread(image_path.read_bytes)

        def run() -> GeminiVisionResult:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                ],
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=GeminiVisionResult,
                ),
            )
            if isinstance(response.parsed, GeminiVisionResult):
                result = response.parsed
            else:
                result = GeminiVisionResult.model_validate_json(response.text)
            return result.model_copy(
                update={
                    "detections": [
                        detection.model_copy(
                            update={
                                "verification_passes": 1,
                                "confirmation_confidence": None,
                                "confirmation_reason": None,
                            }
                        )
                        for detection in result.detections
                    ]
                }
            )

        return await asyncio.to_thread(run)

    async def screen_batch(self, image_paths: list[Path]) -> BatchScreenResult:
        contents: list[types.Part] = [types.Part.from_text(text=BATCH_SCREEN_PROMPT)]
        for index, image_path in enumerate(image_paths, 1):
            image_bytes = await asyncio.to_thread(image_path.read_bytes)
            contents.extend(
                [
                    types.Part.from_text(text=f"IMAGE {index}: {image_path.name}"),
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                ]
            )

        def run() -> BatchScreenResult:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=BatchScreenResult,
                ),
            )
            if isinstance(response.parsed, BatchScreenResult):
                return response.parsed
            return BatchScreenResult.model_validate_json(response.text)

        return await asyncio.to_thread(run)

    async def confirm(self, image_path: Path, detection: Detection) -> AdversarialVisionCheck:
        image_bytes = await asyncio.to_thread(image_path.read_bytes)
        prompt = f"""
Act as an adversarial verifier. Another model claimed this NYC traffic frame
contains a sidewalk shed at normalized box {detection.box.model_dump() if detection.box else None}
because: {detection.visual_reason}

Reject the claim unless you can clearly see BOTH a rigid overhead pedestrian-
protection deck and repeated vertical support posts beside a building frontage.
Roadways, bridges, construction barriers, glare, rain artifacts, tents,
awnings, outdoor dining structures, and guesses are false. A high or elevated
roadway view without a clear sidewalk frontage is unsuitable. Return confirmed
only when the visual evidence is specific.
""".strip()

        def run() -> AdversarialVisionCheck:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                ],
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=AdversarialVisionCheck,
                ),
            )
            if isinstance(response.parsed, AdversarialVisionCheck):
                return response.parsed
            return AdversarialVisionCheck.model_validate_json(response.text)

        return await asyncio.to_thread(run)
