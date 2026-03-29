#!/usr/bin/env python3
"""
motor_test.py — Individual motor verification for Robody mecanum chassis
Run this BEFORE wiring all four motors to confirm each M1–M4 terminal.

Wheel layout (looking down from above):
    FL(M1) --- FR(M2)
      |           |
    RL(M3) --- RR(M4)

Usage:
    python3 motor_test.py              # full auto sequence
    python3 motor_test.py --motor 1    # test one motor only
    python3 motor_test.py --interactive  # step through manually
"""

import time
import sys
import argparse

try:
    from adafruit_motorkit import MotorKit
    from adafruit_motor import motor as motor_lib
except ImportError:
    print("ERROR: adafruit_motorkit not installed.")
    print("  pip3 install adafruit-circuitpython-motorkit --break-system-packages")
    sys.exit(1)

# ------------------------------------------------------------------
# Motor layout — adjust if wiring differs
# These names correspond to the Motor HAT screw terminals M1–M4
# ------------------------------------------------------------------
MOTOR_NAMES = {
    1: "Front-Left  (FL)",
    2: "Front-Right (FR)",
    3: "Rear-Left   (RL)",
    4: "Rear-Right  (RR)",
}

TEST_SPEED = 0.4      # fraction of max speed for testing (0.0–1.0)
SPIN_DURATION = 1.5   # seconds per direction during test
PAUSE_BETWEEN = 0.5   # seconds between steps


def get_motor(kit, idx):
    """Return motor object by 1-indexed terminal number."""
    motors = [None, kit.motor1, kit.motor2, kit.motor3, kit.motor4]
    return motors[idx]


def stop_all(kit):
    for i in range(1, 5):
        m = get_motor(kit, i)
        m.throttle = None   # BRAKE / float (None = coast)


def test_motor(kit, idx, interactive=False):
    """Spin one motor forward, then reverse, then stop."""
    name = MOTOR_NAMES.get(idx, f"Motor {idx}")
    m = get_motor(kit, idx)

    print(f"\n  Motor {idx} ({name})")

    if interactive:
        input(f"    Press Enter to spin M{idx} FORWARD...")

    print(f"    → Forward  ({TEST_SPEED:.0%} throttle, {SPIN_DURATION}s)")
    m.throttle = TEST_SPEED
    time.sleep(SPIN_DURATION)

    print(f"    → Stop")
    m.throttle = 0
    time.sleep(PAUSE_BETWEEN)

    if interactive:
        input(f"    Press Enter to spin M{idx} REVERSE...")

    print(f"    → Reverse  ({TEST_SPEED:.0%} throttle, {SPIN_DURATION}s)")
    m.throttle = -TEST_SPEED
    time.sleep(SPIN_DURATION)

    print(f"    → Stop")
    m.throttle = 0
    time.sleep(PAUSE_BETWEEN)

    if interactive:
        label = input(f"    Did M{idx} spin both directions? (y/n/skip): ").strip().lower()
        return label != 'n'
    return True


def demo_mecanum_moves(kit):
    """
    Brief demos of combined motor patterns for mecanum verification.
    These require all 4 motors wired and the robot chassis assembled.
    """
    print("\n--- Mecanum movement demos (all 4 motors) ---")
    print("  Each move lasts 1.5 seconds at 30% speed.\n")

    moves = [
        ("Forward",          ( 1,  1,  1,  1)),  # all forward
        ("Backward",         (-1, -1, -1, -1)),  # all reverse
        ("Strafe right",     (-1,  1,  1, -1)),  # mecanum lateral
        ("Strafe left",      ( 1, -1, -1,  1)),
        ("Rotate CW",        ( 1, -1,  1, -1)),  # spin in place
        ("Rotate CCW",       (-1,  1, -1,  1)),
    ]

    DEMO_SPEED = 0.3
    DEMO_DUR   = 1.5

    # Motor mapping (verified March 29, 2026):
    # M1=RL, M2=FL, M3=RR, M4=FR
    for label, (fl, fr, rl, rr) in moves:
        print(f"  {label}...")
        kit.motor2.throttle = fl * DEMO_SPEED   # M2 = Front Left
        kit.motor4.throttle = fr * DEMO_SPEED   # M4 = Front Right
        kit.motor1.throttle = rl * DEMO_SPEED   # M1 = Rear Left
        kit.motor3.throttle = rr * DEMO_SPEED   # M3 = Rear Right
        time.sleep(DEMO_DUR)
        stop_all(kit)
        time.sleep(0.4)

    print("  Done.")


def main():
    parser = argparse.ArgumentParser(description="Robody motor test")
    parser.add_argument("--motor", type=int, choices=[1, 2, 3, 4],
                        help="Test only this motor terminal (1–4)")
    parser.add_argument("--interactive", action="store_true",
                        help="Pause between each step for manual confirmation")
    parser.add_argument("--demo", action="store_true",
                        help="Run mecanum movement demos after individual tests")
    args = parser.parse_args()

    print("=" * 50)
    print("  Robody Motor Test")
    print("=" * 50)
    print("  Motor HAT I2C address: 0x60")
    print("  Test speed:", TEST_SPEED)
    print()
    print("  SAFETY: Keep robot on a stand or blocked from rolling.")
    print("  Ctrl+C at any time to stop all motors.\n")

    try:
        kit = MotorKit()   # defaults to I2C bus 1, address 0x60
    except Exception as e:
        print(f"ERROR: Could not init MotorKit: {e}")
        print("  Is the Motor HAT connected? Is I2C enabled?")
        sys.exit(1)

    # Ensure all motors start stopped
    stop_all(kit)

    try:
        if args.motor:
            # Single motor test
            test_motor(kit, args.motor, interactive=args.interactive)
        else:
            # All motors, one at a time
            print("Testing motors M1 → M4 one at a time.")
            results = {}
            for i in range(1, 5):
                ok = test_motor(kit, i, interactive=args.interactive)
                results[i] = ok

            print("\n--- Results ---")
            for i in range(1, 5):
                status = "✓ OK" if results.get(i, True) else "✗ CHECK WIRING"
                print(f"  M{i} ({MOTOR_NAMES[i]}): {status}")

        if args.demo:
            if not args.interactive or input("\nRun mecanum movement demos? (y/n): ").lower() == 'y':
                demo_mecanum_moves(kit)

    except KeyboardInterrupt:
        print("\n  Interrupted.")
    finally:
        stop_all(kit)
        print("  All motors stopped. Done.")


if __name__ == "__main__":
    main()
