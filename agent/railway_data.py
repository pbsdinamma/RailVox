"""
RailVox — Railway Timetable Data Layer

Provides search and filter functions over a static Indian railway timetable.
Pure functions with no async — easy to test independently.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Load timetable data
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent / "data"
_TIMETABLE: dict[str, Any] | None = None


def _load_timetable() -> dict[str, Any]:
    """Load the static timetable JSON. Cached after first call."""
    global _TIMETABLE
    if _TIMETABLE is None:
        timetable_path = _DATA_DIR / "timetable.json"
        with open(timetable_path, "r", encoding="utf-8") as f:
            _TIMETABLE = json.load(f)
    return _TIMETABLE


def _get_trains() -> list[dict]:
    return _load_timetable()["trains"]


def _get_stations() -> dict[str, dict]:
    return _load_timetable()["stations"]


# ---------------------------------------------------------------------------
# Station name normalization
# ---------------------------------------------------------------------------

def _normalize_station(name: str) -> str:
    """Normalize a station name for matching. Handles aliases."""
    name_lower = name.strip().lower()

    stations = _get_stations()
    for station_name, info in stations.items():
        if name_lower == station_name.lower():
            return station_name
        if name_lower == info.get("code", "").lower():
            return station_name
        for alias in info.get("aliases", []):
            if name_lower == alias.lower():
                return station_name

    # Return as-is if no match (let the search handle "not found")
    return name.strip()


def _time_to_minutes(time_str: str) -> int:
    """Convert HH:MM to minutes since midnight."""
    parts = time_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _matches_time_preference(departure: str, preference: str) -> bool:
    """Check if a departure time matches a time-of-day preference."""
    minutes = _time_to_minutes(departure)

    if preference in ("any", "all", ""):
        return True
    elif preference == "morning":
        return 360 <= minutes < 720  # 6:00 AM – 12:00 PM
    elif preference == "afternoon":
        return 720 <= minutes < 960  # 12:00 PM – 4:00 PM
    elif preference == "evening":
        return 960 <= minutes < 1260  # 4:00 PM – 9:00 PM
    elif preference == "night":
        return minutes >= 1260 or minutes < 360  # 9:00 PM – 6:00 AM
    return True


def _matches_day(days_of_run: list[str], date_str: str) -> bool:
    """Check if a train runs on the given date's day of week."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        day_name = dt.strftime("%a")  # Mon, Tue, etc.
        return day_name in days_of_run
    except (ValueError, TypeError):
        return True  # If date parsing fails, don't filter by day


def _format_time_12h(time_24h: str) -> str:
    """Convert 24h time to 12h format for speech."""
    minutes = _time_to_minutes(time_24h)
    hours = minutes // 60
    mins = minutes % 60
    period = "AM" if hours < 12 else "PM"
    display_hour = hours % 12
    if display_hour == 0:
        display_hour = 12
    return f"{display_hour}:{mins:02d} {period}"


def _format_duration(duration_minutes: int) -> str:
    """Format duration for speech output."""
    hours = duration_minutes // 60
    mins = duration_minutes % 60
    if hours > 0 and mins > 0:
        return f"{hours} hour{'s' if hours > 1 else ''} {mins} minute{'s' if mins > 1 else ''}"
    elif hours > 0:
        return f"{hours} hour{'s' if hours > 1 else ''}"
    else:
        return f"{mins} minute{'s' if mins > 1 else ''}"


# ---------------------------------------------------------------------------
# Search functions
# ---------------------------------------------------------------------------

def search(
    origin: str,
    destination: str,
    date: str,
    time_preference: str = "any",
    travel_class: str = "any",
) -> list[dict]:
    """
    Search for trains between two stations on a given date.

    Args:
        origin: Origin station name or code.
        destination: Destination station name or code.
        date: Travel date in YYYY-MM-DD format.
        time_preference: "morning", "afternoon", "evening", "night", or "any".
        travel_class: "1A", "2A", "3A", "SL", "CC", "2S", or "any".

    Returns:
        List of matching train results, sorted by departure time.
    """
    origin_norm = _normalize_station(origin)
    dest_norm = _normalize_station(destination)
    trains = _get_trains()

    results = []
    for train in trains:
        # Check origin matches (exact or via)
        train_origin = train["origin"]
        train_dest = train["destination"]
        train_via = train.get("via", [])

        origin_match = (
            origin_norm.lower() == train_origin.lower()
            or any(origin_norm.lower() == v.lower() for v in train_via)
            or any(
                origin_norm.lower() == alias.lower()
                for s_name, s_info in _get_stations().items()
                if s_name.lower() == train_origin.lower()
                for alias in s_info.get("aliases", [])
            )
        )

        dest_match = (
            dest_norm.lower() == train_dest.lower()
            or any(dest_norm.lower() == v.lower() for v in train_via)
            or any(
                dest_norm.lower() == alias.lower()
                for s_name, s_info in _get_stations().items()
                if s_name.lower() == train_dest.lower()
                for alias in s_info.get("aliases", [])
            )
        )

        # Also check reverse direction and via stations for both
        if not origin_match:
            # Check if origin is in any station's aliases
            for s_name, s_info in _get_stations().items():
                all_names = [s_name.lower()] + [a.lower() for a in s_info.get("aliases", [])]
                if origin_norm.lower() in all_names:
                    canonical = s_name
                    if canonical.lower() == train_origin.lower() or canonical.lower() in [v.lower() for v in train_via]:
                        origin_match = True
                        break

        if not dest_match:
            for s_name, s_info in _get_stations().items():
                all_names = [s_name.lower()] + [a.lower() for a in s_info.get("aliases", [])]
                if dest_norm.lower() in all_names:
                    canonical = s_name
                    if canonical.lower() == train_dest.lower() or canonical.lower() in [v.lower() for v in train_via]:
                        dest_match = True
                        break

        if not (origin_match and dest_match):
            continue

        # Check day of run
        if not _matches_day(train.get("days_of_run", []), date):
            continue

        # Check time preference
        if not _matches_time_preference(train["departure"], time_preference or "any"):
            continue

        # Check travel class
        if travel_class and travel_class.lower() not in ("any", "all", ""):
            if travel_class.upper() not in train.get("classes", []):
                continue

        # Build result
        results.append({
            "train_number": train["number"],
            "train_name": train["name"],
            "origin": train_origin,
            "destination": train_dest,
            "departure": _format_time_12h(train["departure"]),
            "departure_24h": train["departure"],
            "arrival": _format_time_12h(train["arrival"]),
            "arrival_24h": train["arrival"],
            "duration": _format_duration(train["duration_minutes"]),
            "duration_minutes": train["duration_minutes"],
            "classes": train.get("classes", []),
            "type": train.get("type", "Express"),
            "pantry": train.get("pantry", False),
            "days_of_run": train.get("days_of_run", []),
        })

    # Sort by departure time
    results.sort(key=lambda t: t["departure_24h"])

    return results


def get_details(train_number: str) -> dict | None:
    """Get detailed information about a specific train."""
    trains = _get_trains()
    for train in trains:
        if train["number"] == train_number:
            return {
                "train_number": train["number"],
                "train_name": train["name"],
                "origin": train["origin"],
                "destination": train["destination"],
                "departure": _format_time_12h(train["departure"]),
                "arrival": _format_time_12h(train["arrival"]),
                "duration": _format_duration(train["duration_minutes"]),
                "via_stations": train.get("via", []),
                "classes": train.get("classes", []),
                "type": train.get("type", "Express"),
                "pantry": train.get("pantry", False),
                "fares": train.get("fares", {}),
                "days_of_run": train.get("days_of_run", []),
            }
    return None


def check_availability(
    train_number: str,
    travel_class: str,
    date: str,
) -> dict:
    """
    Check seat availability (simulated).

    Returns a simulated availability status.
    """
    import random

    train = get_details(train_number)
    if train is None:
        return {"error": f"Train {train_number} not found"}

    if travel_class.upper() not in train["classes"]:
        return {
            "error": f"Class {travel_class} is not available on train {train_number} ({train['train_name']})"
        }

    # Simulated availability
    statuses = [
        ("AVAILABLE", random.randint(10, 150)),
        ("RAC", random.randint(1, 20)),
        ("WAITLIST", random.randint(1, 50)),
    ]
    status, count = random.choice(statuses)

    fare = train.get("fares", {}).get(travel_class.upper())

    return {
        "train_number": train_number,
        "train_name": train["train_name"],
        "class": travel_class.upper(),
        "date": date,
        "status": status,
        "count": count,
        "fare": fare,
        "message": (
            f"{count} seats available"
            if status == "AVAILABLE"
            else f"RAC {count}" if status == "RAC" else f"Waitlist {count}"
        ),
    }
