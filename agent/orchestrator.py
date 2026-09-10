"""
RailVox — Orchestrator / State Machine

Manages conversation state, generation counters, task lifecycle, and
the three-fence stale-result prevention system.

This is the core complexity of the project — isolated for testability.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from events import EventLogger, EventType, MetricsCollector


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ConversationState(str, Enum):
    """States in the conversation finite state machine."""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    TOOL_RUNNING = "tool_running"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    CANCELLING = "cancelling"
    ERROR = "error"


class TaskStatus(str, Enum):
    """Lifecycle status of a tool-call task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TaskRecord:
    """Tracks a single tool-call task through its lifecycle."""
    task_id: str
    generation: int
    tool_name: str
    tool_args: dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.monotonic)
    completed_at: Optional[float] = None
    result: Optional[Any] = None

    def mark_running(self):
        self.status = TaskStatus.RUNNING

    def mark_completed(self, result: Any):
        self.status = TaskStatus.COMPLETED
        self.completed_at = time.monotonic()
        self.result = result

    def mark_cancelled(self):
        self.status = TaskStatus.CANCELLED
        self.completed_at = time.monotonic()

    def mark_superseded(self):
        self.status = TaskStatus.SUPERSEDED
        self.completed_at = time.monotonic()


@dataclass
class SessionState:
    """
    Server-authoritative session state.

    This lives in the Python agent process. The client never mutates it.
    The generation counter is the linchpin of stale-result prevention.
    """
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    generation: int = 0
    conversation_state: ConversationState = ConversationState.IDLE

    # Current and historical tasks
    current_task: Optional[TaskRecord] = None
    tasks: list[TaskRecord] = field(default_factory=list)
    cancelled_task_ids: set[str] = field(default_factory=set)

    # Intent slots (accumulated across turns)
    intent_slots: dict[str, Any] = field(default_factory=lambda: {
        "origin": None,
        "destination": None,
        "date": None,
        "time_preference": None,
        "travel_class": None,
        "quota": None,
    })


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """
    Core state machine and generation-fencing logic.

    Responsibilities:
    - Manage conversation FSM transitions.
    - Maintain a monotonically increasing generation counter.
    - Track active tool-call tasks.
    - Provide the three fencing checkpoints that prevent stale results
      from reaching the user.
    """

    def __init__(self, session_id: str | None = None):
        self.state = SessionState(
            session_id=session_id or str(uuid.uuid4())[:12]
        )
        self.event_logger = EventLogger(self.state.session_id)
        self.metrics = MetricsCollector(self.event_logger)

        # Active asyncio task for the current tool call (cancellable)
        self._active_async_task: Optional[asyncio.Task] = None

        # Lock for generation increments (asyncio cooperative lock)
        self._generation_lock = asyncio.Lock()

    # -- Properties ----------------------------------------------------------

    @property
    def generation(self) -> int:
        return self.state.generation

    @property
    def conversation_state(self) -> ConversationState:
        return self.state.conversation_state

    @property
    def session_id(self) -> str:
        return self.state.session_id

    # -- State transitions ---------------------------------------------------

    def transition_to(self, new_state: ConversationState, trigger: str = ""):
        """Transition the FSM to a new state and log the event."""
        old_state = self.state.conversation_state
        self.state.conversation_state = new_state

        self.event_logger.log(
            EventType.STATE_TRANSITION,
            generation=self.generation,
            payload={
                "from": old_state.value,
                "to": new_state.value,
                "trigger": trigger,
            },
        )

    # -- Generation management -----------------------------------------------

    async def increment_generation(self) -> int:
        """
        Atomically increment the generation counter.

        Returns the new generation value. This is called on every user
        interruption to invalidate all in-flight work.
        """
        async with self._generation_lock:
            self.state.generation += 1
            return self.state.generation

    def is_stale(self, request_generation: int) -> bool:
        """Check if a request is stale (created at an older generation)."""
        return request_generation < self.state.generation

    # -- Interruption handling -----------------------------------------------

    async def handle_interruption(self) -> int:
        """
        Handle a user barge-in event.

        1. Increment generation counter (invalidates all in-flight work).
        2. Cancel active tool task if any.
        3. Log events.
        4. Transition to INTERRUPTED state.

        Returns the new generation value.
        """
        old_gen = self.generation

        # Log barge-in
        self.event_logger.log(
            EventType.USER_BARGE_IN,
            generation=old_gen,
            payload={
                "during_state": self.conversation_state.value,
                "agent_was_speaking": self.conversation_state == ConversationState.SPEAKING,
            },
        )

        # Record metric
        self.metrics.record_barge_in(old_gen)

        # Increment generation — this is the critical operation
        new_gen = await self.increment_generation()

        # Cancel active tool task
        await self._cancel_active_task(reason="user_interrupt")

        # Record cancel timing
        self.metrics.record_cancel_issued(new_gen)

        # Transition state
        self.transition_to(ConversationState.INTERRUPTED, trigger="user_barge_in")

        # Log TTS clear
        self.event_logger.log(
            EventType.TTS_CLEAR_SENT,
            generation=new_gen,
        )

        # Record playback silence (approximate — actual silence depends on WebRTC)
        self.metrics.record_playback_silence(old_gen)
        self.metrics.record_task_cancelled(new_gen)

        return new_gen

    async def _cancel_active_task(self, reason: str = "user_interrupt"):
        """Cancel the currently running tool task, if any."""
        if self._active_async_task and not self._active_async_task.done():
            self._active_async_task.cancel()

            if self.state.current_task:
                task = self.state.current_task
                task.mark_cancelled()
                self.state.cancelled_task_ids.add(task.task_id)

                self.event_logger.log(
                    EventType.TASK_CANCELLED,
                    generation=self.generation,
                    payload={
                        "task_id": task.task_id,
                        "generation": task.generation,
                        "reason": reason,
                    },
                )

    # -- Task tracking -------------------------------------------------------

    def create_task(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> TaskRecord:
        """Create and register a new task at the current generation."""
        task = TaskRecord(
            task_id=str(uuid.uuid4())[:8],
            generation=self.generation,
            tool_name=tool_name,
            tool_args=tool_args,
        )

        # Supersede current task if one exists
        if self.state.current_task and self.state.current_task.status == TaskStatus.RUNNING:
            old_task = self.state.current_task
            old_task.mark_superseded()

            self.event_logger.log(
                EventType.TASK_SUPERSEDED,
                generation=self.generation,
                payload={
                    "old_task_id": old_task.task_id,
                    "new_task_id": task.task_id,
                    "old_generation": old_task.generation,
                    "new_generation": task.generation,
                },
            )

        self.state.current_task = task
        self.state.tasks.append(task)

        self.event_logger.log(
            EventType.TASK_CREATED,
            generation=self.generation,
            payload={
                "task_id": task.task_id,
                "generation": task.generation,
                "tool_name": tool_name,
                "tool_args": tool_args,
            },
        )

        return task

    def register_async_task(self, async_task: asyncio.Task):
        """Register the asyncio.Task handle for the current tool call."""
        self._active_async_task = async_task

    # -- Fencing checkpoints -------------------------------------------------

    def fence_tool_result(
        self,
        task_id: str,
        dispatch_generation: int,
        result: Any,
    ) -> bool:
        """
        FENCE 1: Check generation before allowing a tool result into the LLM context.

        Returns True if the result is fresh (should be used).
        Returns False if the result is stale (should be discarded).
        """
        if self.is_stale(dispatch_generation):
            self.event_logger.log(
                EventType.TOOL_RESULT_DISCARDED,
                generation=self.generation,
                payload={
                    "task_id": task_id,
                    "reason": "stale_generation",
                    "dispatch_gen": dispatch_generation,
                    "current_gen": self.generation,
                },
            )
            return False

        self.event_logger.log(
            EventType.TOOL_RESULT_RECEIVED,
            generation=self.generation,
            payload={
                "task_id": task_id,
                "generation_at_dispatch": dispatch_generation,
                "result_summary": str(result)[:200],
            },
        )
        return True

    def fence_llm_response(
        self,
        response_text: str,
        response_generation: int,
    ) -> bool:
        """
        FENCE 2: Check generation before committing an LLM response.

        Returns True if the response is fresh.
        Returns False if the response is stale.
        """
        if self.is_stale(response_generation):
            self.event_logger.log(
                EventType.LLM_RESPONSE_DISCARDED,
                generation=self.generation,
                payload={
                    "response_generation": response_generation,
                    "current_generation": self.generation,
                    "reason": "stale_generation",
                },
            )
            return False

        self.event_logger.log(
            EventType.LLM_RESPONSE_COMMITTED,
            generation=self.generation,
            payload={
                "generation": response_generation,
                "response_text": response_text[:200],
            },
        )
        return True

    def fence_tts_request(
        self,
        text: str,
        tts_generation: int,
    ) -> bool:
        """
        FENCE 3: Check generation before enqueuing TTS synthesis.

        Returns True if synthesis should proceed.
        Returns False if the text is stale and should not be spoken.
        """
        if self.is_stale(tts_generation):
            self.event_logger.log(
                EventType.TTS_SYNTHESIS_SKIPPED,
                generation=self.generation,
                payload={
                    "tts_generation": tts_generation,
                    "current_generation": self.generation,
                    "reason": "stale_generation",
                },
            )
            return False

        self.event_logger.log(
            EventType.TTS_SYNTHESIS_STARTED,
            generation=self.generation,
            payload={
                "generation": tts_generation,
                "text_length": len(text),
            },
        )
        return True

    # -- Speech events -------------------------------------------------------

    def record_user_speech_final(self, transcript: str, confidence: float = 1.0):
        """Record a final user speech transcript."""
        self.event_logger.log(
            EventType.USER_SPEECH_FINAL,
            generation=self.generation,
            payload={
                "transcript": transcript,
                "confidence": confidence,
                "is_final": True,
            },
        )
        self.metrics.record_user_speech_end(self.generation)

    def record_user_speech_partial(self, transcript: str, confidence: float = 0.0):
        """Record a partial (interim) user speech transcript."""
        self.event_logger.log(
            EventType.USER_SPEECH_PARTIAL,
            generation=self.generation,
            payload={
                "transcript": transcript,
                "confidence": confidence,
                "is_final": False,
            },
        )

    # -- Metrics passthrough -------------------------------------------------

    def record_llm_first_token(self):
        self.metrics.record_llm_first_token(self.generation)

    def record_rime_first_audio(self):
        self.metrics.record_rime_first_audio(self.generation)

    def record_playback_start(self):
        self.metrics.record_playback_start(self.generation)

    def finalize_turn_metrics(self):
        """Compute and log final metrics for the current turn."""
        return self.metrics.finalize_turn(self.generation)

    # -- Data channel messages for frontend ----------------------------------

    def get_state_update_message(self) -> dict:
        """Build a state update message for the frontend data channel."""
        return {
            "type": "state_update",
            "state": self.conversation_state.value,
            "generation": self.generation,
            "session_id": self.session_id,
        }

    def get_metrics_message(self) -> dict:
        """Build a metrics update message for the frontend debug panel."""
        latest_metrics = {}
        all_metrics = self.metrics.get_all_metrics()
        if all_metrics:
            latest_metrics = all_metrics[-1]

        return {
            "type": "metrics_update",
            "metrics": {
                **latest_metrics,
                "generation": self.generation,
                "stale_results_discarded": len(
                    self.event_logger.find_events(EventType.TOOL_RESULT_DISCARDED)
                ),
                "tasks_cancelled": len(self.state.cancelled_task_ids),
            },
        }
