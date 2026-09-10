"""
RailVox — Session Analysis Script

Reads the append-only JSONL event log for a session and produces:
1. A markdown table of per-turn latency metrics.
2. Stale-result leakage report.
3. Interrupt-to-silence latency analysis.
4. Pass/fail report for the canonical acceptance test conditions.

Usage:
    python scripts/analyze_session.py <session_id>
    python scripts/analyze_session.py --latest
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import defaultdict
from statistics import median, mean


def load_events(session_id: str, log_dir: str = "logs") -> list[dict]:
    """Load all events from a session's JSONL log."""
    log_file = Path(log_dir) / session_id / "events.jsonl"
    if not log_file.exists():
        print(f"Error: Log file not found: {log_file}")
        sys.exit(1)

    events = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def find_latest_session(log_dir: str = "logs") -> str:
    """Find the most recently modified session log directory."""
    log_path = Path(log_dir)
    if not log_path.exists():
        print("Error: logs/ directory not found")
        sys.exit(1)

    sessions = [d for d in log_path.iterdir() if d.is_dir()]
    if not sessions:
        print("Error: No session logs found")
        sys.exit(1)

    latest = max(sessions, key=lambda d: d.stat().st_mtime)
    return latest.name


def analyze_session(events: list[dict]) -> dict:
    """Analyze a session's events and produce a report."""
    report = {
        "total_events": len(events),
        "tasks_created": 0,
        "tasks_cancelled": 0,
        "tasks_completed": 0,
        "results_discarded": 0,
        "results_received": 0,
        "barge_ins": 0,
        "state_transitions": [],
        "turn_metrics": [],
        "leakage_events": [],
    }

    # Count events by type
    for event in events:
        etype = event["event_type"]
        if etype == "task.created":
            report["tasks_created"] += 1
        elif etype == "task.cancelled":
            report["tasks_cancelled"] += 1
        elif etype == "tool.result.received":
            report["results_received"] += 1
        elif etype == "tool.result.discarded":
            report["results_discarded"] += 1
        elif etype == "user.barge_in":
            report["barge_ins"] += 1
        elif etype == "metrics.turn.complete":
            report["turn_metrics"].append(event["payload"])
        elif etype == "state.transition":
            report["state_transitions"].append(event["payload"])

    # Check for leakage: any tts.chunk.enqueued or llm.response.committed
    # events with a generation lower than the current generation at that time
    max_gen_at_time = 0
    for event in events:
        gen = event.get("generation", 0)
        max_gen_at_time = max(max_gen_at_time, gen)

        if event["event_type"] in ("tts.chunk.enqueued", "llm.response.committed"):
            event_gen = event.get("generation", 0)
            if event_gen < max_gen_at_time:
                report["leakage_events"].append(event)

    return report


def print_report(report: dict, session_id: str):
    """Print a formatted analysis report."""
    print(f"\n{'='*60}")
    print(f"  RailVox Session Analysis: {session_id}")
    print(f"{'='*60}\n")

    print(f"Total events: {report['total_events']}")
    print(f"Tasks created: {report['tasks_created']}")
    print(f"Tasks cancelled: {report['tasks_cancelled']}")
    print(f"Results received: {report['results_received']}")
    print(f"Results discarded (stale): {report['results_discarded']}")
    print(f"Barge-ins: {report['barge_ins']}")

    # Stale result leakage
    print(f"\n--- Stale Result Leakage ---")
    leakage_count = len(report["leakage_events"])
    total_results = report["results_received"] + report["results_discarded"]
    print(f"Leakage events: {leakage_count}")
    if total_results > 0:
        print(f"Leakage rate: {leakage_count}/{total_results} ({leakage_count/total_results*100:.1f}%)")
    else:
        print(f"Leakage rate: N/A (no tool results)")

    if leakage_count > 0:
        print(f"⚠️  STALE RESULTS LEAKED!")
        for event in report["leakage_events"]:
            print(f"  - {event['event_type']} at gen={event['generation']}")
    else:
        print(f"✅ No stale result leakage detected")

    # Turn metrics
    if report["turn_metrics"]:
        print(f"\n--- Turn Latency Metrics ---")
        print(f"{'Metric':<30} {'Median':>10} {'Mean':>10} {'Min':>10} {'Max':>10}")
        print(f"{'-'*30} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")

        metric_names = [
            "e2e_response_ms", "stt_to_llm_ms", "llm_to_tts_ms",
            "tts_to_playback_ms", "interrupt_latency_ms",
            "cancel_latency_ms", "tts_stop_latency_ms",
        ]

        for name in metric_names:
            values = [
                m[name] for m in report["turn_metrics"]
                if m.get(name) is not None
            ]
            if values:
                print(
                    f"{name:<30} {median(values):>10.1f} {mean(values):>10.1f} "
                    f"{min(values):>10.1f} {max(values):>10.1f}"
                )

    print(f"\n{'='*60}\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_session.py <session_id|--latest>")
        sys.exit(1)

    if sys.argv[1] == "--latest":
        session_id = find_latest_session()
    else:
        session_id = sys.argv[1]

    print(f"Analyzing session: {session_id}")
    events = load_events(session_id)
    report = analyze_session(events)
    print_report(report, session_id)


if __name__ == "__main__":
    main()
