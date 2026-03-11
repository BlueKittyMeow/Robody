#!/usr/bin/env python3
"""
Robody Daemon — Lifecycle Orchestrator
=======================================
The supervisor that ties all Robody cognitive modules together into a
running system. Manages startup, mode transitions, scheduled maintenance,
dream cycles, and graceful shutdown.

This is NOT a traditional init.d daemon — it's a single-process orchestrator
that runs the heartbeat loop and schedules background tasks around it.

Lifecycle:
  1. Startup: verify database, check sensors, enter initial mode
  2. Run: heartbeat loop with event-driven sensing
  3. Background: periodic health checks, weight maintenance
  4. Dream: triggered by REST mode + quiet_minutes threshold
  5. Shutdown: graceful state save, log rotation

Architecture position:
  - Sits above Layer 2 (Inner Life / Heartbeat)
  - Coordinates Layer 0-1 (Reflexes / Awareness) through sensor state
  - Triggers Layer 3 (Consciousness / Claude) when thresholds met
  - Triggers Layer 5 (Dream) during REST mode

Usage:
    python3 robody_daemon.py                    # run the daemon
    python3 robody_daemon.py --simulate         # simulation mode (no hardware)
    python3 robody_daemon.py --check            # pre-flight checks only
    python3 robody_daemon.py --status           # show current state

On Jetson Nano (production):
    systemctl start robody
    # or: python3 robody_daemon.py &

On desktop (development):
    python3 robody_daemon.py --simulate --verbose
"""

import sqlite3
import json
import time
import signal
import sys
import os
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from threading import Thread, Event

# Module imports
sys.path.insert(0, str(Path(__file__).parent))

from robody_heartbeat import Heartbeat, Mode, SensorState
from robody_graph_walker import run_walk, run_dream, run_gap_detection
from robody_weight_maintenance import (
    run_decay, apply_dream_updates, promote_confirmed_edges,
    distribution_health_check, entropy_monitor, run_nightly,
)
from robody_staging_log import (
    StagingLog, NightlyConsolidator,
    warm_today_territory, clear_warm_territory,
)
from robody_consciousness import (
    ConsciousnessThreshold, ConsciousnessLog,
    InvocationTier, InvocationReason,
)

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

DB_PATH = Path(__file__).parent / "robody_seed.sqlite"
STATE_DIR = Path(__file__).parent / "state"
LOG_DIR = Path(__file__).parent / "daemon_logs"
PID_FILE = Path(__file__).parent / "robody.pid"

# Timing constants (in seconds)
HEARTBEAT_INTERVAL = 5.0       # Base heartbeat when nothing is happening
HEALTH_CHECK_INTERVAL = 3600   # Run health check every hour
BACKGROUND_WALK_INTERVAL = 300 # Background thought every 5 minutes
DREAM_QUIET_THRESHOLD = 1800   # 30 minutes quiet before dreaming
NIGHTLY_HOUR = 3               # Run nightly maintenance at 3 AM
LOG_ROTATE_DAYS = 7            # Keep a week of logs

# Ollama configuration
OLLAMA_URL = "http://10.0.0.123:11434"  # MarshLair for now, localhost on Jetson


class RobodyDaemon:
    """
    Main orchestrator for the Robody cognitive system.

    The daemon runs a main loop that:
    1. Ticks the heartbeat (SENSE→NOTICE→THINK→DECIDE→LOG)
    2. Checks for mode transitions
    3. Schedules background tasks (thoughts, maintenance, dreams)
    4. Handles signals for graceful shutdown
    """

    def __init__(self, db_path=DB_PATH, simulate=False, verbose=False):
        self.db_path = db_path
        self.simulate = simulate
        self.verbose = verbose
        self.running = False
        self.shutdown_event = Event()

        # State
        self.heartbeat = None
        self.staging_log = StagingLog()
        self.consciousness = ConsciousnessThreshold()
        self.last_health_check = None
        self.last_background_walk = None
        self.last_nightly = None
        self.last_consciousness_check = datetime.now()
        self.dream_active = False
        self.startup_time = None
        self.cycle_count = 0

        # Logging
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.logger = self._setup_logging()

    def _setup_logging(self):
        """Configure daemon logging."""
        logger = logging.getLogger("robody")
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)

        # File handler
        log_file = LOG_DIR / f"robody_{datetime.now().strftime('%Y%m%d')}.log"
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(fh)

        # Console handler
        if self.verbose:
            ch = logging.StreamHandler()
            ch.setLevel(logging.DEBUG)
            ch.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%H:%M:%S"
            ))
            logger.addHandler(ch)

        return logger

    # ---------------------------------------------------------------
    # Pre-flight checks
    # ---------------------------------------------------------------

    def preflight(self):
        """Verify all systems before starting."""
        checks = {}

        # Database exists and is valid
        try:
            conn = sqlite3.connect(self.db_path)
            nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            conn.close()
            checks["database"] = {
                "ok": nodes > 0 and edges > 0,
                "detail": f"{nodes:,} nodes, {edges:,} edges",
            }
        except Exception as e:
            checks["database"] = {"ok": False, "detail": str(e)}

        # State directory exists
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        checks["state_dir"] = {
            "ok": STATE_DIR.exists(),
            "detail": str(STATE_DIR),
        }

        # Ollama reachable (non-blocking check)
        if not self.simulate:
            try:
                import urllib.request
                req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                    models = [m["name"] for m in data.get("models", [])]
                    has_brainstem = any("robody" in m for m in models)
                    checks["ollama"] = {
                        "ok": True,
                        "detail": f"Connected, brainstem={'yes' if has_brainstem else 'NO'}",
                    }
            except Exception as e:
                checks["ollama"] = {"ok": False, "detail": str(e)}
        else:
            checks["ollama"] = {"ok": True, "detail": "Skipped (simulation mode)"}

        # No existing PID file (or stale)
        if PID_FILE.exists():
            try:
                old_pid = int(PID_FILE.read_text().strip())
                os.kill(old_pid, 0)  # Check if process exists
                checks["pid"] = {
                    "ok": False,
                    "detail": f"Another instance running (PID {old_pid})",
                }
            except (OSError, ValueError):
                # Process doesn't exist, stale PID file
                PID_FILE.unlink()
                checks["pid"] = {"ok": True, "detail": "Stale PID cleaned up"}
        else:
            checks["pid"] = {"ok": True, "detail": "No existing PID"}

        return checks

    def print_preflight(self, checks):
        """Pretty-print preflight results."""
        print(f"\n{'='*50}")
        print(f"Robody Pre-flight Checks")
        print(f"{'='*50}")
        all_ok = True
        for name, check in checks.items():
            status = "✓" if check["ok"] else "✗"
            print(f"  {status} {name}: {check['detail']}")
            if not check["ok"]:
                all_ok = False
        print(f"\n  {'All systems go!' if all_ok else 'ISSUES DETECTED'}")
        return all_ok

    # ---------------------------------------------------------------
    # Signal handling
    # ---------------------------------------------------------------

    def _setup_signals(self):
        """Register signal handlers for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
        if hasattr(signal, "SIGUSR1"):
            signal.signal(signal.SIGUSR1, self._handle_status)

    def _handle_shutdown(self, signum, frame):
        """Graceful shutdown handler."""
        self.logger.info(f"Shutdown signal received (signal {signum})")
        self.running = False
        self.shutdown_event.set()

    def _handle_status(self, signum, frame):
        """Status request handler (kill -USR1 <pid>)."""
        self.logger.info(self._status_summary())

    def _status_summary(self):
        """Generate current status summary."""
        uptime = (datetime.now() - self.startup_time) if self.startup_time else timedelta(0)
        mode = self.heartbeat.state.mode.value if self.heartbeat else "not started"
        return (
            f"Robody Status: mode={mode}, "
            f"uptime={uptime}, "
            f"cycles={self.cycle_count}, "
            f"dreaming={self.dream_active}"
        )

    # ---------------------------------------------------------------
    # Main loop
    # ---------------------------------------------------------------

    def start(self):
        """Start the Robody daemon."""
        # Pre-flight
        checks = self.preflight()
        all_ok = all(c["ok"] for c in checks.values())
        if self.verbose:
            self.print_preflight(checks)
        if not all_ok:
            self.logger.error("Pre-flight checks failed, aborting")
            return False

        # Write PID
        PID_FILE.write_text(str(os.getpid()))

        # Setup signals
        self._setup_signals()

        # Initialize heartbeat
        self.heartbeat = Heartbeat(
            db_path=self.db_path,
            simulate=self.simulate,
            verbose=self.verbose,
        )
        self.heartbeat.initialize()

        self.startup_time = datetime.now()
        self.running = True
        self.last_health_check = datetime.now()
        self.last_background_walk = datetime.now()
        self.last_nightly = datetime.now()

        self.logger.info(f"Robody daemon started (PID {os.getpid()}, "
                        f"simulate={self.simulate})")
        self.logger.info(f"Database: {self.db_path}")
        self.logger.info(f"Initial mode: {self.heartbeat.state.mode.value}")

        try:
            self._run_loop()
        except Exception as e:
            self.logger.error(f"Fatal error in main loop: {e}", exc_info=True)
        finally:
            self._shutdown()

        return True

    def _run_loop(self):
        """Core event loop."""
        while self.running:
            cycle_start = time.time()
            entry = None

            # 1. Heartbeat tick
            try:
                entry = self.heartbeat.run_cycle()
                self.cycle_count += 1
                if self.verbose and self.cycle_count % 10 == 0:
                    self.logger.debug(
                        f"Cycle {self.cycle_count}: mode={entry.get('mode', '?')}, "
                        f"decision={entry.get('decision', '?')}"
                    )
            except Exception as e:
                self.logger.warning(f"Heartbeat cycle error: {e}")

            # 2. Check for scheduled tasks
            now = datetime.now()

            # Background thoughts (every 5 minutes, when not dreaming)
            if (not self.dream_active and
                    (now - self.last_background_walk).total_seconds() > BACKGROUND_WALK_INTERVAL):
                self._run_background_thought()
                self.last_background_walk = now

            # Health check (every hour)
            if (now - self.last_health_check).total_seconds() > HEALTH_CHECK_INTERVAL:
                self._run_health_check()
                self.last_health_check = now

            # Nightly maintenance (at 3 AM, once per day)
            if (now.hour == NIGHTLY_HOUR and
                    (now - self.last_nightly).total_seconds() > 72000):  # >20 hours since last
                self._run_nightly_maintenance()
                self.last_nightly = now

            # 3. Consciousness threshold check (every 30 seconds)
            if (not self.dream_active and
                    (now - self.last_consciousness_check).total_seconds() > 30):
                self._check_consciousness(entry)
                self.last_consciousness_check = now

            # 4. Check for dream trigger
            if self._should_dream():
                self._run_dream_cycle()

            # 5. Sleep until next cycle
            elapsed = time.time() - cycle_start
            sleep_time = max(0.1, HEARTBEAT_INTERVAL - elapsed)

            # Adaptive sleep: shorter when active, longer when resting
            if self.heartbeat and self.heartbeat.state.mode in (Mode.REST, Mode.DREAM):
                sleep_time = min(sleep_time * 3, 30.0)
            elif self.heartbeat and self.heartbeat.state.mode == Mode.ALERT:
                sleep_time = min(sleep_time * 0.3, 1.0)

            self.shutdown_event.wait(timeout=sleep_time)

    # ---------------------------------------------------------------
    # Scheduled tasks
    # ---------------------------------------------------------------

    def _run_background_thought(self):
        """Run a brief background thought walk."""
        self.logger.debug("Running background thought...")
        try:
            dialogues = run_walk(
                steps=10,
                density_threshold=3,
                dry_run=self.simulate,
                verbose=False,
            )
            if dialogues and self.verbose:
                self.logger.debug(f"Background thought produced {len(dialogues)} entries")
        except Exception as e:
            self.logger.warning(f"Background thought error: {e}")

    def _run_health_check(self):
        """Run periodic graph health check."""
        self.logger.info("Running health check...")
        try:
            health = distribution_health_check(self.db_path, verbose=False)
            entropy = entropy_monitor(self.db_path, verbose=False)

            self.logger.info(
                f"Health: {health.get('total_edges', 0)} edges, "
                f"entropy={entropy.get('edge_weight_entropy', 0):.2f}"
            )

            # Log health state
            log_file = LOG_DIR / "health_history.jsonl"
            with open(log_file, "a") as f:
                f.write(json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "health": health,
                    "entropy": entropy,
                }) + "\n")

        except Exception as e:
            self.logger.warning(f"Health check error: {e}")

    def _check_consciousness(self, heartbeat_entry=None):
        """
        Evaluate whether to invoke consciousness (Claude API).

        This is the gate between brainstem processing and full awareness.
        Most cycles, nothing happens — the brainstem handles it fine.
        Occasionally, conditions warrant bringing in the consciousness
        layer for deeper processing.

        When invoked, the request gets logged for cost tracking.
        The actual API call is stubbed for now (TODO: implement API caller).
        """
        try:
            current_mode = self.heartbeat.state.mode if self.heartbeat else None
            staging_entries = self.staging_log.read_today()

            request = self.consciousness.evaluate(
                heartbeat_entry=heartbeat_entry,
                staging_entries=staging_entries,
                current_mode=current_mode,
            )

            if request:
                self.logger.info(
                    f"Consciousness invocation: {request.tier.value} for "
                    f"{request.reason.value} (urgency={request.urgency:.2f}, "
                    f"est=${request.estimated_cost:.4f})"
                )

                if not self.simulate:
                    # TODO: actual API call goes here
                    # For now, just log the request
                    self.consciousness.log.record(request)
                    self.logger.info("  (API call stubbed — logged for cost tracking)")

                    # Log to staging (consciousness invocations are experiences too)
                    self.staging_log.record_action(
                        action=f"consciousness_invocation_{request.tier.value}",
                        motivation=request.reason.value,
                        outcome="stubbed",
                    )

        except Exception as e:
            self.logger.warning(f"Consciousness check error: {e}")

    def _run_nightly_maintenance(self):
        """
        Run the full nightly maintenance sequence.

        Order matters (from Part 13, updated with territory warming):
          1. Warm territory: nudge edges near today's activated concepts
          2. Consolidation: staging log → graph updates (today's experiences)
          3. Dream cycle: runs on the warmed, updated graph
          4. Clear warm territory: remove temporary nudges
          5. Weight maintenance: decay, promotion, health check
          6. Log rotation

        The warming happens BEFORE consolidation so the dream walker has
        gravitational pull toward the day's experiences. Clearing happens
        AFTER dreaming but BEFORE weight decay, so the decay operates on
        true weights rather than artificially inflated ones.
        """
        self.logger.info("Starting nightly maintenance...")
        try:
            # Step 1: Warm territory around today's experiences
            self.logger.info("  [1/6] Warming today's territory...")
            warm_result = warm_today_territory(
                db_path=self.db_path,
                staging_dir=self.staging_log.staging_dir,
                dry_run=self.simulate,
                verbose=self.verbose,
            )
            self.logger.info(
                f"  Warmed: {warm_result['edges_warmed']} edges near "
                f"{len(warm_result['nodes_matched'])} activated nodes"
            )

            # Step 2: Consolidate staging log into graph
            self.logger.info("  [2/6] Consolidating staging log...")
            consolidator = NightlyConsolidator(
                db_path=self.db_path,
                dry_run=self.simulate,
                verbose=self.verbose,
            )
            consol_result = consolidator.run()
            self.logger.info(f"  Consolidation: {consol_result}")

            # Step 3: Dream cycle (runs on warmed, updated graph)
            self.logger.info("  [3/6] Running dream cycle...")
            self._run_dream_cycle()

            # Step 4: Clear warm territory (restore true weights)
            self.logger.info("  [4/6] Clearing warm territory...")
            clear_result = clear_warm_territory(
                db_path=self.db_path,
                staging_dir=self.staging_log.staging_dir,
                verbose=self.verbose,
            )
            self.logger.info(f"  Cleared: {clear_result['edges_cleared']} edges")

            # Step 5: Weight maintenance (on true weights, not warmed)
            self.logger.info("  [5/6] Running weight maintenance...")
            result = run_nightly(
                db_path=self.db_path,
                dry_run=self.simulate,
                verbose=self.verbose,
            )
            self.logger.info(f"  Weight maintenance: {result}")

            # Step 6: Rotate old logs
            self.logger.info("  [6/6] Rotating logs...")
            self._rotate_logs()

            self.logger.info("Nightly maintenance complete.")

        except Exception as e:
            self.logger.error(f"Nightly maintenance error: {e}", exc_info=True)

    def _should_dream(self):
        """Check if conditions are right for dreaming."""
        if self.dream_active:
            return False
        if not self.heartbeat:
            return False

        state = self.heartbeat.state

        # Must be in REST mode
        if state.mode != Mode.REST:
            return False

        # Must have been quiet for a while
        if state.recent_thoughts:
            # Not truly quiet
            return False

        # Check quiet_minutes from sensor state
        sensors = self.heartbeat.sensors
        if sensors and sensors.quiet_minutes >= (DREAM_QUIET_THRESHOLD / 60):
            return True

        return False

    def _run_dream_cycle(self):
        """Run the full dream cycle."""
        self.dream_active = True
        self.logger.info("Entering dream cycle...")

        # Switch to DREAM mode
        if self.heartbeat:
            self.heartbeat.state.mode = Mode.DREAM
            self.heartbeat.state.dream_due = False

        try:
            result = run_dream(
                dry_run=self.simulate,
                verbose=self.verbose,
            )
            if result:
                self.logger.info(
                    f"Dream cycle complete: {len(result.get('fragments', []))} fragments, "
                    f"{len(result.get('new_edges', []))} new edges"
                )

                # Apply dream weight updates
                apply_dream_updates(
                    db_path=self.db_path,
                    dry_run=self.simulate,
                    verbose=False,
                )

        except Exception as e:
            self.logger.error(f"Dream cycle error: {e}", exc_info=True)
        finally:
            self.dream_active = False
            # Return to REST mode
            if self.heartbeat:
                self.heartbeat.state.mode = Mode.REST

    # ---------------------------------------------------------------
    # Shutdown and cleanup
    # ---------------------------------------------------------------

    def _shutdown(self):
        """Graceful shutdown."""
        self.logger.info("Shutting down...")

        # Save final state
        try:
            state_file = STATE_DIR / "daemon_state.json"
            state_file.write_text(json.dumps({
                "shutdown_time": datetime.now().isoformat(),
                "cycles": self.cycle_count,
                "uptime_s": (datetime.now() - self.startup_time).total_seconds()
                if self.startup_time else 0,
                "last_mode": self.heartbeat.state.mode.value
                if self.heartbeat else "unknown",
            }, indent=2))
        except Exception as e:
            self.logger.warning(f"State save error: {e}")

        # Clean PID file
        if PID_FILE.exists():
            PID_FILE.unlink()

        self.logger.info(
            f"Robody daemon stopped. "
            f"Ran {self.cycle_count} cycles over "
            f"{(datetime.now() - self.startup_time) if self.startup_time else 'unknown'}"
        )

    def _rotate_logs(self):
        """Remove logs older than LOG_ROTATE_DAYS."""
        cutoff = datetime.now() - timedelta(days=LOG_ROTATE_DAYS)
        for log_file in LOG_DIR.glob("*.log"):
            try:
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff:
                    log_file.unlink()
                    self.logger.debug(f"Rotated old log: {log_file.name}")
            except Exception:
                pass


# -------------------------------------------------------------------
# Status command
# -------------------------------------------------------------------

def show_status():
    """Show current daemon status."""
    print(f"\n{'='*50}")
    print(f"Robody Daemon Status")
    print(f"{'='*50}")

    # Check PID
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)
            print(f"  Running: PID {pid}")
        except (OSError, ValueError):
            print(f"  Not running (stale PID file)")
    else:
        print(f"  Not running")

    # Check last state
    state_file = STATE_DIR / "daemon_state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            print(f"  Last shutdown: {state.get('shutdown_time', 'unknown')}")
            print(f"  Last mode: {state.get('last_mode', 'unknown')}")
            print(f"  Total cycles: {state.get('cycles', 0)}")
        except Exception:
            pass

    # Check database
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            conn.close()
            print(f"  Database: {nodes:,} nodes, {edges:,} edges")
            print(f"  DB size: {DB_PATH.stat().st_size / (1024*1024):.1f} MB")
        except Exception as e:
            print(f"  Database error: {e}")

    # Recent logs
    logs = sorted(LOG_DIR.glob("robody_*.log"), reverse=True)
    if logs:
        latest = logs[0]
        print(f"  Latest log: {latest.name}")
        # Show last 5 lines
        try:
            lines = latest.read_text().strip().split("\n")
            print(f"  Recent activity:")
            for line in lines[-5:]:
                print(f"    {line}")
        except Exception:
            pass


# -------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Robody Daemon")
    parser.add_argument("--simulate", action="store_true",
                        help="Simulation mode (no hardware, no LLM calls)")
    parser.add_argument("--check", action="store_true",
                        help="Run pre-flight checks only")
    parser.add_argument("--status", action="store_true",
                        help="Show current daemon status")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--db", type=str, default=str(DB_PATH))
    args = parser.parse_args()

    if args.status:
        show_status()
        sys.exit(0)

    daemon = RobodyDaemon(
        db_path=Path(args.db),
        simulate=args.simulate,
        verbose=args.verbose,
    )

    if args.check:
        checks = daemon.preflight()
        all_ok = daemon.print_preflight(checks)
        sys.exit(0 if all_ok else 1)

    success = daemon.start()
    sys.exit(0 if success else 1)
