"""
railway_data.py — static timetable search layer.

Loads timetable.json from the data/ directory and provides
search + availability functions. No async, easy to unit test.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


_DATA_DIR = Path(__file__).parent / "data"
_TIMETABLE: dict[str, Any] | None = None


def _load_timetable() -> dict[str, Any]:
    global _TIMETABLE
    if _TIMETABLE is None:
        with open(_DATA_DIR / "timetable.json", "r", encoding="utf-8") as f:
            _TIMETABLE = json.load(f)
    return _TIMETABLE


def _get_trains() -> list[dict]:
    return _load_timetable()["trains"]


def _get_stations() -> dict[str, dict]:
    return _load_timetable()["stations"]


def _normalize_station(name: str) -> str:
    """Resolve a station name/code/alias to its canonical name."""
    s = name.strip().lower()
    for station_name, info in _get_stations().items():
        if s == station_name.lower():
            return station_name
        if s == info.get("code", "").lower():
            return station_name
        if any(s == a.lower() for a in info.get("aliases", [])):
            return station_name
    return name.strip()


def _time_to_minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _matches_time_preference(departure: str, pref: str) -> bool:
    mins = _time_to_minutes(departure)
    if pref in ("any", "all", ""):
        return True
    elif pref == "morning":
        return 360 <= mins < 720
    elif pref == "afternoon":
        return 720 <= mins < 960
    elif pref == "evening":
        return 960 <= mins < 1260
    elif pref == "night":
        return mins >= 1260 or mins < 360
    return True


def _matches_day(days: list[str], date_str: str) -> bool:
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a")
        return day in days
    except (ValueError, TypeError):
        return True


def _fmt_time(t: str) -> str:
    """Convert 24h time to 12h AM/PM."""
    mins = _time_to_minutes(t)
    h, m = divmod(mins, 60)
    period = "AM" if h < 12 else "PM"
    h = h % 12 or 12
    return f"{h}:{m:02d} {period}"


def _fmt_duration(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    parts = []
    if h:
        parts.append(f"{h} hour{'s' if h > 1 else ''}")
    if m:
        parts.append(f"{m} minute{'s' if m > 1 else ''}")
    return " ".join(parts)


def _station_matches(name: str, train_origin: str, via: list[str]) -> bool:
    """Check if a station name matches a train's origin or any via station."""
    norm = _normalize_station(name)
    if norm.lower() == train_origin.lower():
        return True
    if any(norm.lower() == v.lower() for v in via):
        return True
    # fallback: check all aliases
    for s_name, s_info in _get_stations().items():
        all_names = [s_name.lower()] + [a.lower() for a in s_info.get("aliases", [])]
        if norm.lower() in all_names:
            canonical = s_name
            if canonical.lower() == train_origin.lower() or canonical.lower() in [v.lower() for v in via]:
                return True
    return False


def search(
    origin: str,
    destination: str,
    date: str,
    time_preference: str = "any",
    travel_class: str = "any",
) -> list[dict]:
    """Search trains between two stations on a given date."""
    results = []
    for train in _get_trains():
        if not _station_matches(origin, train["origin"], train.get("via", [])):
            continue
        if not _station_matches(destination, train["destination"], train.get("via", [])):
            continue
        if not _matches_day(train.get("days_of_run", []), date):
            continue
        if not _matches_time_preference(train["departure"], time_preference or "any"):
            continue
        if travel_class and travel_class.lower() not in ("any", "all", ""):
            if travel_class.upper() not in train.get("classes", []):
                continue

        results.append({
            "train_number": train["number"],
            "train_name": train["name"],
            "origin": train["origin"],
            "destination": train["destination"],
            "departure": _fmt_time(train["departure"]),
            "departure_24h": train["departure"],
            "arrival": _fmt_time(train["arrival"]),
            "arrival_24h": train["arrival"],
            "duration": _fmt_duration(train["duration_minutes"]),
            "duration_minutes": train["duration_minutes"],
            "classes": train.get("classes", []),
            "type": train.get("type", "Express"),
            "pantry": train.get("pantry", False),
            "days_of_run": train.get("days_of_run", []),
        })

    results.sort(key=lambda t: t["departure_24h"])
    return results


def get_details(train_number: str) -> dict | None:
    """Get full details for a train by number."""
    for train in _get_trains():
        if train["number"] == train_number:
            return {
                "train_number": train["number"],
                "train_name": train["name"],
                "origin": train["origin"],
                "destination": train["destination"],
                "departure": _fmt_time(train["departure"]),
                "arrival": _fmt_time(train["arrival"]),
                "duration": _fmt_duration(train["duration_minutes"]),
                "via_stations": train.get("via", []),
                "classes": train.get("classes", []),
                "type": train.get("type", "Express"),
                "pantry": train.get("pantry", False),
                "fares": train.get("fares", {}),
                "days_of_run": train.get("days_of_run", []),
            }
    return None


def check_availability(train_number: str, travel_class: str, date: str) -> dict:
    """Simulated seat availability check."""
    import random

    train = get_details(train_number)
    if train is None:
        return {"error": f"Train {train_number} not found"}
    if travel_class.upper() not in train["classes"]:
        return {"error": f"Class {travel_class} not available on train {train_number}"}

    status, count = random.choice([
        ("AVAILABLE", random.randint(10, 150)),
        ("RAC", random.randint(1, 20)),
        ("WAITLIST", random.randint(1, 50)),
    ])

    fare = train.get("fares", {}).get(travel_class.upper())
    msg = (
        f"{count} seats available" if status == "AVAILABLE"
        else f"RAC {count}" if status == "RAC"
        else f"Waitlist {count}"
    )

    return {
        "train_number": train_number,
        "train_name": train["train_name"],
        "class": travel_class.upper(),
        "date": date,
        "status": status,
        "count": count,
        "fare": fare,
        "message": msg,
    }
