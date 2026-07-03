"""
Staged fire detection state types.

Defines the DetectionState enum and the event dataclasses produced by the
staged verification pipeline in FireDetector.evaluate().
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DetectionState(Enum):
    """Three-stage fire detection confidence level."""

    NORMAL = "normal"
    SUSPECTED_FIRE = "suspected_fire"
    VERIFIED_FIRE = "verified_fire"


@dataclass
class AlertEvent:
    """
    Emitted when the detection state transitions to SUSPECTED_FIRE.

    Contains a snapshot of all evidence available at detection time.
    """

    state: DetectionState
    timestamp: float
    latitude: Optional[float]
    longitude: Optional[float]
    smoke: float
    temperature: float
    humidity: float
    flame: object
    camera_detected: bool
    camera_result: Optional[dict]
    verification_reason: str
    image_path: Optional[str] = field(default=None)


@dataclass
class ReportEvent:
    """
    Emitted when the detection state transitions to VERIFIED_FIRE.

    Extends AlertEvent evidence with a second confirmation timestamp.
    """

    state: DetectionState
    timestamp: float
    report_timestamp: float
    latitude: Optional[float]
    longitude: Optional[float]
    smoke: float
    temperature: float
    humidity: float
    flame: object
    camera_detected: bool
    camera_result: Optional[dict]
    verification_reason: str
    image_path: Optional[str] = field(default=None)
