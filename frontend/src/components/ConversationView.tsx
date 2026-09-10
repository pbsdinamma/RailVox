"use client";

import { useEffect, useRef } from "react";

interface Transcript {
  role: "user" | "assistant";
  text: string;
  timestamp: number;
}

interface ConversationViewProps {
  transcripts: Transcript[];
}

/**
 * ConversationView — Scrollable conversation transcript.
 *
 * Renders user and assistant speech bubbles with auto-scroll.
 */
export default function ConversationView({ transcripts }: ConversationViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcripts]);

  if (transcripts.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center text-[var(--text-muted)]">
          <p className="text-lg mb-2">🎤 Ready to listen</p>
          <p className="text-sm">
            Try saying: &ldquo;Find trains from Kharagpur to Kolkata tomorrow&rdquo;
          </p>
        </div>
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="space-y-3 max-w-2xl mx-auto">
      {transcripts.map((t, i) => (
        <div
          key={i}
          className={`flex ${
            t.role === "user" ? "justify-end" : "justify-start"
          } animate-fade-in-up`}
        >
          <div
            className={`px-4 py-2.5 ${
              t.role === "user" ? "bubble-user" : "bubble-assistant"
            }`}
          >
            {/* Role label */}
            <p
              className={`text-[10px] uppercase tracking-wider mb-1 ${
                t.role === "user"
                  ? "text-indigo-200/60"
                  : "text-[var(--text-muted)]"
              }`}
            >
              {t.role === "user" ? "You" : "RailVox"}
            </p>
            {/* Message text */}
            <p
              className={`text-sm leading-relaxed ${
                t.role === "user" ? "text-white" : "text-[var(--text-primary)]"
              }`}
            >
              {t.text}
            </p>
            {/* Timestamp */}
            <p
              className={`text-[9px] mt-1 ${
                t.role === "user"
                  ? "text-indigo-200/40"
                  : "text-[var(--text-muted)]"
              }`}
            >
              {new Date(t.timestamp).toLocaleTimeString()}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
