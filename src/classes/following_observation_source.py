"""Pure source identity for an existing follow session.

These values neither own a session nor qualify measurement freshness, target
identity, calibration accuracy or physical timing. Callers supply identities
already established by the observation producer and its independent owner.
"""

from dataclasses import dataclass
from enum import Enum

from classes.gimbal_types import CameraObservationSource, GimbalAngleObservation
from classes.guidance_observation import ImageFrameContext, ImageMeasurement


def _identity(value: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError("following_observation_source_identity_invalid")


@dataclass(frozen=True)
class ImageObservationOwner:
    """Current publisher identity, available independently of analysis frames."""

    source_id: str
    source_epoch: str

    def __post_init__(self):
        _identity(self.source_id)
        _identity(self.source_epoch)


@dataclass(frozen=True)
class ImageFollowingSource:
    source_id: str
    source_epoch: str
    geometry_revision: str
    calibration_revision: str | None = None

    def __post_init__(self):
        for value in (self.source_id, self.source_epoch, self.geometry_revision):
            _identity(value)
        if self.calibration_revision is not None:
            _identity(self.calibration_revision)


@dataclass(frozen=True)
class GimbalFollowingSource:
    source: CameraObservationSource
    provider_id: str
    geometry_revision: str

    def __post_init__(self):
        if not isinstance(self.source, CameraObservationSource):
            raise ValueError("following_camera_observation_source_invalid")
        _identity(self.provider_id)
        _identity(self.geometry_revision)


FollowingObservationSource = ImageFollowingSource | GimbalFollowingSource


class ObservationSourceVerdict(str, Enum):
    UNCHANGED = "unchanged"
    UNAVAILABLE = "unavailable"
    DEFINITELY_CHANGED = "definitely_changed"


def project_following_observation_source(observation) -> FollowingObservationSource | None:
    """Strip sample/target state without manufacturing a missing source owner.

    Image geometry refers to the producer's analysis revision, never encoded
    delivery dimensions or a media receiver/stream epoch. A source match alone
    says nothing about whether this particular frame or angle remains usable.
    """
    if observation is None:
        return None
    if isinstance(observation, (ImageFollowingSource, GimbalFollowingSource)):
        return observation
    if isinstance(observation, (ImageFrameContext, ImageMeasurement)):
        provenance = observation.provenance
        return ImageFollowingSource(provenance.source_id, provenance.capture.source_epoch,
                                    provenance.geometry_revision, provenance.calibration_revision)
    if isinstance(observation, GimbalAngleObservation):
        if observation.source is None:
            return None
        return GimbalFollowingSource(observation.source, observation.provider_id, observation.geometry_revision)
    raise ValueError("following_observation_source_contract_invalid")


def _available_source(observation) -> FollowingObservationSource | None:
    try:
        return project_following_observation_source(observation)
    except (ValueError, TypeError, AttributeError):
        return None


def compare_following_observation_source(
    pinned: FollowingObservationSource | None, *, current, sample, current_context=None,
) -> ObservationSourceVerdict:
    """Check independent current ownership and sample binding against a pin.

    A gimbal owner may supply its source-only CameraObservationSource; the
    sample must still supply provider/geometry binding. A complete projected
    current source also compares those revisions independently. Image owners
    supply current_context for analysis geometry; a changed publisher identity
    wins even before the next context exists. Definite current changes take
    precedence over missing or malformed analysis contexts and samples.
    Missing pins never bind themselves from whatever data happens to arrive.
    """
    if not isinstance(pinned, (ImageFollowingSource, GimbalFollowingSource)):
        return ObservationSourceVerdict.UNAVAILABLE
    if isinstance(current, ImageObservationOwner):
        if (not isinstance(pinned, ImageFollowingSource)
                or (current.source_id, current.source_epoch) != (pinned.source_id, pinned.source_epoch)):
            return ObservationSourceVerdict.DEFINITELY_CHANGED
        current_available = current_context is not None
    elif isinstance(current, CameraObservationSource):
        current_available = True
        if not isinstance(pinned, GimbalFollowingSource) or current != pinned.source:
            return ObservationSourceVerdict.DEFINITELY_CHANGED
    else:
        current_source = _available_source(current)
        current_available = current_source is not None
        if current_available and current_source != pinned:
            return ObservationSourceVerdict.DEFINITELY_CHANGED
    if current_context is not None:
        analysis_source = _available_source(current_context)
        if analysis_source is None:
            current_available = False
        elif analysis_source != pinned:
            return ObservationSourceVerdict.DEFINITELY_CHANGED
    sample_source = _available_source(sample)
    if sample_source is not None and sample_source != pinned:
        return ObservationSourceVerdict.DEFINITELY_CHANGED
    if not current_available or sample_source is None:
        return ObservationSourceVerdict.UNAVAILABLE
    return ObservationSourceVerdict.UNCHANGED
