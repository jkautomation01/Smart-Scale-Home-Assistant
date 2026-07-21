"""Parsing of raw GATT notification payloads from a Medisana BS4xx scale.

Byte layouts below are reverse-engineered by the keptenkurk/BS440 project
and reused here. See const.py for provenance/caveats.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import struct

from .const import EPOCH_2010_OFFSET

_LOGGER = logging.getLogger(__name__)


@dataclass
class PersonRecord:
    """A person/profile-slot record (handle for CHAR_PERSON_UUID)."""

    person_id: int
    gender: int
    age: int
    height_cm: int
    activity_level: int


@dataclass
class WeightRecord:
    """A weight measurement record (handle for CHAR_WEIGHT_UUID)."""

    person_id: int
    weight_kg: float
    timestamp: int


@dataclass
class BodyRecord:
    """A body-composition record (handle for CHAR_BODY_UUID)."""

    person_id: int
    timestamp: int
    kcal: float
    fat_percent: float
    water_percent: float
    muscle_percent: float
    bone_mass_kg: float


def parse_person(data: bytes) -> PersonRecord | None:
    """Parse a person/profile payload.

    Layout (9 bytes): [0]=0x84 marker, [2]=person id, [4]=gender,
    [5]=age, [6]=height cm, [8]=activity level.
    """
    if len(data) < 9 or data[0] != 0x84:
        _LOGGER.debug("Ignoring unexpected person payload: %s", data.hex())
        return None
    return PersonRecord(
        person_id=data[2],
        gender=data[4],
        age=data[5],
        height_cm=data[6],
        activity_level=data[8],
    )


def parse_weight(data: bytes) -> WeightRecord | None:
    """Parse a weight payload.

    Layout (14 bytes): [0]=0x1D marker, [1:3]=weight in 10g units (LE),
    [5:9]=timestamp (LE uint32), [13]=person id.
    """
    if len(data) < 14 or data[0] != 0x1D:
        _LOGGER.debug("Ignoring unexpected weight payload: %s", data.hex())
        return None
    raw_weight = struct.unpack_from("<H", data, 1)[0]
    timestamp = struct.unpack_from("<I", data, 5)[0]
    return WeightRecord(
        person_id=data[13],
        weight_kg=raw_weight / 100.0,
        timestamp=timestamp,
    )


def parse_body(data: bytes) -> BodyRecord | None:
    """Parse a body-composition payload.

    Layout (16 bytes): [0]=0x6F marker, [1:5]=timestamp (LE uint32),
    [5]=person id, [6:16]=5x uint16 (LE) each *10 and masked with 0x0FFF:
    kcal, fat%, water%, muscle%, bone mass (kg).
    """
    if len(data) < 16 or data[0] != 0x6F:
        _LOGGER.debug("Ignoring unexpected body payload: %s", data.hex())
        return None
    timestamp = struct.unpack_from("<I", data, 1)[0]
    person_id = data[5]
    kcal, fat, water, muscle, bone = struct.unpack_from("<HHHHH", data, 6)
    return BodyRecord(
        person_id=person_id,
        timestamp=timestamp,
        kcal=(kcal & 0x0FFF) / 10.0,
        fat_percent=(fat & 0x0FFF) / 10.0,
        water_percent=(water & 0x0FFF) / 10.0,
        muscle_percent=(muscle & 0x0FFF) / 10.0,
        bone_mass_kg=(bone & 0x0FFF) / 10.0,
    )


def sanitize_timestamp(raw_timestamp: int, use_2010_epoch: bool) -> int:
    """Convert a scale-relative timestamp to a Unix epoch timestamp."""
    if use_2010_epoch:
        return raw_timestamp + EPOCH_2010_OFFSET
    return raw_timestamp
