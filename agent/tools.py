"""
tools.py — tool definitions for train search, details, and availability.

These are called by the LLM via function calling. Each search has a
simulated delay to mimic real IRCTC API latency (good for demoing interruptions).
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta

from livekit.agents import RunContext, function_tool

import railway_data


def _resolve_relative_date(date_str: str) -> str:
    """Turn 'tomorrow', 'Friday' etc into YYYY-MM-DD."""
    today = datetime.now()
    s = date_str.strip().lower()

    if s == "today":
        return today.strftime("%Y-%m-%d")
    elif s == "tomorrow":
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, day in enumerate(day_names):
        if day in s:
            diff = i - today.weekday()
            if diff <= 0:
                diff += 7
            return (today + timedelta(days=diff)).strftime("%Y-%m-%d")

    return date_str.strip()


@function_tool
async def search_trains(
    context: RunContext,
    origin: str,
    destination: str,
    date: str,
    time_preference: str = "any",
    travel_class: str = "any",
) -> str:
    """
    Search for trains between two Indian railway stations.

    Args:
        origin: Departure station name (e.g. "Kolkata", "Kharagpur Junction")
        destination: Arrival station name (e.g. "Mumbai", "New Delhi")
        date: Travel date — "today", "tomorrow", a day name like "Friday", or YYYY-MM-DD
        time_preference: "morning", "afternoon", "evening", "night", or "any"
        travel_class: "1A", "2A", "3A", "SL", "CC", "2S", or "any"
    """
    resolved = _resolve_relative_date(date)

    # Simulate IRCTC search latency — this is the window where users can barge in
    await asyncio.sleep(random.uniform(3.0, 8.0))

    results = railway_data.search(
        origin=origin,
        destination=destination,
        date=resolved,
        time_preference=time_preference or "any",
        travel_class=travel_class or "any",
    )

    if not results:
        return json.dumps({
            "found": 0,
            "message": f"No trains found from {origin} to {destination} on {resolved}.",
            "trains": [],
        })

    return json.dumps({
        "found": len(results),
        "date": resolved,
        "trains": results[:5],  # cap at 5 for voice readability
    })


@function_tool
async def get_train_details(context: RunContext, train_number: str) -> str:
    """
    Get full details for a specific train by number.

    Args:
        train_number: The 5-digit train number (e.g. "12301")
    """
    await asyncio.sleep(random.uniform(1.0, 3.0))

    details = railway_data.get_details(train_number)
    if not details:
        return json.dumps({"error": f"Train {train_number} not found."})

    return json.dumps(details)


@function_tool
async def check_availability(
    context: RunContext,
    train_number: str,
    travel_class: str,
    date: str,
) -> str:
    """
    Check seat availability for a train on a given date.

    Args:
        train_number: 5-digit train number
        travel_class: Class code — "1A", "2A", "3A", "SL", "CC", "2S"
        date: Travel date in YYYY-MM-DD or relative format
    """
    await asyncio.sleep(random.uniform(2.0, 5.0))

    resolved = _resolve_relative_date(date)
    result = railway_data.check_availability(train_number, travel_class, resolved)
    return json.dumps(result)


ALL_TOOLS = [search_trains, get_train_details, check_availability]
