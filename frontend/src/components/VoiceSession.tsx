"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useVoiceAssistant,
  BarVisualizer,
  useDataChannel,
} from "@livekit/components-react";
import StatusIndicator from "./StatusIndicator";
import ConversationView from "./ConversationView";
import MetricsPanel from "./MetricsPanel";

/**
 * Token fetcher — calls our Next.js API route to get a LiveKit JWT.
 */
async function fetchToken(): Promise<{ token: string; url: string }> {
  const resp = await fetch("/api/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      room_name: `railvox-${Date.now()}`,
      participant_name: "user",
    }),
  });

  if (!resp.ok) {
    throw new Error(`Token fetch failed: ${resp.statusText}`);
  }

  return resp.json();
}

interface VoiceSessionProps {
  onDisconnect: () => void;
}

/**
 * VoiceSession — The main voice interaction view.
 *
 * Manages LiveKit room connection, renders conversation transcript,
 * status indicator, and optional debug metrics panel.
 */
export default function VoiceSession({ onDisconnect }: VoiceSessionProps) {
  const [connectionDetails, setConnectionDetails] = useState<{
    token: string;
    url: string;
  } | null>(null);
  const [isConnecting, setIsConnecting] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch token on mount
  useEffect(() => {
    fetchToken()
      .then((details) => {
        setConnectionDetails(details);
        setIsConnecting(false);
      })
      .catch((err) => {
        setError(err.message);
        setIsConnecting(false);
      });
  }, []);

  if (error) {
    return (
      <div className="gradient-bg min-h-screen flex items-center justify-center">
        <div className="glass-card p-8 text-center max-w-md">
          <div className="text-4xl mb-4">⚠️</div>
          <h2 className="text-xl font-semibold mb-2">Connection Error</h2>
          <p className="text-[var(--text-secondary)] mb-4">{error}</p>
          <p className="text-xs text-[var(--text-muted)] mb-6">
            Make sure the agent server is running and .env.local is configured.
          </p>
          <button
            onClick={onDisconnect}
            className="px-4 py-2 rounded-lg bg-[var(--bg-card)] border border-[var(--border)] hover:border-[var(--accent)] transition-colors cursor-pointer"
          >
            Back
          </button>
        </div>
      </div>
    );
  }

  if (isConnecting || !connectionDetails) {
    return (
      <div className="gradient-bg min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="flex items-center justify-center gap-2 mb-4">
            <div className="thinking-dot w-2 h-2 bg-indigo-400 rounded-full" />
            <div className="thinking-dot w-2 h-2 bg-indigo-400 rounded-full" />
            <div className="thinking-dot w-2 h-2 bg-indigo-400 rounded-full" />
          </div>
          <p className="text-[var(--text-secondary)]">Connecting to RailVox...</p>
        </div>
      </div>
    );
  }

  return (
    <LiveKitRoom
      serverUrl={connectionDetails.url}
      token={connectionDetails.token}
      connect={true}
      audio={true}
      video={false}
      onDisconnected={onDisconnect}
      className="gradient-bg min-h-screen"
    >
      <RoomAudioRenderer />
      <VoiceSessionInner onDisconnect={onDisconnect} />
    </LiveKitRoom>
  );
}

/**
 * Inner component — must be inside LiveKitRoom to use hooks.
 */
function VoiceSessionInner({ onDisconnect }: { onDisconnect: () => void }) {
  const { state, audioTrack, agentTranscriptions } = useVoiceAssistant();
  const [showMetrics, setShowMetrics] = useState(false);
  const [agentState, setAgentState] = useState("idle");
  const [metrics, setMetrics] = useState<Record<string, unknown>>({});
  const [transcripts, setTranscripts] = useState<
    Array<{ id: string; role: "user" | "assistant"; text: string; timestamp: number }>
  >([]);

  // Handle data channel messages from the agent
  const onDataReceived = useCallback(
    (payload: Uint8Array) => {
      try {
        const message = JSON.parse(new TextDecoder().decode(payload));

        if (message.type === "state_update") {
          setAgentState(message.state);
        } else if (message.type === "metrics_update") {
          setMetrics(message.metrics);
        }
      } catch {
        // Ignore non-JSON data
      }
    },
    []
  );

  useDataChannel({ onMessage: onDataReceived });

  // Track transcriptions
  useEffect(() => {
    if (agentTranscriptions && agentTranscriptions.length > 0) {
      const latest = agentTranscriptions[agentTranscriptions.length - 1];
      if (latest && latest.text) {
        setTranscripts((prev) => {
          const existingIdx = prev.findIndex((t) => t.id === latest.id);
          
          if (existingIdx !== -1) {
            const lastTranscript = prev[existingIdx];
            if (lastTranscript.text === latest.text) {
              return prev;
            }
            const updated = [...prev];
            updated[existingIdx] = { ...lastTranscript, text: latest.text };
            return updated;
          }

          return [
            ...prev,
            {
              id: latest.id,
              role: "assistant",
              text: latest.text,
              timestamp: Date.now(),
            },
          ];
        });
      }
    }
  }, [agentTranscriptions]);

  // Toggle metrics with 'D' key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "d" || e.key === "D") {
        setShowMetrics((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Map LiveKit agent state to our display state
  const displayState = useMemo(() => {
    if (agentState !== "idle") return agentState;
    // Fall back to LiveKit's state string
    if (state === "speaking") return "speaking";
    if (state === "thinking") return "thinking";
    if (state === "listening") return "listening";
    return "idle";
  }, [state, agentState]);

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="flex items-center justify-between p-4 border-b border-[var(--border)]">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🚂</span>
          <h1 className="text-lg font-semibold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
            RailVox
          </h1>
          <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--bg-card)] border border-[var(--border)] text-[var(--text-muted)]">
            Rime Coda
          </span>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowMetrics((p) => !p)}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-colors cursor-pointer ${
              showMetrics
                ? "bg-indigo-600/20 border-indigo-500 text-indigo-300"
                : "bg-transparent border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)]"
            }`}
            title="Toggle debug metrics (D)"
          >
            📊 Debug
          </button>
          <button
            onClick={onDisconnect}
            className="text-xs px-3 py-1.5 rounded-lg bg-red-600/10 border border-red-500/30 text-red-400 hover:bg-red-600/20 transition-colors cursor-pointer"
          >
            Disconnect
          </button>
        </div>
      </header>

      {/* Main content */}
      <div className="flex-1 flex flex-col relative">
        {/* Conversation transcript */}
        <div className="flex-1 overflow-y-auto p-4">
          <ConversationView transcripts={transcripts} />
        </div>

        {/* Center status indicator */}
        <div className="flex flex-col items-center pb-8 pt-4">
          <StatusIndicator state={displayState} />

          {/* Audio visualizer */}
          {audioTrack && (
            <div className="mt-4 h-12 w-48">
              <BarVisualizer
                state={state}
                barCount={5}
                trackRef={audioTrack}
                className="h-full"
                options={{ minHeight: 4 }}
              />
            </div>
          )}

          {/* State label */}
          <p className="mt-3 text-xs text-[var(--text-muted)] uppercase tracking-widest">
            {displayState}
          </p>
        </div>

        {/* Metrics overlay */}
        {showMetrics && (
          <div className="absolute top-2 right-2 z-50">
            <MetricsPanel
              metrics={metrics}
              agentState={displayState}
              onClose={() => setShowMetrics(false)}
            />
          </div>
        )}
      </div>
    </div>
  );
}
