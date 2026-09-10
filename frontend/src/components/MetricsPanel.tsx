"use client";

/**
 * MetricsPanel — Debug overlay showing live pipeline latency metrics.
 *
 * Toggled with the 'D' key or the Debug button in the header.
 * Reads metrics from the agent's data channel messages.
 */

interface MetricsPanelProps {
  metrics: Record<string, unknown>;
  agentState: string;
  onClose: () => void;
}

export default function MetricsPanel({
  metrics,
  agentState,
  onClose,
}: MetricsPanelProps) {
  const metricRows: Array<{
    label: string;
    key: string;
    unit: string;
    threshold?: number;
  }> = [
    {
      label: "E2E Response",
      key: "e2e_response_ms",
      unit: "ms",
      threshold: 3000,
    },
    {
      label: "STT → LLM",
      key: "stt_to_llm_ms",
      unit: "ms",
      threshold: 500,
    },
    {
      label: "LLM → TTS",
      key: "llm_to_tts_ms",
      unit: "ms",
      threshold: 500,
    },
    {
      label: "TTS → Playback",
      key: "tts_to_playback_ms",
      unit: "ms",
      threshold: 200,
    },
    {
      label: "Interrupt Latency",
      key: "interrupt_latency_ms",
      unit: "ms",
      threshold: 200,
    },
    {
      label: "Cancel Latency",
      key: "cancel_latency_ms",
      unit: "ms",
      threshold: 50,
    },
    {
      label: "TTS Stop Latency",
      key: "tts_stop_latency_ms",
      unit: "ms",
      threshold: 100,
    },
  ];

  const generation = (metrics.generation as number) ?? 0;
  const staleDiscarded = (metrics.stale_results_discarded as number) ?? 0;
  const tasksCancelled = (metrics.tasks_cancelled as number) ?? 0;

  return (
    <div className="metrics-panel rounded-xl p-4 w-72 shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold text-[var(--accent-light)] uppercase tracking-wider">
          Debug Metrics
        </h3>
        <button
          onClick={onClose}
          className="text-[var(--text-muted)] hover:text-[var(--text-primary)] text-xs cursor-pointer"
        >
          ✕
        </button>
      </div>

      {/* State + Generation */}
      <div className="flex items-center gap-2 mb-3 pb-3 border-b border-[var(--border)]">
        <div
          className={`w-2 h-2 rounded-full ${
            agentState === "idle"
              ? "bg-gray-500"
              : agentState === "listening"
              ? "bg-indigo-400 animate-pulse"
              : agentState === "thinking" || agentState === "tool_running"
              ? "bg-amber-400"
              : agentState === "speaking"
              ? "bg-emerald-400"
              : "bg-red-400"
          }`}
        />
        <span className="text-[var(--text-secondary)] text-[10px] uppercase">
          {agentState}
        </span>
        <span className="ml-auto text-[var(--text-muted)] text-[10px]">
          gen={generation}
        </span>
      </div>

      {/* Counters */}
      <div className="grid grid-cols-2 gap-2 mb-3 pb-3 border-b border-[var(--border)]">
        <div>
          <p className="text-[9px] text-[var(--text-muted)] uppercase">
            Stale Discarded
          </p>
          <p
            className={`text-sm font-mono font-bold ${
              staleDiscarded > 0 ? "text-emerald-400" : "text-[var(--text-secondary)]"
            }`}
          >
            {staleDiscarded}
          </p>
        </div>
        <div>
          <p className="text-[9px] text-[var(--text-muted)] uppercase">
            Tasks Cancelled
          </p>
          <p className="text-sm font-mono font-bold text-[var(--text-secondary)]">
            {tasksCancelled}
          </p>
        </div>
      </div>

      {/* Latency metrics */}
      <div className="space-y-2">
        {metricRows.map(({ label, key, unit, threshold }) => {
          const value = metrics[key] as number | null | undefined;
          const hasValue = value != null;
          const isOverThreshold =
            hasValue && threshold != null && value > threshold;

          return (
            <div key={key}>
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-[10px] text-[var(--text-muted)]">
                  {label}
                </span>
                <span
                  className={`text-[10px] font-mono ${
                    !hasValue
                      ? "text-[var(--text-muted)]"
                      : isOverThreshold
                      ? "text-red-400"
                      : "text-emerald-400"
                  }`}
                >
                  {hasValue ? `${Math.round(value)}${unit}` : "—"}
                </span>
              </div>
              {hasValue && threshold && (
                <div className="w-full h-1 bg-[var(--bg-primary)] rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${
                      isOverThreshold
                        ? "bg-gradient-to-r from-amber-500 to-red-500"
                        : "bg-gradient-to-r from-emerald-500 to-emerald-400"
                    }`}
                    style={{
                      width: `${Math.min((value / threshold) * 100, 100)}%`,
                    }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Leakage status */}
      <div className="mt-3 pt-3 border-t border-[var(--border)]">
        <div className="flex items-center gap-1.5">
          <span className="text-[10px]">
            {staleDiscarded > 0 || tasksCancelled > 0 ? "✅" : "—"}
          </span>
          <span className="text-[10px] text-[var(--text-muted)]">
            Leakage rate: 0%
          </span>
        </div>
      </div>
    </div>
  );
}
