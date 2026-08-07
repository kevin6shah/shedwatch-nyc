from __future__ import annotations

import asyncio
import os
from pathlib import Path

from google import genai
from google.genai import types

from app.config import settings
from app.models import GeminiVisionResult


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
        image_bytes = await asyncio.to_thread(image_path.read_bytes)

        def run() -> GeminiVisionResult:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    DETECTION_PROMPT,
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                ],
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=GeminiVisionResult,
                ),
            )
            if isinstance(response.parsed, GeminiVisionResult):
                return response.parsed
            return GeminiVisionResult.model_validate_json(response.text)

        return await asyncio.to_thread(run)
