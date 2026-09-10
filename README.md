# RailVox 🚂🎤

Voice-native Indian railway search assistant with mid-flight correction and stale-result fencing.

Built for the DataForge × Pathway × Rime Hackathon Challenge.

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- LiveKit Cloud account (or local LiveKit server)
- API keys: Rime, Deepgram, OpenAI

### Setup

cd C:\PBS\RIME\agent
pip install -r requirements.txt
python agent.py dev

cd C:\PBS\RIME\frontend
npm install
npm run dev


1. **Clone the repo:**
   ```bash
   git clone <repo-url>
   cd railvox
   ```

2. **Configure environment:**
   ```bash
   cp agent/.env.example agent/.env
   # Edit agent/.env with your API keys
   ```

3. **Install agent dependencies:**
   ```bash
   cd agent
   pip install -r requirements.txt
   ```

4. **Install frontend dependencies:**
   ```bash
   cd frontend
   npm install
   ```

5. **Start the agent:**
   ```bash
   cd agent
   python agent.py dev
   ```

6. **Start the frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

7. **Open** http://localhost:3000

## Architecture

```
Mic → LiveKit WebRTC → Deepgram Nova-2 STT (streaming)
    → GPT-4o (streaming + tool-calling)
    → Rime Coda TTS (WebSocket streaming)
    → LiveKit WebRTC → Speaker
```

### Cancellation Architecture

Every request is tagged with a monotonically increasing **generation counter**. When the user interrupts:

1. Generation is incremented.
2. Active tool tasks are cancelled via `asyncio.Task.cancel()`.
3. Rime receives `{"operation": "clear"}` to stop synthesis.
4. Three fencing checkpoints block stale results:
   - **Fence 1:** Tool result → checks generation before entering LLM context.
   - **Fence 2:** LLM response → checks generation before committing.
   - **Fence 3:** TTS request → checks generation before synthesizing.

## Third-Party Services

| Service | Purpose | Model/Config |
|---|---|---|
| **Rime** | TTS (primary, sole default) | Coda, celeste, en, WebSocket |
| **Deepgram** | STT | Nova-2, en, streaming |
| **OpenAI** | LLM | GPT-4o, streaming, tool-calling |
| **LiveKit** | Transport + orchestration | Cloud, WebRTC |

## Rime Configuration

| Parameter | Value |
|---|---|
| **Model ID** | `coda` |
| **Speaker/Voice** | `celeste` |
| **Language** | `en` |
| **Endpoint** | `wss://users-ws.rime.ai/ws3` (via `livekit-plugins-rime`) |
| **Audio Format** | PCM |
| **Sample Rate** | 16000 Hz |
| **Transport** | WebSocket (streaming, `use_websocket=True`) |

## Known Limitations

1. Static timetable data (~45 trains) — not connected to live IRCTC.
2. English only — no Hindi or other Indian language support in v1.
3. No actual booking — search and information only.
4. Tool latency is simulated (`asyncio.sleep(3-8s)`) — reflects realistic IRCTC timing but is not a real API call.
5. Echo cancellation depends on browser WebRTC AEC — performance varies by device/browser.

## Failure Behavior

| Failure | Behavior |
|---|---|
| STT down | Agent speaks "Having trouble hearing you" via TTS, retries |
| LLM down | Agent speaks error, retries with backoff |
| Rime down | **Fallback to Deepgram Aura TTS** (disclosed, non-default) |
| Tool error | LLM generates natural error response |

### Fallback Disclosure

Rime Coda is the **default and primary** TTS provider in all flows. If Rime is unreachable, the system falls back to Deepgram Aura TTS. This fallback is:
- Logged as `tts.fallback.activated` in the event log
- Displayed in the UI with a warning indicator
- **Not used in the judged demo flow**

## Evidence

See [RIME_EVIDENCE.md](./RIME_EVIDENCE.md) for:
- Hard voice engineering claims
- Acceptance test definitions
- Quantitative results
- Reproducible test commands

## Project Structure

```
railvox/
├── agent/              # Python LiveKit Agent (backend)
│   ├── agent.py        # Entrypoint: AgentSession setup
│   ├── orchestrator.py # State machine, generation fencing
│   ├── tools.py        # @function_tool definitions
│   ├── railway_data.py # Timetable search logic
│   ├── events.py       # Event logging + metrics
│   ├── prompts.py      # LLM system prompt
│   └── data/           # Static timetable JSON
├── frontend/           # Next.js frontend
│   └── src/            # React components + hooks
├── scripts/            # Analysis + evidence generation
└── docs/               # Architecture docs
```

## License

MIT
