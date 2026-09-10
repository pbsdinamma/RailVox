"""
RailVox — Event Types, Event Logger, and Metrics Collector

Provides structured event logging (append-only JSONL) and per-turn
latency metrics for observability and evidence generation.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Event data model
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """All event types in the RailVox event taxonomy."""

    # User speech events
    USER_SPEECH_PARTIAL = "user.speech.partial"
    USER_SPEECH_FINAL = "user.speech.final"
    USER_BARGE_IN = "user.barge_in"

    # Task lifecycle
    TASK_CREATED = "task.created"
    TASK_SUPERSEDED = "task.superseded"
    TASK_CANCELLED = "task.cancelled"

    # Tool events
    TOOL_DISPATCHED = "tool.dispatched"
    TOOL_RESULT_RECEIVED = "tool.result.received"
    TOOL_RESULT_DISCARDED = "tool.result.discarded"

    # LLM events
    LLM_RESPONSE_STARTED = "llm.response.started"
    LLM_RESPONSE_COMMITTED = "llm.response.committed"
    LLM_RESPONSE_DISCARDED = "llm.response.discarded"

    # TTS events
    TTS_SYNTHESIS_STARTED = "tts.synthesis.started"
    TTS_SYNTHESIS_SKIPPED = "tts.synthesis.skipped"
    TTS_CHUNK_ENQUEUED = "tts.chunk.enqueued"
    TTS_PLAYBACK_STARTED = "tts.playback.started"
    TTS_PLAYBACK_STOPPED = "tts.playback.stopped"
    TTS_CLEAR_SENT = "tts.clear.sent"
    TTS_FALLBACK_ACTIVATED = "tts.fallback.activated"

    # State machine
    STATE_TRANSITION = "state.transition"

    # Intent tracking
    INTENT_SLOTS_UPDATED = "intent.slots.updated"

    # Assistant
    ASSISTANT_RESPONSE_COMMITTED = "assistant.response.committed"

    # Metrics
    METRICS_TURN_COMPLETE = "metrics.turn.complete"


@dataclass
class Event:
    """A single event in the append-only event log."""

    event_type: str
    timestamp: float  # time.monotonic()
    wall_time: str  # ISO 8601
    session_id: str
    generation: int
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


# ---------------------------------------------------------------------------
# Event Logger — append-only JSONL per session
# ---------------------------------------------------------------------------

class EventLogger:
    """Append-only JSONL event logger for a single session."""

    def __init__(self, session_id: str, log_dir: str = "logs"):
        self.session_id = session_id
        self.log_dir = Path(log_dir) / session_id
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "events.jsonl"
        self._events: list[Event] = []

    def log(
        self,
        event_type: str | EventType,
        generation: int,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        """Log an event and append it to the JSONL file."""
        if isinstance(event_type, EventType):
            event_type = event_type.value

        event = Event(
            event_type=event_type,
            timestamp=time.monotonic(),
            wall_time=datetime.now(timezone.utc).isoformat(),
            session_id=self.session_id,
            generation=generation,
            payload=payload or {},
        )

        self._events.append(event)

        # Append to JSONL file
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(event.to_json() + "\n")

        # Structured console log
        logger.info(
            event_type,
            session_id=self.session_id,
            generation=generation,
            **event.payload,
        )

        return event

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    def find_events(
        self,
        event_type: str | EventType,
        predicate: Any = None,
    ) -> list[Event]:
        """Find events matching a type and optional predicate."""
        if isinstance(event_type, EventType):
            event_type = event_type.value
        matches = [e for e in self._events if e.event_type == event_type]
        if predicate:
            matches = [e for e in matches if predicate(e)]
        return matches


# ---------------------------------------------------------------------------
# Metrics Collector — per-turn latency measurements
# ---------------------------------------------------------------------------

@dataclass
class TurnMetrics:
    """Latency measurements for a single conversational turn."""

    generation: int
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Normal turn timestamps (time.monotonic())
    t_user_speech_end: Optional[float] = None
    t_stt_final: Optional[float] = None
    t_llm_first_token: Optional[float] = None
    t_rime_first_audio: Optional[float] = None
    t_playback_start: Optional[float] = None

    # Interruption timestamps
    t_barge_in_onset: Optional[float] = None
    t_playback_silence: Optional[float] = None
    t_cancel_issued: Optional[float] = None
    t_task_cancelled: Optional[float] = None

    def compute_latencies(self) -> dict[str, float | None]:
        """Compute derived latency metrics in milliseconds."""
        def delta_ms(end: Optional[float], start: Optional[float]) -> float | None:
            if end is not None and start is not None:
                return (end - start) * 1000
            return None

        return {
            "e2e_response_ms": delta_ms(self.t_playback_start, self.t_user_speech_end),
            "stt_latency_ms": delta_ms(self.t_stt_final, self.t_user_speech_end),
            "stt_to_llm_ms": delta_ms(self.t_llm_first_token, self.t_stt_final),
            "llm_to_tts_ms": delta_ms(self.t_rime_first_audio, self.t_llm_first_token),
            "tts_to_playback_ms": delta_ms(self.t_playback_start, self.t_rime_first_audio),
            "interrupt_latency_ms": delta_ms(self.t_playback_silence, self.t_barge_in_onset),
            "cancel_latency_ms": delta_ms(self.t_task_cancelled, self.t_barge_in_onset),
            "tts_stop_latency_ms": delta_ms(
                self.t_playback_silence, self.t_cancel_issued
            ),
        }


class MetricsCollector:
    """Collects per-turn metrics across a session."""

    def __init__(self, event_logger: EventLogger):
        self.event_logger = event_logger
        self._turns: dict[int, TurnMetrics] = {}  # keyed by generation

    def get_or_create_turn(self, generation: int) -> TurnMetrics:
        if generation not in self._turns:
            self._turns[generation] = TurnMetrics(generation=generation)
        return self._turns[generation]

    def record_user_speech_end(self, generation: int):
        turn = self.get_or_create_turn(generation)
        turn.t_user_speech_end = time.monotonic()
        turn.t_stt_final = turn.t_user_speech_end  # Same event for our purposes

    def record_llm_first_token(self, generation: int):
        turn = self.get_or_create_turn(generation)
        turn.t_llm_first_token = time.monotonic()

    def record_rime_first_audio(self, generation: int):
        turn = self.get_or_create_turn(generation)
        turn.t_rime_first_audio = time.monotonic()

    def record_playback_start(self, generation: int):
        turn = self.get_or_create_turn(generation)
        turn.t_playback_start = time.monotonic()

    def record_barge_in(self, generation: int):
        turn = self.get_or_create_turn(generation)
        turn.t_barge_in_onset = time.monotonic()

    def record_playback_silence(self, generation: int):
        turn = self.get_or_create_turn(generation)
        turn.t_playback_silence = time.monotonic()

    def record_cancel_issued(self, generation: int):
        turn = self.get_or_create_turn(generation)
        turn.t_cancel_issued = time.monotonic()

    def record_task_cancelled(self, generation: int):
        turn = self.get_or_create_turn(generation)
        turn.t_task_cancelled = time.monotonic()

    def finalize_turn(self, generation: int):
        """Compute and log final metrics for a completed turn."""
        turn = self.get_or_create_turn(generation)
        latencies = turn.compute_latencies()

        self.event_logger.log(
            EventType.METRICS_TURN_COMPLETE,
            generation=generation,
            payload={"turn_id": turn.turn_id, **latencies},
        )

        return latencies

    def get_all_metrics(self) -> list[dict]:
        """Get metrics for all turns."""
        results = []
        for gen in sorted(self._turns.keys()):
            turn = self._turns[gen]
            results.append(
                {
                    "generation": gen,
                    "turn_id": turn.turn_id,
                    **turn.compute_latencies(),
                }
            )
        return results
