"""
RailVox — Tool Definitions

LiveKit @function_tool decorated functions for railway timetable search.
These are called by the LLM via OpenAI's tool-calling protocol.

Each tool includes simulated realistic latency (3-8 seconds) to demonstrate
conversation continuity during long-running operations.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta

from livekit.agents import RunContext, function_tool

import railway_data


def _resolve_relative_date(date_str: str) -> str:
    """
    Resolve relative date references to YYYY-MM-DD format.

    Handles: "today", "tomorrow", day names ("Friday", "Monday"), and
    already-formatted dates.
    """
    today = datetime.now()
    date_lower = date_str.strip().lower()

    if date_lower == "today":
        return today.strftime("%Y-%m-%d")
    elif date_lower == "tomorrow":
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        # Try to match day names (Monday, Tuesday, etc.)
        day_names = [
            "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday",
        ]
        for i, day in enumerate(day_names):
            if day in date_lower:
                # Find the next occurrence of this day
                current_day = today.weekday()  # 0=Monday
                days_ahead = i - current_day
                if days_ahead <= 0:
                    days_ahead += 7
                target = today + timedelta(days=days_ahead)
                return target.strftime("%Y-%m-%d")

        # Try parsing as a date directly
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%B %d", "%b %d"):
            try:
                parsed = datetime.strptime(date_str.strip(), fmt)
                # If year is 1900 (no year in format), use current year
                if parsed.year == 1900:
                    parsed = parsed.replace(year=today.year)
                    # If the date has passed this year, use next year
                    if parsed < today:
                        parsed = parsed.replace(year=today.year + 1)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Fallback: return as-is and let the search handle it
        return date_str.strip()


@function_tool
async def search_trains(
    ctx: RunContext,
    origin: str,
    destination: str,
    date: str,
    time_preference: str = "any",
    travel_class: str = "any",
) -> str:
    """Search for trains between two Indian railway stations on a specific date.

    Use this tool when the user asks to find trains, check schedules, or look up
    train options between two cities or stations.

    Args:
        origin: The origin station name or city. Examples: "Kharagpur",
            "New Delhi", "Mumbai", "Bangalore".
        destination: The destination station name or city. Examples: "Kolkata",
            "Howrah", "Chennai", "Pune".
        date: The travel date. Can be a relative reference like "tomorrow",
            "Friday", "next Monday", or an absolute date like "2026-09-12".
        time_preference: Preferred time of day for departure. One of:
            "morning" (6 AM - 12 PM), "afternoon" (12 PM - 4 PM),
            "evening" (4 PM - 9 PM), "night" (9 PM - 6 AM), or "any".
            Defaults to "any".
        travel_class: Preferred travel class. One of: "1A" (First AC),
            "2A" (Second AC), "3A" (Third AC), "SL" (Sleeper),
            "CC" (AC Chair Car), "2S" (Second Sitting), or "any".
            Defaults to "any".

    Returns:
        JSON string with a list of matching trains, or an error message
        if no trains are found.
    """
    # Resolve relative dates
    resolved_date = _resolve_relative_date(date)

    # Simulate realistic IRCTC search latency (3-8 seconds)
    # This is the critical point where asyncio.CancelledError can be raised
    # if the user interrupts during the search.
    latency = random.uniform(3.0, 8.0)
    await asyncio.sleep(latency)

    # Perform the search
    results = railway_data.search(
        origin=origin,
        destination=destination,
        date=resolved_date,
        time_preference=time_preference or "any",
        travel_class=travel_class or "any",
    )

    if not results:
        return json.dumps({
            "status": "no_results",
            "message": (
                f"No trains found from {origin} to {destination} on {resolved_date}"
                + (f" in the {time_preference}" if time_preference and time_preference != "any" else "")
                + ". Try a different date or check the station names."
            ),
            "query": {
                "origin": origin,
                "destination": destination,
                "date": resolved_date,
                "time_preference": time_preference,
                "travel_class": travel_class,
            },
        })

    return json.dumps({
        "status": "success",
        "count": len(results),
        "date": resolved_date,
        "results": results[:5],  # Limit to top 5 for conciseness
        "query": {
            "origin": origin,
            "destination": destination,
            "date": resolved_date,
            "time_preference": time_preference,
            "travel_class": travel_class,
        },
    })


@function_tool
async def get_train_details(
    ctx: RunContext,
    train_number: str,
) -> str:
    """Get detailed information about a specific train including stops, fares,
    and amenities.

    Use this tool when the user asks for more details about a specific train,
    wants to know the fare, stops, or other information.

    Args:
        train_number: The 5-digit Indian Railways train number.
            Example: "12301" for Howrah Rajdhani Express.

    Returns:
        JSON string with detailed train information, or an error if not found.
    """
    # Shorter latency for detail lookups (1-3 seconds)
    await asyncio.sleep(random.uniform(1.0, 3.0))

    details = railway_data.get_details(train_number)

    if details is None:
        return json.dumps({
            "status": "not_found",
            "message": f"Train number {train_number} not found. Please check the number and try again.",
        })

    return json.dumps({
        "status": "success",
        **details,
    })


@function_tool
async def check_availability(
    ctx: RunContext,
    train_number: str,
    travel_class: str,
    date: str,
) -> str:
    """Check seat availability for a specific train, class, and travel date.

    Use this tool when the user asks about seat availability, whether seats
    are available, or wants to know the booking status.

    Args:
        train_number: The 5-digit Indian Railways train number.
        travel_class: The travel class to check. One of: "1A", "2A", "3A",
            "SL", "CC", "2S".
        date: The travel date in YYYY-MM-DD format or a relative reference.

    Returns:
        JSON string with availability status (AVAILABLE, RAC, or WAITLIST),
        count, and fare information.
    """
    resolved_date = _resolve_relative_date(date)

    # Simulate availability check latency (2-5 seconds)
    await asyncio.sleep(random.uniform(2.0, 5.0))

    result = railway_data.check_availability(
        train_number=train_number,
        travel_class=travel_class,
        date=resolved_date,
    )

    return json.dumps(result)


# List of all tools for registration with AgentSession
ALL_TOOLS = [search_trains, get_train_details, check_availability]
