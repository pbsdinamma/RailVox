# RailVox 🚂🎤

**Voice-native Indian railway search assistant with mid-flight slot correction and stale-result fencing.**

Built for the DataForge × Pathway × Rime Hackathon.

---

## What it does

RailVox lets you search Indian railway trains entirely by voice — no typing, no forms. You speak a query like *"Find me a sleeper train from Kolkata to Mumbai tomorrow evening"*, the agent searches, and reads results back in natural speech using Rime Coda TTS.

The hard problem it solves: **mid-flight interruption with zero stale data leakage.** If you interrupt while the agent is mid-search or mid-response, the old query is cancelled, the new one takes over, and the spoken response only ever reflects the latest request. This is significantly harder than it sounds because STT, LLM, and TTS all pipeline asynchronously.

---

## Architecture

```
Mic → LiveKit WebRTC → Deepgram Nova-2 STT
    → Groq LLM (openai/gpt-oss-120b, tool-calling)
    → Rime Coda TTS (WebSocket streaming)
    → LiveKit WebRTC → Speaker
```

### Interruption handling

Every request is tagged with a monotonically increasing **generation counter**. On barge-in:

1. Generation counter increments atomically.
2. In-flight `asyncio.Task` (the tool call) is cancelled.
3. Rime receives `{"operation": "clear"}` to flush pending audio.
4. Three fences block stale results from re-entering the pipeline:
   - **Fence 1 — Tool result:** generation check before result enters LLM context.
   - **Fence 2 — LLM response:** generation check before committing text.
   - **Fence 3 — TTS enqueue:** generation check before sending to Rime.

This guarantees that even if the network delivers a stale tool response after cancellation, it is silently discarded and never spoken.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- LiveKit Cloud account (free tier works)
- API keys: Rime, Deepgram, Groq, LiveKit

### Setup

```bash
# 1. Clone
git clone https://github.com/pbsdinamma/RailVox.git
cd RailVox

# 2. Agent
cp agent/.env.example agent/.env
# fill in your keys in agent/.env

cd agent
pip install -r requirements.txt
python agent.py dev

# 3. Frontend (separate terminal)
cp frontend/.env.example frontend/.env
# fill in the same LiveKit + Rime keys

cd frontend
npm install
npm run dev

# 4. Open http://localhost:3000
```

---

## Rime Configuration

| Parameter | Value |
|---|---|
| **Model ID** | `coda` |
| **Speaker** | `celeste` |
| **Language** | `en` |
| **Endpoint** | `wss://users-ws.rime.ai/ws3` (via `livekit-plugins-rime`) |
| **Audio Format** | PCM |
| **Sample Rate** | 16,000 Hz |
| **Transport** | WebSocket streaming (`use_websocket=True`) |
| **Segmentation** | `bySentence` — each sentence streams as soon as the LLM produces it |

Rime is the **sole default TTS provider**. There is no fallback active in the judged flow.

---

## Third-Party Services

| Service | Role | Config |
|---|---|---|
| **Rime** | TTS — primary | Coda, celeste, en, WebSocket |
| **Deepgram** | STT | Nova-2, en-IN, streaming, smart_format |
| **Groq** | LLM | openai/gpt-oss-120b, tool-calling |
| **LiveKit** | Transport + orchestration | Cloud, WebRTC, data channel |
| **Silero VAD** | Voice activity detection | activation_threshold=0.6 |

---

## Project Structure

```
RailVox/
├── agent/
│   ├── agent.py          # AgentSession setup, event hooks
│   ├── orchestrator.py   # State machine + generation fencing
│   ├── tools.py          # search_trains, get_train_details, check_availability
│   ├── railway_data.py   # Timetable search over static JSON
│   ├── events.py         # Structured event logging + latency metrics
│   ├── prompts.py        # LLM system prompt
│   ├── data/
│   │   └── timetable.json  # ~60 trains, major Indian routes
│   ├── scripts/
│   │   └── analyze_session.py  # Post-session latency analysis
│   └── tests/
│       ├── test_orchestrator.py
│       └── test_railway_data.py
├── frontend/
│   └── src/
│       ├── app/           # Next.js app router
│       └── components/    # VoiceSession, ConversationView, MetricsPanel
├── README.md
└── RIME_EVIDENCE.md
```

---

## Known Limitations

1. **Static timetable** — ~60 trains hardcoded in `data/timetable.json`. Not connected to live IRCTC APIs.
2. **Simulated search latency** — tool calls sleep for 3–8 seconds to mimic real IRCTC response time. This is intentional for demoing interruption, not a real API constraint.
3. **English only** — no Hindi or regional language support in v1.
4. **No booking** — search and information only.
5. **AEC quality** — echo cancellation is browser WebRTC AEC. Performance varies by device; use headphones for best results.
6. **STT accuracy on Indian accents** — Deepgram Nova-2 handles Indian English well but is not separately benchmarked for accent variants.

---

## Failure Behavior

| Failure | Behavior |
|---|---|
| STT connection drops | LiveKit reconnects automatically; agent is silent until reconnected |
| LLM API error | Agent says "I'm having trouble thinking right now, please try again" |
| Rime TTS unreachable | Session logs `tts.fallback.activated`; no audio fallback is implemented — agent stays silent |
| Tool call throws | LLM generates a natural error response: "I couldn't find results for that route" |
| Double barge-in < 500ms | Both interrupts handled; generation counter increments twice; only latest query executes |

---

## Evidence

See [`RIME_EVIDENCE.md`](./RIME_EVIDENCE.md) for the hard voice engineering claim, acceptance test, procedure, and quantitative results.

---

## License

MIT
