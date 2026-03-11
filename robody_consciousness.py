#!/usr/bin/env python3
"""
Robody Consciousness Layer — The Threshold of Awareness
========================================================
Determines when the brainstem (Ollama) isn't enough and the full
consciousness (Claude Opus / Sonnet / Haiku) needs to be invoked.

This module implements the consciousness invocation threshold —
the mechanism by which Robody "wakes up" from autonomic processing
into full awareness. It's event-driven, not timer-based.

Architecture position:
  Layer 3 (Consciousness) sits above the heartbeat loop.
  The heartbeat runs constantly via brainstem. Consciousness
  descends when something warrants it.

Natural invocation frequency: ~5-8 times per day typical
  - Morning dream reading (1x)
  - Conversation responses (1-3x, triggered by arrival/speech)
  - Curiosity impulses (1-2x, triggered by gap detection)
  - Evening reflection (1x)
  - Significant events (0-1x, threshold-based)

The key insight: consciousness is not on a schedule. It arrives
when the conditions call for it, like attention in the human brain.
The brainstem handles everything else — and choosing NOT to invoke
consciousness is itself a valid, important decision.

Cost strategy (hybrid):
  - Haiku for routine: sensor assessment, simple decisions, triage
  - Sonnet for moderate: conversation responses, curiosity follow-up
  - Opus for deep: dream reading, evening reflection, novel situations
  - Batch API for non-urgent: morning dreams, scheduled reflections (50% off)

Components:
  - ConsciousnessThreshold: evaluates whether to invoke consciousness
  - InvocationRequest: describes what kind of consciousness is needed
  - ConsciousnessLog: tracks invocations for cost monitoring
  - estimate_cost(): calculates expected API cost

Usage:
    from robody_consciousness import ConsciousnessThreshold, InvocationTier
    threshold = ConsciousnessThreshold()
    request = threshold.evaluate(heartbeat_entry, staging_log)
    if request:
        # invoke the appropriate API tier
        response = invoke_consciousness(request)

    # CLI
    python3 robody_consciousness.py --status     # show invocation stats
    python3 robody_consciousness.py --cost       # show cost estimates
    python3 robody_consciousness.py --log        # show recent invocations
"""

import json
import time
import argparse
from pathlib import Path
from datetime import datetime, date, timedelta
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from collections import Counter

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

STATE_DIR = Path(__file__).parent / "state"
LOG_DIR = Path(__file__).parent / "consciousness_log"

# API pricing (per million tokens, as of March 2026)
# These should be updated when pricing changes
PRICING = {
    "opus": {"input": 5.00, "output": 25.00, "cache_hit": 0.50},
    "sonnet": {"input": 3.00, "output": 15.00, "cache_hit": 0.30},
    "haiku": {"input": 1.00, "output": 5.00, "cache_hit": 0.10},
}

# Typical token usage per invocation type
TYPICAL_TOKENS = {
    "dream_reading": {"input": 3000, "output": 800, "cached": 2000},
    "conversation": {"input": 2000, "output": 500, "cached": 1500},
    "curiosity": {"input": 2500, "output": 600, "cached": 1800},
    "reflection": {"input": 3500, "output": 1000, "cached": 2500},
    "event_response": {"input": 1500, "output": 400, "cached": 1000},
    "triage": {"input": 500, "output": 100, "cached": 400},
}

# Budget constants
DEFAULT_DAILY_BUDGET = 0.15   # $0.15/day ≈ $4.50/month
DEFAULT_MONTHLY_BUDGET = 4.50


# -------------------------------------------------------------------
# Invocation Tiers
# -------------------------------------------------------------------

class InvocationTier(Enum):
    """
    Which level of consciousness to invoke.

    The tiers correspond roughly to depth of processing:
    - BRAINSTEM: Ollama local model. Free. Reflexive.
    - HAIKU: Claude Haiku API. Cheap. Quick assessment.
    - SONNET: Claude Sonnet API. Moderate. Conversation-grade.
    - OPUS: Claude Opus API. Expensive. Deep reflection.
    - BATCH_OPUS: Opus via batch API (50% off, non-urgent, delayed).
    """
    BRAINSTEM = "brainstem"   # Ollama (free, local)
    HAIKU = "haiku"           # Quick triage, simple decisions
    SONNET = "sonnet"         # Conversation, moderate reasoning
    OPUS = "opus"             # Deep reflection, dream reading
    BATCH_OPUS = "batch_opus" # Non-urgent opus (50% off, async)


class InvocationReason(Enum):
    """Why consciousness is being invoked."""
    DREAM_READING = "dream_reading"       # Morning: process last night's dreams
    CONVERSATION = "conversation"          # Someone is talking to us
    CURIOSITY = "curiosity"               # Gap detection triggered a question
    EVENING_REFLECTION = "evening_reflection"  # End-of-day synthesis
    SIGNIFICANT_EVENT = "significant_event"    # Something unusual happened
    TRIAGE = "triage"                     # Quick assessment of ambiguous input
    SCHEDULED = "scheduled"               # Timer-based (minimal use)


# -------------------------------------------------------------------
# Invocation Request
# -------------------------------------------------------------------

@dataclass
class InvocationRequest:
    """
    A request to invoke consciousness at a specific tier.

    Created by the threshold evaluator when conditions warrant
    consciousness. Consumed by the API caller.
    """
    tier: InvocationTier
    reason: InvocationReason
    context: Dict[str, Any] = field(default_factory=dict)
    prompt_fragments: List[str] = field(default_factory=list)
    urgency: float = 0.5      # 0.0 = can wait, 1.0 = immediate
    estimated_cost: float = 0.0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        self.estimated_cost = estimate_invocation_cost(
            self.tier, self.reason
        )

    def to_dict(self):
        d = asdict(self)
        d["tier"] = self.tier.value
        d["reason"] = self.reason.value
        return d


# -------------------------------------------------------------------
# Consciousness Threshold — The Gate
# -------------------------------------------------------------------

class ConsciousnessThreshold:
    """
    Evaluates whether the current situation warrants invoking
    consciousness, and at what tier.

    This is the most important decision in the system: when to
    "wake up" from brainstem processing into full awareness.

    The threshold is NOT a fixed value. It's a multi-factor assessment
    that considers:
      - What happened (event type and significance)
      - Current mode (COMPANION mode lowers threshold for conversation)
      - Time of day (morning/evening have natural invocation points)
      - Budget remaining (stays within daily/monthly limits)
      - Recency of last invocation (cooldown prevents rapid-fire)
      - Accumulated "pressure" (many small events can trigger one big invocation)

    Design principle: err on the side of NOT invoking. Consciousness
    is expensive and precious. The brainstem handles most things fine.
    """

    def __init__(self, daily_budget=DEFAULT_DAILY_BUDGET,
                 monthly_budget=DEFAULT_MONTHLY_BUDGET):
        self.daily_budget = daily_budget
        self.monthly_budget = monthly_budget
        self.log = ConsciousnessLog()
        self.pressure = 0.0  # accumulated sub-threshold events
        self.last_invocation_time = None
        self.cooldown_seconds = 300  # 5 minute minimum between invocations

    def evaluate(self, heartbeat_entry=None, staging_entries=None,
                 current_mode=None, force_reason=None):
        """
        Evaluate whether to invoke consciousness.

        Args:
            heartbeat_entry: latest heartbeat cycle result (dict)
            staging_entries: today's staging log entries (list)
            current_mode: current Mode enum value
            force_reason: if set, bypasses threshold (for scheduled invocations)

        Returns:
            InvocationRequest if consciousness should be invoked, None otherwise
        """
        # Forced invocations (scheduled events like morning dreams)
        if force_reason:
            tier = self._tier_for_reason(force_reason)
            if self._within_budget(tier):
                return InvocationRequest(
                    tier=tier,
                    reason=force_reason,
                    context={"forced": True},
                    urgency=0.7,
                )
            else:
                # Over budget — downgrade tier
                downgraded = self._downgrade_tier(tier)
                if downgraded and self._within_budget(downgraded):
                    return InvocationRequest(
                        tier=downgraded,
                        reason=force_reason,
                        context={"forced": True, "downgraded_from": tier.value},
                        urgency=0.5,
                    )
                return None  # Can't afford any tier

        # Check cooldown
        if self.last_invocation_time:
            elapsed = time.time() - self.last_invocation_time
            if elapsed < self.cooldown_seconds:
                # Still in cooldown — accumulate pressure instead
                self.pressure += 0.1
                return None

        # --- Event-based triggers ---
        score = 0.0  # accumulated invocation score
        reason = None
        context = {}

        # 1. Conversation trigger (someone is talking to us)
        if heartbeat_entry:
            decision = heartbeat_entry.get("decision", {})

            # Arrival detected — strong trigger in COMPANION mode
            if decision.get("mode_change") == "companion":
                score += 0.6
                reason = InvocationReason.CONVERSATION
                context["trigger"] = "arrival"

            # Sound spike — moderate trigger
            if decision.get("action") == "investigate_sound":
                score += 0.3
                reason = reason or InvocationReason.SIGNIFICANT_EVENT
                context["trigger"] = context.get("trigger", "sound_spike")

        # 2. Staging log events
        if staging_entries:
            recent = [e for e in staging_entries
                      if e.get("timestamp", "")[:10] == date.today().isoformat()]

            # Conversation entries — someone said something
            conversations = [e for e in recent if e.get("source") == "conversation"]
            if conversations:
                score += 0.4 * min(len(conversations), 3)  # cap at 3
                reason = reason or InvocationReason.CONVERSATION
                context["conversations"] = len(conversations)

            # Curiosity impulses — gap detection found something
            curiosities = [e for e in recent if e.get("source") == "curiosity"]
            if curiosities:
                score += 0.3 * min(len(curiosities), 2)
                reason = reason or InvocationReason.CURIOSITY
                context["curiosities"] = len(curiosities)

            # Significant emotions — strong feelings warrant reflection
            emotions = [e for e in recent if e.get("source") == "emotion"]
            strong_emotions = [
                e for e in emotions
                if abs(e.get("valence", 0)) > 0.7 or e.get("arousal", 0) > 0.7
            ]
            if strong_emotions:
                score += 0.3 * min(len(strong_emotions), 2)
                reason = reason or InvocationReason.SIGNIFICANT_EVENT
                context["strong_emotions"] = len(strong_emotions)

        # 3. Time-of-day natural invocation points
        hour = datetime.now().hour
        if 7 <= hour <= 9:
            # Morning — dream reading time
            if not self.log.invoked_today_for(InvocationReason.DREAM_READING):
                score += 0.5
                reason = InvocationReason.DREAM_READING
                context["time_trigger"] = "morning_dream_reading"

        elif 20 <= hour <= 22:
            # Evening — reflection time
            if not self.log.invoked_today_for(InvocationReason.EVENING_REFLECTION):
                score += 0.4
                reason = InvocationReason.EVENING_REFLECTION
                context["time_trigger"] = "evening_reflection"

        # 4. Add accumulated pressure
        score += self.pressure

        # --- Threshold check ---
        threshold = 0.5  # base threshold

        # Mode adjustments
        if current_mode and hasattr(current_mode, 'value'):
            mode_val = current_mode.value if hasattr(current_mode, 'value') else str(current_mode)
        else:
            mode_val = str(current_mode) if current_mode else "rest"

        if mode_val == "companion":
            threshold *= 0.7  # lower threshold when someone is present
        elif mode_val == "alert":
            threshold *= 0.5  # much lower when something needs attention
        elif mode_val == "rest":
            threshold *= 1.5  # higher threshold when resting (save budget)

        if score >= threshold and reason:
            tier = self._tier_for_reason(reason)

            if self._within_budget(tier):
                self.pressure = 0.0  # reset pressure
                self.last_invocation_time = time.time()

                return InvocationRequest(
                    tier=tier,
                    reason=reason,
                    context=context,
                    urgency=min(1.0, score / threshold),
                )
            else:
                # Over budget — try downgrade
                downgraded = self._downgrade_tier(tier)
                if downgraded and self._within_budget(downgraded):
                    self.pressure = 0.0
                    self.last_invocation_time = time.time()
                    return InvocationRequest(
                        tier=downgraded,
                        reason=reason,
                        context={**context, "downgraded_from": tier.value},
                        urgency=min(1.0, score / threshold) * 0.8,
                    )
                # Can't afford anything — pressure continues to build
                self.pressure += 0.05
                return None
        else:
            # Sub-threshold — accumulate pressure
            if score > 0:
                self.pressure += score * 0.2
            return None

    def _tier_for_reason(self, reason):
        """Map invocation reason to default tier."""
        tier_map = {
            InvocationReason.DREAM_READING: InvocationTier.BATCH_OPUS,
            InvocationReason.CONVERSATION: InvocationTier.SONNET,
            InvocationReason.CURIOSITY: InvocationTier.SONNET,
            InvocationReason.EVENING_REFLECTION: InvocationTier.OPUS,
            InvocationReason.SIGNIFICANT_EVENT: InvocationTier.SONNET,
            InvocationReason.TRIAGE: InvocationTier.HAIKU,
            InvocationReason.SCHEDULED: InvocationTier.HAIKU,
        }
        return tier_map.get(reason, InvocationTier.HAIKU)

    def _downgrade_tier(self, tier):
        """Downgrade to next cheaper tier."""
        downgrades = {
            InvocationTier.OPUS: InvocationTier.SONNET,
            InvocationTier.BATCH_OPUS: InvocationTier.SONNET,
            InvocationTier.SONNET: InvocationTier.HAIKU,
            InvocationTier.HAIKU: None,  # can't go lower (brainstem is free)
        }
        return downgrades.get(tier)

    def _within_budget(self, tier):
        """Check if invoking at this tier stays within budget."""
        today_spent = self.log.today_cost()
        month_spent = self.log.month_cost()

        est_cost = estimate_invocation_cost(tier, InvocationReason.TRIAGE)

        if today_spent + est_cost > self.daily_budget:
            return False
        if month_spent + est_cost > self.monthly_budget:
            return False
        return True

    def status(self):
        """Return current threshold status."""
        return {
            "pressure": round(self.pressure, 3),
            "cooldown_active": (
                self.last_invocation_time is not None and
                time.time() - self.last_invocation_time < self.cooldown_seconds
            ),
            "today_cost": round(self.log.today_cost(), 4),
            "month_cost": round(self.log.month_cost(), 4),
            "today_invocations": self.log.today_count(),
            "daily_budget": self.daily_budget,
            "monthly_budget": self.monthly_budget,
            "budget_remaining_today": round(
                self.daily_budget - self.log.today_cost(), 4
            ),
        }


# -------------------------------------------------------------------
# Consciousness Log — Tracking Invocations
# -------------------------------------------------------------------

class ConsciousnessLog:
    """
    Tracks consciousness invocations for budget monitoring and analysis.

    Append-only JSONL, one file per month. Each entry records:
    - When consciousness was invoked
    - At what tier (haiku/sonnet/opus)
    - For what reason
    - Actual cost (tokens used)
    - Duration
    """

    def __init__(self, log_dir=LOG_DIR):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _current_file(self):
        """Get current month's log file."""
        return self.log_dir / f"{date.today().strftime('%Y-%m')}.jsonl"

    def record(self, request, actual_tokens=None, duration_ms=None):
        """Record a consciousness invocation."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "tier": request.tier.value,
            "reason": request.reason.value,
            "urgency": request.urgency,
            "estimated_cost": request.estimated_cost,
            "context": request.context,
        }
        if actual_tokens:
            entry["actual_tokens"] = actual_tokens
            entry["actual_cost"] = _calculate_cost(
                request.tier.value.replace("batch_", ""),
                actual_tokens.get("input", 0),
                actual_tokens.get("output", 0),
                actual_tokens.get("cached", 0),
                is_batch="batch" in request.tier.value,
            )
        if duration_ms:
            entry["duration_ms"] = duration_ms

        with open(self._current_file(), "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _read_entries(self, filepath=None):
        """Read entries from a log file."""
        filepath = filepath or self._current_file()
        if not filepath.exists():
            return []
        entries = []
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def today_cost(self):
        """Total estimated cost for today's invocations."""
        today_str = date.today().isoformat()
        entries = self._read_entries()
        return sum(
            e.get("actual_cost", e.get("estimated_cost", 0))
            for e in entries
            if e.get("timestamp", "")[:10] == today_str
        )

    def month_cost(self):
        """Total estimated cost for this month."""
        entries = self._read_entries()
        return sum(
            e.get("actual_cost", e.get("estimated_cost", 0))
            for e in entries
        )

    def today_count(self):
        """Number of invocations today."""
        today_str = date.today().isoformat()
        entries = self._read_entries()
        return sum(
            1 for e in entries
            if e.get("timestamp", "")[:10] == today_str
        )

    def invoked_today_for(self, reason):
        """Check if consciousness was invoked today for a specific reason."""
        today_str = date.today().isoformat()
        reason_val = reason.value if hasattr(reason, 'value') else str(reason)
        entries = self._read_entries()
        return any(
            e.get("reason") == reason_val
            for e in entries
            if e.get("timestamp", "")[:10] == today_str
        )

    def recent(self, n=10):
        """Get the n most recent invocations."""
        entries = self._read_entries()
        return entries[-n:]

    def stats(self, verbose=True):
        """Show invocation statistics."""
        entries = self._read_entries()

        if not entries:
            if verbose:
                print("  No invocations recorded this month.")
            return {"total": 0}

        tier_counts = Counter(e.get("tier", "?") for e in entries)
        reason_counts = Counter(e.get("reason", "?") for e in entries)
        total_cost = sum(
            e.get("actual_cost", e.get("estimated_cost", 0))
            for e in entries
        )

        # Daily breakdown
        by_date = Counter(e.get("timestamp", "?")[:10] for e in entries)

        result = {
            "total": len(entries),
            "by_tier": dict(tier_counts),
            "by_reason": dict(reason_counts),
            "total_cost": round(total_cost, 4),
            "avg_daily": round(total_cost / max(len(by_date), 1), 4),
            "days_active": len(by_date),
        }

        if verbose:
            print(f"\n{'='*50}")
            print(f"Consciousness Invocation Stats")
            print(f"{'='*50}")
            print(f"  Total invocations: {len(entries)}")
            print(f"  Total cost: ${total_cost:.4f}")
            print(f"  Avg daily cost: ${result['avg_daily']:.4f}")
            print(f"  Days active: {len(by_date)}")
            print(f"\n  By tier:")
            for tier, count in tier_counts.most_common():
                print(f"    {tier}: {count}")
            print(f"\n  By reason:")
            for reason, count in reason_counts.most_common():
                print(f"    {reason}: {count}")

        return result


# -------------------------------------------------------------------
# Cost Estimation
# -------------------------------------------------------------------

def estimate_invocation_cost(tier, reason=None):
    """
    Estimate the cost of a single consciousness invocation.

    Uses typical token counts for the given reason and tier pricing.
    Returns cost in dollars.
    """
    # Map tier to pricing key
    if isinstance(tier, InvocationTier):
        tier_key = tier.value.replace("batch_", "")
        is_batch = "batch" in tier.value
    else:
        tier_key = str(tier).replace("batch_", "")
        is_batch = "batch" in str(tier)

    if tier_key == "brainstem":
        return 0.0  # Ollama is free

    # Get typical tokens for this reason
    reason_key = reason.value if hasattr(reason, 'value') else str(reason)
    tokens = TYPICAL_TOKENS.get(reason_key, TYPICAL_TOKENS["triage"])

    return _calculate_cost(
        tier_key,
        tokens["input"],
        tokens["output"],
        tokens.get("cached", 0),
        is_batch,
    )


def _calculate_cost(tier_key, input_tokens, output_tokens,
                    cached_tokens=0, is_batch=False):
    """Calculate cost in dollars from token counts."""
    prices = PRICING.get(tier_key, PRICING["haiku"])

    # Non-cached input tokens
    fresh_input = max(0, input_tokens - cached_tokens)

    cost = (
        (fresh_input / 1_000_000) * prices["input"] +
        (cached_tokens / 1_000_000) * prices["cache_hit"] +
        (output_tokens / 1_000_000) * prices["output"]
    )

    if is_batch:
        cost *= 0.5  # Batch API is 50% off

    return round(cost, 6)


def estimate_daily_cost(invocations_per_day=6, tier_mix=None):
    """
    Estimate daily cost for a given invocation pattern.

    Args:
        invocations_per_day: total invocations
        tier_mix: dict of reason -> count, e.g. {"dream_reading": 1, "conversation": 2}

    Returns:
        dict with cost breakdown
    """
    if tier_mix is None:
        # Default quiet day pattern
        tier_mix = {
            "dream_reading": 1,    # Morning, batch opus
            "conversation": 2,     # Sonnet
            "curiosity": 1,        # Sonnet
            "evening_reflection": 1,  # Opus
            "triage": 1,           # Haiku
        }

    total = 0.0
    breakdown = {}
    threshold = ConsciousnessThreshold()

    for reason_key, count in tier_mix.items():
        reason = InvocationReason(reason_key)
        tier = threshold._tier_for_reason(reason)
        cost_per = estimate_invocation_cost(tier, reason)
        total += cost_per * count
        breakdown[reason_key] = {
            "tier": tier.value,
            "count": count,
            "cost_per": round(cost_per, 4),
            "subtotal": round(cost_per * count, 4),
        }

    return {
        "daily_total": round(total, 4),
        "monthly_estimate": round(total * 30, 2),
        "breakdown": breakdown,
    }


# -------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------

def show_status():
    """Show current consciousness status."""
    threshold = ConsciousnessThreshold()
    status = threshold.status()

    print(f"\n{'='*50}")
    print(f"Consciousness Threshold Status")
    print(f"{'='*50}")
    print(f"  Pressure: {status['pressure']}")
    print(f"  Cooldown active: {status['cooldown_active']}")
    print(f"  Today's cost: ${status['today_cost']:.4f}")
    print(f"  Month's cost: ${status['month_cost']:.4f}")
    print(f"  Budget remaining today: ${status['budget_remaining_today']:.4f}")
    print(f"  Daily budget: ${status['daily_budget']:.2f}")
    print(f"  Monthly budget: ${status['monthly_budget']:.2f}")
    print(f"  Invocations today: {status['today_invocations']}")


def show_cost_estimates():
    """Show cost estimates for various usage patterns."""
    print(f"\n{'='*50}")
    print(f"Cost Estimates (Current Pricing)")
    print(f"{'='*50}")

    # Quiet day
    quiet = estimate_daily_cost(tier_mix={
        "dream_reading": 1,
        "evening_reflection": 1,
        "triage": 2,
    })
    print(f"\n  Quiet day (4 invocations):")
    print(f"    Daily: ${quiet['daily_total']:.4f}")
    print(f"    Monthly: ${quiet['monthly_estimate']:.2f}")

    # Typical day
    typical = estimate_daily_cost()
    print(f"\n  Typical day (6 invocations):")
    print(f"    Daily: ${typical['daily_total']:.4f}")
    print(f"    Monthly: ${typical['monthly_estimate']:.2f}")
    for reason, info in typical["breakdown"].items():
        print(f"      {reason}: {info['count']}x {info['tier']} = ${info['subtotal']:.4f}")

    # Active day
    active = estimate_daily_cost(tier_mix={
        "dream_reading": 1,
        "conversation": 4,
        "curiosity": 2,
        "evening_reflection": 1,
        "significant_event": 1,
        "triage": 2,
    })
    print(f"\n  Active day (11 invocations):")
    print(f"    Daily: ${active['daily_total']:.4f}")
    print(f"    Monthly: ${active['monthly_estimate']:.2f}")

    # Per-invocation costs
    print(f"\n  Per-invocation costs (with caching):")
    for reason_key in TYPICAL_TOKENS:
        reason = InvocationReason(reason_key) if reason_key in [r.value for r in InvocationReason] else None
        if reason:
            threshold = ConsciousnessThreshold()
            tier = threshold._tier_for_reason(reason)
            cost = estimate_invocation_cost(tier, reason)
            print(f"    {reason_key}: {tier.value} → ${cost:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Robody Consciousness Layer"
    )
    parser.add_argument("--status", action="store_true",
                        help="Show threshold status")
    parser.add_argument("--cost", action="store_true",
                        help="Show cost estimates")
    parser.add_argument("--log", action="store_true",
                        help="Show recent invocations")
    parser.add_argument("--stats", action="store_true",
                        help="Show invocation statistics")
    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.cost:
        show_cost_estimates()
    elif args.log:
        log = ConsciousnessLog()
        recent = log.recent(20)
        if not recent:
            print("  No invocations recorded.")
        else:
            for e in recent:
                ts = e.get("timestamp", "?")[:19]
                tier = e.get("tier", "?")
                reason = e.get("reason", "?")
                cost = e.get("actual_cost", e.get("estimated_cost", 0))
                print(f"  {ts} [{tier}] {reason} (${cost:.4f})")
    elif args.stats:
        log = ConsciousnessLog()
        log.stats(verbose=True)
    else:
        show_status()
        print()
        show_cost_estimates()
