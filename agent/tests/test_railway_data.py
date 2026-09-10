"""
RailVox — Unit Tests for Railway Data Layer

Tests search, filtering, station normalization, and date handling.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import railway_data


class TestStationNormalization:
    """Tests for station name/alias resolution."""

    def test_exact_name(self):
        result = railway_data._normalize_station("Kharagpur Junction")
        assert result == "Kharagpur Junction"

    def test_alias_kolkata_to_howrah(self):
        result = railway_data._normalize_station("Kolkata")
        assert result == "Howrah Junction"

    def test_alias_calcutta(self):
        result = railway_data._normalize_station("Calcutta")
        assert result == "Howrah Junction"

    def test_code_kgp(self):
        result = railway_data._normalize_station("KGP")
        assert result == "Kharagpur Junction"

    def test_alias_bombay(self):
        result = railway_data._normalize_station("Bombay")
        assert result == "Mumbai CST"

    def test_alias_bangalore(self):
        result = railway_data._normalize_station("Bangalore")
        assert result == "Bengaluru City Junction"

    def test_unknown_station(self):
        result = railway_data._normalize_station("Atlantis")
        assert result == "Atlantis"


class TestTimePreference:
    """Tests for time-of-day filtering."""

    def test_morning(self):
        assert railway_data._matches_time_preference("08:00", "morning")
        assert not railway_data._matches_time_preference("14:00", "morning")

    def test_afternoon(self):
        assert railway_data._matches_time_preference("14:00", "afternoon")
        assert not railway_data._matches_time_preference("08:00", "afternoon")

    def test_evening(self):
        assert railway_data._matches_time_preference("17:15", "evening")
        assert railway_data._matches_time_preference("18:45", "evening")
        assert not railway_data._matches_time_preference("08:00", "evening")

    def test_night(self):
        assert railway_data._matches_time_preference("23:00", "night")
        assert not railway_data._matches_time_preference("14:00", "night")

    def test_any(self):
        assert railway_data._matches_time_preference("08:00", "any")
        assert railway_data._matches_time_preference("23:00", "any")


class TestSearch:
    """Tests for train search functionality."""

    def test_kharagpur_to_howrah(self):
        """The canonical test route — must return results."""
        results = railway_data.search(
            origin="Kharagpur",
            destination="Kolkata",
            date="2026-09-12",  # A Friday
        )
        assert len(results) > 0
        for r in results:
            assert "train_name" in r
            assert "departure" in r

    def test_kharagpur_to_howrah_evening(self):
        """Evening filter for the canonical test."""
        results = railway_data.search(
            origin="Kharagpur",
            destination="Kolkata",
            date="2026-09-12",
            time_preference="evening",
        )
        assert len(results) > 0
        for r in results:
            # All should be evening departures (after 4 PM)
            dep_minutes = railway_data._time_to_minutes(r["departure_24h"])
            assert dep_minutes >= 960  # 4:00 PM

    def test_no_results(self):
        """Route with no trains should return empty."""
        results = railway_data.search(
            origin="Atlantis",
            destination="Mordor",
            date="2026-09-12",
        )
        assert len(results) == 0

    def test_delhi_to_mumbai(self):
        """Popular route should have results."""
        results = railway_data.search(
            origin="New Delhi",
            destination="Mumbai",
            date="2026-09-12",
        )
        assert len(results) > 0


class TestDetails:
    """Tests for train detail lookup."""

    def test_existing_train(self):
        details = railway_data.get_details("12301")
        assert details is not None
        assert details["train_name"] == "Howrah Rajdhani Express"
        assert "fares" in details

    def test_nonexistent_train(self):
        details = railway_data.get_details("99999")
        assert details is None


class TestTimeFormatting:
    """Tests for time display formatting."""

    def test_12h_format_pm(self):
        assert railway_data._format_time_12h("17:15") == "5:15 PM"

    def test_12h_format_am(self):
        assert railway_data._format_time_12h("06:30") == "6:30 AM"

    def test_12h_format_noon(self):
        assert railway_data._format_time_12h("12:00") == "12:00 PM"

    def test_12h_format_midnight(self):
        assert railway_data._format_time_12h("00:00") == "12:00 AM"
