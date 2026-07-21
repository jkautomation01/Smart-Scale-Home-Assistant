"""Constants for the Medisana BLE Scale integration."""
from __future__ import annotations

DOMAIN = "medisana_ble"
DEFAULT_NAME = "Medisana Scale"

CONF_TIME_OFFSET = "use_2010_epoch"
CONF_PERSON_NAME_PREFIX = "person_name_"

MAX_PERSON_SLOTS = 8

# GATT characteristic UUIDs for the Medisana BS4xx family, reverse-engineered
# by the keptenkurk/BS440 project (https://github.com/keptenkurk/BS440) and
# reused by bwynants/weegschaal (https://github.com/bwynants/weegschaal) for
# ESPHome. Confirmed against BS410, BS430, BS440, BS444 and BS550. The BS436
# has NOT been independently confirmed to use the same characteristics -
# enable debug logging for this integration and weigh in to verify the raw
# payloads look sane before relying on the readings.
CHAR_PERSON_UUID = "00008a82-0000-1000-8000-00805f9b34fb"
CHAR_WEIGHT_UUID = "00008a21-0000-1000-8000-00805f9b34fb"
CHAR_BODY_UUID = "00008a22-0000-1000-8000-00805f9b34fb"
CHAR_COMMAND_UUID = "00008a81-0000-1000-8000-00805f9b34fb"

COMMAND_SET_TIMESTAMP = 0x02

# Some scales in this family (BS410/BS444, and per user reports others too)
# store their internal clock relative to 2010-01-01T00:00:00Z instead of the
# Unix epoch. This is exposed as a per-entry option because it's the one
# protocol detail most likely to differ on an unconfirmed model like BS436.
EPOCH_2010_OFFSET = 1262304000

GENDER_LABELS = {1: "male", 2: "female"}
ACTIVITY_LABELS = {0: "normal", 3: "high"}

MIN_RECONNECT_INTERVAL = 20  # seconds, debounce reconnect on repeat adverts
MEASUREMENT_TIMEOUT = 30  # hard cap on time to wait for a reading after connect

# The scale replays its stored measurement history (up to ~30 past
# records) on every connection, not just the latest weigh-in. We keep
# listening until this many seconds pass with no new notification before
# treating the burst as finished, then pick the record with the highest
# timestamp per person - that's the actual current weigh-in.
QUIET_PERIOD = 3

SIGNAL_MEDISANA_DATA = "medisana_ble_data_{entry_id}"
