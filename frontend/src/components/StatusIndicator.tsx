"use client";

/**
 * StatusIndicator — Visual representation of the agent's current state.
 *
 * States:
 * - idle: Dim microphone icon
 * - listening: Pulsing blue microphone
 * - thinking: Animated dots
 * - tool_running: Spinner with search icon
 * - speaking: Green waveform bars
 * - interrupted: Red flash
 */
export default function StatusIndicator({ state }: { state: string }) {
  return (
    <div className="relative flex items-center justify-center w-24 h-24">
      {/* Background glow ring */}
      {state === "listening" && (
        <>
          <div className="absolute inset-0 rounded-full bg-indigo-500/20 pulse-ring" />
          <div
            className="absolute inset-0 rounded-full bg-indigo-500/10 pulse-ring"
            style={{ animationDelay: "0.5s" }}
          />
        </>
      )}

      {state === "speaking" && (
        <div className="absolute inset-0 rounded-full bg-emerald-500/10 pulse-ring" />
      )}

      {state === "interrupted" && (
        <div className="absolute inset-0 rounded-full bg-red-500/30 animate-ping" />
      )}

      {/* Main circle */}
      <div
        className={`relative w-20 h-20 rounded-full flex items-center justify-center transition-all duration-300 ${
          state === "idle"
            ? "bg-[var(--bg-card)] border border-[var(--border)]"
            : state === "listening"
            ? "bg-indigo-600/20 border-2 border-indigo-500 shadow-[0_0_30px_rgba(99,102,241,0.3)]"
            : state === "thinking" || state === "tool_running"
            ? "bg-amber-600/10 border-2 border-amber-500/50"
            : state === "speaking"
            ? "bg-emerald-600/10 border-2 border-emerald-500/50 shadow-[0_0_20px_rgba(34,197,94,0.2)]"
            : state === "interrupted"
            ? "bg-red-600/10 border-2 border-red-500"
            : "bg-[var(--bg-card)] border border-[var(--border)]"
        }`}
      >
        {/* Icon / Animation */}
        {state === "idle" && <MicIcon className="w-8 h-8 text-[var(--text-muted)]" />}

        {state === "listening" && (
          <MicIcon className="w-8 h-8 text-indigo-400 animate-pulse" />
        )}

        {(state === "thinking" || state === "tool_running") && (
          <div className="flex items-center gap-1.5">
            <div className="thinking-dot w-2.5 h-2.5 bg-amber-400 rounded-full" />
            <div className="thinking-dot w-2.5 h-2.5 bg-amber-400 rounded-full" />
            <div className="thinking-dot w-2.5 h-2.5 bg-amber-400 rounded-full" />
          </div>
        )}

        {state === "speaking" && (
          <div className="flex items-end gap-1 h-6">
            {[1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className="waveform-bar w-1.5 bg-emerald-400 rounded-full"
                style={{ animationDelay: `${i * 0.1}s` }}
              />
            ))}
          </div>
        )}

        {state === "interrupted" && (
          <span className="text-2xl">⚡</span>
        )}
      </div>
    </div>
  );
}

function MicIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
      />
    </svg>
  );
}
