"""
agent.py — main entrypoint for RailVox.

Sets up the LiveKit AgentSession with Rime TTS, Deepgram STT, Groq LLM,
and wires event hooks for barge-in handling and generation fencing.

Usage:
    python agent.py dev    # development
    python agent.py start  # production
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("railvox")


class RailVoxAgent:
    """Main voice agent. Wraps AgentSession with interruption handling."""

    def __init__(self):
        self.orchestrator: Orchestrator | None = None
        self._session: AgentSession | None = None
        self._room: rtc.Room | None = None

    async def start(self, ctx: JobContext):
        await ctx.connect()

        self.orchestrator = Orchestrator(session_id=ctx.room.name)
        self._room = ctx.room

        logger.info("agent starting | session=%s", self.orchestrator.session_id)

        today = datetime.now()
        date_context = (
            f"\n\nToday's date is {today.strftime('%A, %B %d, %Y')}. "
            f"Use this to resolve relative dates like 'tomorrow' or 'Friday'."
        )

        agent = Agent(
            instructions=SYSTEM_PROMPT + date_context,
            tools=ALL_TOOLS,
        )

        # VAD threshold raised slightly to filter background fan/room noise
        session = AgentSession(
            vad=silero.VAD.load(
                activation_threshold=0.6,
                min_silence_duration=0.5,
            ),
            stt=deepgram.STT(
                model="nova-2",
                language="en",
                interim_results=True,
                smart_format=True,
                punctuate=True,
            ),
            llm=groq.LLM(
                model="openai/gpt-oss-120b",
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
        self._register_event_handlers(session)

        await session.start(room=ctx.room, agent=agent)

        await session.say(
            "Hello! I'm RailVox, your railway search assistant. "
            "Tell me where you'd like to travel.",
            allow_interruptions=True,
        )

        logger.info("agent ready")

    def _register_event_handlers(self, session: AgentSession):
        @session.on("user_started_speaking")
        def on_user_started_speaking():
            logger.info("[VAD] user speaking | state=%s", self.orchestrator.conversation_state.value)
            if self.orchestrator.conversation_state in (
                ConversationState.SPEAKING,
                ConversationState.TOOL_RUNNING,
                ConversationState.THINKING,
            ):
                logger.info(
                    "barge-in | state=%s gen=%d",
                    self.orchestrator.conversation_state.value,
                    self.orchestrator.generation,
                )
                asyncio.create_task(self._handle_barge_in())
            else:
                self.orchestrator.transition_to(
                    ConversationState.LISTENING,
                    trigger="user_speech_start",
                )

        @session.on("user_speech_committed")
        def on_user_speech_committed(msg):
            text = msg.content if hasattr(msg, "content") else str(msg)
            logger.info("[STT] user said: %r", text)
            self.orchestrator.record_user_speech_final(text)
            self.orchestrator.transition_to(
                ConversationState.THINKING,
                trigger="user_speech_final",
            )
            self._publish_state_update()

        @session.on("agent_started_speaking")
        def on_agent_started_speaking():
            self.orchestrator.transition_to(
                ConversationState.SPEAKING,
                trigger="agent_speech_start",
            )
            self.orchestrator.record_playback_start()
            self._publish_state_update()

        @session.on("agent_stopped_speaking")
        def on_agent_stopped_speaking():
            if self.orchestrator.conversation_state == ConversationState.SPEAKING:
                self.orchestrator.transition_to(
                    ConversationState.IDLE,
                    trigger="agent_speech_complete",
                )
                self.orchestrator.finalize_turn_metrics()
                self._publish_state_update()
                self._publish_metrics_update()

        @session.on("function_calls_collected")
        def on_function_calls_collected(calls):
            self.orchestrator.transition_to(
                ConversationState.TOOL_RUNNING,
                trigger="tool_call_started",
            )
            for call in calls:
                tool_name = call.function_info.name if hasattr(call, 'function_info') else str(call)
                self.orchestrator.create_task(tool_name=tool_name, tool_args={})
            self._publish_state_update()

    async def _handle_barge_in(self):
        try:
            new_gen = await self.orchestrator.handle_interruption()
            logger.info(
                "barge-in handled | gen=%d cancelled=%d",
                new_gen,
                len(self.orchestrator.state.cancelled_task_ids),
            )
            self._publish_state_update()
            self._publish_metrics_update()
        except Exception as e:
            logger.error("barge-in error: %s", e, exc_info=True)

    def _publish_state_update(self):
        if self._room:
            try:
                msg = json.dumps(self.orchestrator.get_state_update_message())
                asyncio.create_task(
                    self._room.local_participant.publish_data(msg.encode(), reliable=True)
                )
            except Exception as e:
                logger.debug("state publish failed: %s", e)

    def _publish_metrics_update(self):
        if self._room:
            try:
                msg = json.dumps(self.orchestrator.get_metrics_message())
                asyncio.create_task(
                    self._room.local_participant.publish_data(msg.encode(), reliable=True)
                )
            except Exception as e:
                logger.debug("metrics publish failed: %s", e)


async def entrypoint(ctx: JobContext):
    agent = RailVoxAgent()
    await agent.start(ctx)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
