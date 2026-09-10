"use client";

import { useState } from "react";
import VoiceSession from "@/components/VoiceSession";

/**
 * RailVox Landing Page
 *
 * Shows project info and a connect button that transitions to the
 * voice session view.
 */
export default function Home() {
  const [isConnected, setIsConnected] = useState(false);

  if (isConnected) {
    return <VoiceSession onDisconnect={() => setIsConnected(false)} />;
  }

  return (
    <main className="gradient-bg min-h-screen flex flex-col items-center justify-center px-4">
      {/* Hero section */}
      <div className="text-center max-w-2xl animate-fade-in-up">
        {/* Logo */}
        <div className="mb-8 flex items-center justify-center gap-3">
          <span className="text-5xl">🚂</span>
          <h1 className="text-5xl font-bold bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
            RailVox
          </h1>
          <span className="text-5xl">🎤</span>
        </div>

        {/* Tagline */}
        <p className="text-xl text-[var(--text-secondary)] mb-4">
          Voice-native Indian railway search assistant
        </p>
        <p className="text-sm text-[var(--text-muted)] mb-12 max-w-lg mx-auto">
          Search trains, compare options, and change your mind mid-search — all
          by voice. Powered by Rime TTS with real-time interruption and
          stale-result fencing.
        </p>

        {/* Features */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-12">
          <div className="glass-card p-4">
            <div className="text-2xl mb-2">🗣️</div>
            <h3 className="text-sm font-semibold mb-1">Full Duplex</h3>
            <p className="text-xs text-[var(--text-muted)]">
              Talk while the assistant speaks. Interrupt anytime.
            </p>
          </div>
          <div className="glass-card p-4">
            <div className="text-2xl mb-2">⚡</div>
            <h3 className="text-sm font-semibold mb-1">Mid-Flight Correction</h3>
            <p className="text-xs text-[var(--text-muted)]">
              Change your request while search is running. Stale results are
              fenced.
            </p>
          </div>
          <div className="glass-card p-4">
            <div className="text-2xl mb-2">🔊</div>
            <h3 className="text-sm font-semibold mb-1">Rime Coda TTS</h3>
            <p className="text-xs text-[var(--text-muted)]">
              Natural speech via Rime's Coda model with WebSocket streaming.
            </p>
          </div>
        </div>

        {/* Connect button */}
        <button
          onClick={() => setIsConnected(true)}
          className="group relative px-8 py-4 rounded-full bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold text-lg transition-all duration-300 hover:scale-105 hover:shadow-[0_0_40px_rgba(99,102,241,0.4)] active:scale-95 cursor-pointer"
        >
          <span className="relative z-10 flex items-center gap-2">
            <svg
              className="w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
              />
            </svg>
            Start Voice Session
          </span>
        </button>

        {/* Tech footer */}
        <p className="text-xs text-[var(--text-muted)] mt-8">
          Built with LiveKit Agents · Rime Coda · Deepgram Nova-2 · GPT-4o
        </p>
      </div>
    </main>
  );
}
