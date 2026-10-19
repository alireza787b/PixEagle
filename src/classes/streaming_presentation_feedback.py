"""Optional, peer-bound presentation observations; never flight authority."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VideoPresentationFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: int = Field(ge=1, le=1)
    epoch: str = Field(pattern=r"^[1-9][0-9]*$", max_length=20)
    elapsed_ms: int = Field(ge=0, le=2**53 - 1)
    verified_frames: int = Field(ge=0, le=2**53 - 1)
    presented_frames: int = Field(ge=0, le=2**53 - 1)
    last_presented_age_bound_ms: Optional[float] = Field(default=None, ge=0, le=600_000, allow_inf_nan=False)
    since_last_presentation_ms: Optional[int] = Field(default=None, ge=0, le=2**53 - 1)

    @model_validator(mode="after")
    def validate_counters(self):
        if self.presented_frames > self.verified_frames:
            raise ValueError("Presented frames exceed verified frame receipts")
        if self.presented_frames == 0 and (
                self.last_presented_age_bound_ms is not None or self.since_last_presentation_ms is not None):
            raise ValueError("No presentation age exists before the first presented frame")
        return self
