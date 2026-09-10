"""
RailVox — LiveKit Agent Entrypoint

This is the main entry point for the RailVox voice agent. It sets up the
LiveKit AgentSession with Rime TTS, Deepgram STT, Groq Llama 3, and
registers event hooks for interruption handling and generation fencing.

Run with:
    python agent.py dev        # Development mode (auto-reload)
    python agent.py start      # Production mode
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import deepgram, groq, rime, silero

from orchestrator import ConversationState, Orchestrator
from prompts import SYSTEM_PROMPT
from tools import ALL_TOOLS

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("railvox")


class RailVoxAgent:
    """
    RailVox voice agent with generation-fenced interruption handling.

    This class wraps the LiveKit AgentSession with:
    - Orchestrator for state machine + generation counters
    - Event hooks for barge-in detection and cancellation
    - Data channel messaging for frontend state/metrics
    """

    def __init__(self):
        self.orchestrator: Orchestrator | None = None
        self._session: AgentSession | None = None
        self._room: rtc.Room | None = None

    async def start(self, ctx: JobContext):
        """Called when a new participant joins the LiveKit room."""
        await ctx.connect()

        # Initialize orchestrator for this session
        self.orchestrator = Orchestrator(session_id=ctx.room.name)
        self._room = ctx.room

        logger.info(
            "RailVox agent starting | session=%s", self.orchestrator.session_id
        )

        # Build the date context for the system prompt
        today = datetime.now()
        date_context = (
            f"\n\nToday's date is {today.strftime('%A, %B %d, %Y')}. "
            f"Use this to resolve relative dates like 'tomorrow' or 'Friday'."
        )

        # Create the agent with our system prompt and tools
        agent = Agent(
            instructions=SYSTEM_PROMPT + date_context,
            tools=ALL_TOOLS,
        )

        # Configure the session with Rime TTS (WebSocket streaming),
        # Deepgram STT, Groq Llama 3, and Silero VAD
        session = AgentSession(
            vad=silero.VAD.load(),
            stt=deepgram.STT(
                model="nova-2",
                language="en",
                interim_results=True,
                smart_format=True,
                punctuate=True,
            ),
            llm=groq.LLM(
                model="llama-3.3-70b-versatile",
                temperature=0.7,
            ),
            tts=rime.TTS(
                model="coda",
                speaker="celeste",
                use_websocket=True,
                segment="bySentence",
                speed_alpha=1.0,
            ),
        )

        self._session = session

        # Register event handlers for interruption and observability
        self._register_event_handlers(session)

        # Start the session
        await session.start(
            room=ctx.room,
            agent=agent,
        )

        # Send initial greeting — brief, not a full demo
        # (Greeting is NOT the core demo — it's just UX polish)
        await session.say(
            "Hello! I'm RailVox, your railway search assistant. "
            "Tell me where you'd like to travel.",
            allow_interruptions=True,
        )

        logger.info("RailVox agent started and greeting sent")

    def _register_event_handlers(self, session: AgentSession):
        """
        Register event handlers on the AgentSession for:
        - User speech events (partial + final transcripts)
        - Interruption / barge-in detection
        - Agent speech events
        - Tool call lifecycle
        """

        # -- User started speaking (barge-in detection) ----------------------
        @session.on("user_started_speaking")
        def on_user_started_speaking():
            """
            Fired when VAD detects user speech.
            If the agent is currently speaking, this is a barge-in.
            LiveKit automatically stops TTS and sends Rime 'clear'.
            We increment the generation counter and cancel active tasks.
            """
            if self.orchestrator.conversation_state in (
                ConversationState.SPEAKING,
                ConversationState.TOOL_RUNNING,
                ConversationState.THINKING,
            ):
                logger.info(
                    "BARGE-IN detected during state=%s, gen=%d",
                    self.orchestrator.conversation_state.value,
                    self.orchestrator.generation,
                )
                # Handle interruption asynchronously
                asyncio.create_task(self._handle_barge_in())
            else:
                self.orchestrator.transition_to(
                    ConversationState.LISTENING,
                    trigger="user_speech_start",
                )

        # -- User speech committed (final transcript) ------------------------
        @session.on("user_speech_committed")
        def on_user_speech_committed(msg):
            """Final user transcript received — log and update state."""
            text = msg.content if hasattr(msg, "content") else str(msg)
            self.orchestrator.record_user_speech_final(text)
            self.orchestrator.transition_to(
                ConversationState.THINKING,
                trigger="user_speech_final",
            )
            self._publish_state_update()

        # -- Agent started speaking ------------------------------------------
        @session.on("agent_started_speaking")
        def on_agent_started_speaking():
            """Agent TTS playback has begun."""
            self.orchestrator.transition_to(
                ConversationState.SPEAKING,
                trigger="agent_speech_start",
            )
            self.orchestrator.record_playback_start()
            self._publish_state_update()

        # -- Agent stopped speaking ------------------------------------------
        @session.on("agent_stopped_speaking")
        def on_agent_stopped_speaking():
            """Agent TTS playback completed or was interrupted."""
            if self.orchestrator.conversation_state == ConversationState.SPEAKING:
                self.orchestrator.transition_to(
                    ConversationState.IDLE,
                    trigger="agent_speech_complete",
                )
                self.orchestrator.finalize_turn_metrics()
                self._publish_state_update()
                self._publish_metrics_update()

        # -- Tool call started -----------------------------------------------
        @session.on("function_calls_collected")
        def on_function_calls_collected(calls):
            """Tool calls about to be executed — track them."""
            self.orchestrator.transition_to(
                ConversationState.TOOL_RUNNING,
                trigger="tool_call_started",
            )
            for call in calls:
                tool_name = call.function_info.name if hasattr(call, 'function_info') else str(call)
                self.orchestrator.create_task(
                    tool_name=tool_name,
                    tool_args={},
                )
            self._publish_state_update()

    async def _handle_barge_in(self):
        """
        Handle a user barge-in event.

        This is the core of the hard voice engineering problem:
        1. Increment generation counter (fences all stale work).
        2. Cancel active tool task.
        3. LiveKit automatically handles TTS stop + Rime clear.
        """
        try:
            new_gen = await self.orchestrator.handle_interruption()
            logger.info(
                "Barge-in handled | new_gen=%d | tasks_cancelled=%d",
                new_gen,
                len(self.orchestrator.state.cancelled_task_ids),
            )
            self._publish_state_update()
            self._publish_metrics_update()
        except Exception as e:
            logger.error("Error handling barge-in: %s", e, exc_info=True)

    def _publish_state_update(self):
        """Send a state update to the frontend via LiveKit data channel."""
        if self._room:
            try:
                message = json.dumps(
                    self.orchestrator.get_state_update_message()
                )
                # Publish to all participants in the room
                asyncio.create_task(
                    self._room.local_participant.publish_data(
                        message.encode(),
                        reliable=True,
                    )
                )
            except Exception as e:
                logger.debug("Failed to publish state update: %s", e)

    def _publish_metrics_update(self):
        """Send a metrics update to the frontend via LiveKit data channel."""
        if self._room:
            try:
                message = json.dumps(
                    self.orchestrator.get_metrics_message()
                )
                asyncio.create_task(
                    self._room.local_participant.publish_data(
                        message.encode(),
                        reliable=True,
                    )
                )
            except Exception as e:
                logger.debug("Failed to publish metrics update: %s", e)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def entrypoint(ctx: JobContext):
    """LiveKit agent entrypoint — creates and starts a RailVoxAgent."""
    agent = RailVoxAgent()
    await agent.start(ctx)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        ),
    )
