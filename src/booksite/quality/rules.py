from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class NativeTextStatus(StrEnum):
    TEXT_GOOD = "TEXT_GOOD"
    TEXT_SUSPECT = "TEXT_SUSPECT"
    IMAGE_ONLY = "IMAGE_ONLY"
    MIXED = "MIXED"


class TextQualityThresholds(BaseModel):
    good_character_count: int = Field(default=100, ge=1)
    suspect_character_count: int = Field(default=20, ge=1)
    maximum_replacement_ratio: float = Field(default=0.005, ge=0, le=1)
    image_only_coverage_ratio: float = Field(default=0.5, ge=0, le=1)


def classify_native_text(
    text: str,
    image_coverage_ratio: float,
    thresholds: TextQualityThresholds | None = None,
) -> NativeTextStatus:
    limits = thresholds or TextQualityThresholds()
    character_count = len(text.strip())
    replacement_ratio = text.count("\ufffd") / max(character_count, 1)

    if (
        character_count >= limits.good_character_count
        and replacement_ratio < limits.maximum_replacement_ratio
    ):
        return NativeTextStatus.TEXT_GOOD
    if character_count >= limits.suspect_character_count:
        return NativeTextStatus.TEXT_SUSPECT
    if image_coverage_ratio > limits.image_only_coverage_ratio:
        return NativeTextStatus.IMAGE_ONLY
    return NativeTextStatus.MIXED
