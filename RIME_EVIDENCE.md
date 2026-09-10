# RIME_EVIDENCE.md

## Hard Voice Claim

RailVox solves two hard voice engineering problems simultaneously:

1. **Interruption and recovery**: When the user speaks during agent TTS playback, audio stops within 200ms, in-flight tool tasks are cancelled, and stale results are fenced at three checkpoints (tool result ingestion, LLM response commit, TTS enqueue) to guarantee they never re-enter the conversation.

2. **Conversation continuity during tool work**: During 3–8 second simulated railway searches, the voice session remains responsive. The user can interrupt, modify slots, or cancel without losing conversation context.

## Rime Configuration

| Parameter | Value |
|---|---|
| Model ID | `coda` |
| Speaker | `celeste` |
| Language | `en` |
| Endpoint | `wss://users-ws.rime.ai/ws3` (via `livekit-plugins-rime`) |
| Audio Format | PCM |
| Sample Rate | 16000 Hz |
| Transport | WebSocket streaming (`use_websocket=True`) |
| Mid-stream cancel | `{"operation": "clear"}` via WebSocket |

## Acceptance Test Definition

### Test: Mid-Flight Slot Correction (Canonical)

**Precondition:** Agent is idle. Generation counter is at 0.

**Steps:**
1. User says: "Find trains from Kharagpur to Kolkata tomorrow."
2. Agent begins processing (THINKING → TOOL_RUNNING → SPEAKING filler).
3. At t+2 seconds, user interrupts: "Actually make it Friday evening."

**Expected Results:**
1. ✅ Old Rime audio playback stops within 200ms of barge-in detection.
2. ✅ Old tool task (T1) is marked CANCELLED; its eventual result is logged as `tool.result.discarded`.
3. ✅ New utterance is parsed as a modification (date→Friday, time→evening), not a new unrelated intent.
4. ✅ New task (T2) executes with `date=Friday` and `time_preference=evening`.
5. ✅ Final spoken response references only Friday evening trains — no mixing of stale data.

## Procedure

### Automated Test

```bash
cd agent
python scripts/run_acceptance_test.py --scenario canonical_friday --trials 20
```

### Manual Reproduction

1. Start agent and frontend per README.
2. Open browser, connect to session.
3. Speak: "Find trains from Kharagpur to Kolkata tomorrow."
4. Wait 2 seconds, then interrupt: "Actually make it Friday evening."
5. After response completes, check `agent/logs/{session_id}/events.jsonl`.
6. Verify conditions 1–5 from the event log.

### Event Log Verification

```bash
cd agent
python scripts/analyze_session.py --latest
```

This will report:
- Interrupt latency (barge-in → silence)
- Task cancellation count
- Stale result leakage rate
- Per-turn latency breakdown

## Quantitative Results

> **Note:** Fill in after running acceptance tests. Values below are targets.

| Metric | Target | Median | P95 | P99 | Trials |
|---|---|---|---|---|---|
| Interrupt latency (barge-in → silence) | < 200ms | _TBD_ | _TBD_ | _TBD_ | 20 |
| Cancel latency (interrupt → task cancelled) | < 50ms | _TBD_ | _TBD_ | _TBD_ | 20 |
| TTS stop latency (clear sent → audio flushed) | < 100ms | _TBD_ | _TBD_ | _TBD_ | 20 |
| Tool response latency (dispatch → result) | 3–8s | _TBD_ | _TBD_ | _TBD_ | 20 |
| Stale result leakage rate | 0% | _TBD_ | — | — | 20 |

## Second Stress Variant: Rapid Double Interruption

**Test:** User interrupts twice in rapid succession (< 500ms apart) with different instructions.

1. "Find trains from Delhi to Jaipur on Saturday."
2. (+1.5s) "Actually, Agra."
3. (+0.4s) "No wait, Lucknow."

**Expected:** Only Lucknow results spoken. Two `task.cancelled` events. Generation increments from 0→1→2. Zero stale result leakage.

## Limitations

1. Tool latency is simulated (`asyncio.sleep`), not a real external API.
2. Audio interrupt latency includes LiveKit's WebRTC transport overhead (~50ms).
3. Tests use Chrome browser's WebRTC AEC — results may differ on other browsers.
4. The 200ms interrupt latency target is measured server-side (barge-in detection to audio track mute).
5. STT accuracy on Indian English accents (Deepgram Nova-2) is not separately benchmarked.
