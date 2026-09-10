"""
RailVox — Unit Tests for Orchestrator

Tests the core state machine, generation counter, and fencing logic.
"""

import asyncio
import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator import Orchestrator, ConversationState, TaskStatus


@pytest.fixture
def orchestrator():
    """Create a fresh orchestrator for each test."""
    return Orchestrator(session_id="test-session")


class TestGenerationCounter:
    """Tests for the monotonic generation counter."""

    def test_initial_generation_is_zero(self, orchestrator):
        assert orchestrator.generation == 0

    @pytest.mark.asyncio
    async def test_increment_generation(self, orchestrator):
        new_gen = await orchestrator.increment_generation()
        assert new_gen == 1
        assert orchestrator.generation == 1

    @pytest.mark.asyncio
    async def test_multiple_increments(self, orchestrator):
        await orchestrator.increment_generation()
        await orchestrator.increment_generation()
        await orchestrator.increment_generation()
        assert orchestrator.generation == 3


class TestStaleDetection:
    """Tests for the is_stale check."""

    def test_current_generation_is_not_stale(self, orchestrator):
        assert not orchestrator.is_stale(0)

    @pytest.mark.asyncio
    async def test_old_generation_is_stale(self, orchestrator):
        await orchestrator.increment_generation()
        assert orchestrator.is_stale(0)
        assert not orchestrator.is_stale(1)

    @pytest.mark.asyncio
    async def test_multiple_generations_stale(self, orchestrator):
        for _ in range(5):
            await orchestrator.increment_generation()
        assert orchestrator.is_stale(0)
        assert orchestrator.is_stale(3)
        assert orchestrator.is_stale(4)
        assert not orchestrator.is_stale(5)


class TestFencing:
    """Tests for the three fencing checkpoints."""

    def test_fence_tool_result_fresh(self, orchestrator):
        """Fresh tool result should be accepted."""
        task = orchestrator.create_task("search_trains", {"origin": "Delhi"})
        assert orchestrator.fence_tool_result(task.task_id, 0, {"trains": []})

    @pytest.mark.asyncio
    async def test_fence_tool_result_stale(self, orchestrator):
        """Stale tool result should be discarded."""
        task = orchestrator.create_task("search_trains", {"origin": "Delhi"})
        await orchestrator.increment_generation()
        assert not orchestrator.fence_tool_result(task.task_id, 0, {"trains": []})

    def test_fence_llm_response_fresh(self, orchestrator):
        """Fresh LLM response should be committed."""
        assert orchestrator.fence_llm_response("I found trains", 0)

    @pytest.mark.asyncio
    async def test_fence_llm_response_stale(self, orchestrator):
        """Stale LLM response should be discarded."""
        await orchestrator.increment_generation()
        assert not orchestrator.fence_llm_response("Old response", 0)

    def test_fence_tts_request_fresh(self, orchestrator):
        """Fresh TTS request should proceed."""
        assert orchestrator.fence_tts_request("Speech text", 0)

    @pytest.mark.asyncio
    async def test_fence_tts_request_stale(self, orchestrator):
        """Stale TTS request should be skipped."""
        await orchestrator.increment_generation()
        assert not orchestrator.fence_tts_request("Old speech", 0)


class TestTaskLifecycle:
    """Tests for task creation and cancellation."""

    def test_create_task(self, orchestrator):
        task = orchestrator.create_task("search_trains", {"origin": "Mumbai"})
        assert task.status == TaskStatus.PENDING
        assert task.generation == 0
        assert orchestrator.state.current_task == task

    def test_supersede_task(self, orchestrator):
        task1 = orchestrator.create_task("search_trains", {"origin": "Delhi"})
        task1.mark_running()
        task2 = orchestrator.create_task("search_trains", {"origin": "Mumbai"})
        assert task1.status == TaskStatus.SUPERSEDED
        assert orchestrator.state.current_task == task2

    @pytest.mark.asyncio
    async def test_interruption_cancels_task(self, orchestrator):
        task = orchestrator.create_task("search_trains", {"origin": "Delhi"})
        task.mark_running()

        # Simulate an asyncio task
        async def fake_tool():
            await asyncio.sleep(10)

        async_task = asyncio.create_task(fake_tool())
        orchestrator.register_async_task(async_task)
        orchestrator.transition_to(ConversationState.TOOL_RUNNING)

        # Handle interruption
        new_gen = await orchestrator.handle_interruption()

        assert new_gen == 1
        assert task.status == TaskStatus.CANCELLED
        assert task.task_id in orchestrator.state.cancelled_task_ids
        assert async_task.cancelled()


class TestStateTransitions:
    """Tests for FSM state transitions."""

    def test_initial_state(self, orchestrator):
        assert orchestrator.conversation_state == ConversationState.IDLE

    def test_transition_to_listening(self, orchestrator):
        orchestrator.transition_to(ConversationState.LISTENING)
        assert orchestrator.conversation_state == ConversationState.LISTENING

    @pytest.mark.asyncio
    async def test_interruption_transitions_to_interrupted(self, orchestrator):
        orchestrator.transition_to(ConversationState.SPEAKING)
        await orchestrator.handle_interruption()
        assert orchestrator.conversation_state == ConversationState.INTERRUPTED


class TestEventLogging:
    """Tests for event logging during operations."""

    def test_task_created_event(self, orchestrator):
        orchestrator.create_task("search_trains", {"origin": "Delhi"})
        events = orchestrator.event_logger.find_events("task.created")
        assert len(events) == 1
        assert events[0].payload["tool_name"] == "search_trains"

    @pytest.mark.asyncio
    async def test_barge_in_event(self, orchestrator):
        orchestrator.transition_to(ConversationState.SPEAKING)
        await orchestrator.handle_interruption()
        events = orchestrator.event_logger.find_events("user.barge_in")
        assert len(events) == 1
        assert events[0].payload["agent_was_speaking"] is True

    @pytest.mark.asyncio
    async def test_stale_result_discarded_event(self, orchestrator):
        task = orchestrator.create_task("search_trains", {"origin": "Delhi"})
        await orchestrator.increment_generation()
        orchestrator.fence_tool_result(task.task_id, 0, {"trains": []})
        events = orchestrator.event_logger.find_events("tool.result.discarded")
        assert len(events) == 1
        assert events[0].payload["reason"] == "stale_generation"
