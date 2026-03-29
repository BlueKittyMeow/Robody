#!/usr/bin/env python3
"""
mecanum.py — Mecanum wheel kinematics and motor control for Robody

Provides the MecanumDrive class: accepts (vx, vy, omega) velocity commands
and maps them to individual motor throttles via the Adafruit Motor HAT.

Coordinate frame (ROS convention):
    +X = forward
    +Y = left (strafe)
    +Z = up

Positive omega = counter-clockwise (CCW) rotation from above.

Wheel layout (top-down view):
    FL(M2) ── FR(M4)
       |           |
    RL(M1) ── RR(M3)

Mecanum roller angles:
    FL: rollers at +45°  (/)
    FR: rollers at -45°  (\)
    RL: rollers at -45°  (\)
    RR: rollers at +45°  (/)

Inverse kinematics (velocity → wheel speed):
    FL =  vx - vy - (lx + ly) * omega
    FR =  vx + vy + (lx + ly) * omega
    RL =  vx + vy - (lx + ly) * omega
    RR =  vx - vy + (lx + ly) * omega

where lx, ly are the half-distances between wheel centers.

Usage:
    from mecanum import MecanumDrive

    drive = MecanumDrive()
    drive.move(vx=0.5, vy=0.0, omega=0.0)  # forward at 50%
    drive.move(vx=0.0, vy=0.5, omega=0.0)  # strafe left at 50%
    drive.stop()
"""

import time
import sys

try:
    from adafruit_motorkit import MotorKit
except ImportError:
    print("ERROR: adafruit_motorkit not installed.")
    sys.exit(1)

# ------------------------------------------------------------------
# Chassis geometry (meters — update with actual measurements)
# These don't affect throttle mapping (which uses normalized ±1.0 units)
# but will matter when integrating with ROS odometry.
# ------------------------------------------------------------------
WHEEL_BASE_M   = 0.120   # distance between front and rear axles (m)
TRACK_WIDTH_M  = 0.160   # distance between left and right wheels (m)
WHEEL_RADIUS_M = 0.038   # mecanum wheel radius (m) — 75mm diameter

# Geometric constant used in kinematics
LX = WHEEL_BASE_M  / 2.0   # half wheelbase
LY = TRACK_WIDTH_M / 2.0   # half track width
L  = LX + LY               # sum used in omega mixing

# Motor index → physical position (verified March 29, 2026)
# All four spin forward with positive throttle — no inversions needed
MOTOR_FL = 2   # Motor HAT M2 → Front Left
MOTOR_FR = 4   # Motor HAT M4 → Front Right
MOTOR_RL = 1   # Motor HAT M1 → Rear Left
MOTOR_RR = 3   # Motor HAT M3 → Rear Right

# Safety: max throttle allowed (0.0–1.0). Reduce to slow-walk during testing.
MAX_THROTTLE = 1.0


class MecanumDrive:
    """
    Mecanum wheel drive controller for Robody.

    Translates (vx, vy, omega) velocity commands in normalized units
    (−1.0 to +1.0) to individual motor throttles.

    Normalization: vx=1.0 means full forward, vx=-1.0 means full reverse.
    Values are clamped to [-1.0, 1.0] and scaled by MAX_THROTTLE.
    """

    def __init__(self, i2c_address=0x60, max_throttle=None):
        self.kit = MotorKit(address=i2c_address)
        self._motors = {
            MOTOR_FL: self.kit.motor2,
            MOTOR_FR: self.kit.motor4,
            MOTOR_RL: self.kit.motor1,
            MOTOR_RR: self.kit.motor3,
        }
        self.max_throttle = max_throttle or MAX_THROTTLE
        self._last_cmd = (0.0, 0.0, 0.0)
        self.stop()

    # ------------------------------------------------------------------
    # Core motion commands
    # ------------------------------------------------------------------

    def move(self, vx=0.0, vy=0.0, omega=0.0):
        """
        Set wheel speeds from velocity command.

        Args:
            vx:    forward/backward (-1.0 = full reverse, +1.0 = full forward)
            vy:    lateral strafe   (-1.0 = full right,   +1.0 = full left)
            omega: rotation         (-1.0 = full CW,      +1.0 = full CCW)
        """
        self._last_cmd = (vx, vy, omega)

        # Inverse kinematics
        fl =  vx - vy - L * omega
        fr =  vx + vy + L * omega
        rl =  vx + vy - L * omega
        rr =  vx - vy + L * omega

        # Normalize: if any value exceeds 1.0, scale all down proportionally
        max_val = max(abs(fl), abs(fr), abs(rl), abs(rr), 1.0)
        fl /= max_val
        fr /= max_val
        rl /= max_val
        rr /= max_val

        # Apply max throttle ceiling and set
        self._set_throttles(
            fl * self.max_throttle,
            fr * self.max_throttle,
            rl * self.max_throttle,
            rr * self.max_throttle,
        )

    def stop(self):
        """Stop all motors (coast)."""
        for m in self._motors.values():
            m.throttle = 0
        self._last_cmd = (0.0, 0.0, 0.0)

    def brake(self):
        """Active brake all motors (set throttle to None = motor driver brake mode)."""
        for m in self._motors.values():
            m.throttle = None
        self._last_cmd = (0.0, 0.0, 0.0)

    # ------------------------------------------------------------------
    # Named convenience moves (useful for testing and scripted behavior)
    # ------------------------------------------------------------------

    def forward(self, speed=0.5):
        self.move(vx=speed)

    def backward(self, speed=0.5):
        self.move(vx=-speed)

    def strafe_right(self, speed=0.5):
        self.move(vy=-speed)

    def strafe_left(self, speed=0.5):
        self.move(vy=speed)

    def rotate_cw(self, speed=0.5):
        self.move(omega=-speed)

    def rotate_ccw(self, speed=0.5):
        self.move(omega=speed)

    def diagonal_forward_right(self, speed=0.5):
        self.move(vx=speed, vy=-speed)

    def diagonal_forward_left(self, speed=0.5):
        self.move(vx=speed, vy=speed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_throttles(self, fl, fr, rl, rr):
        """Apply throttle values with clamping."""
        values = {
            MOTOR_FL: fl,
            MOTOR_FR: fr,
            MOTOR_RL: rl,
            MOTOR_RR: rr,
        }
        for idx, val in values.items():
            clamped = max(-1.0, min(1.0, val))
            self._motors[idx].throttle = clamped

    def get_last_cmd(self):
        return self._last_cmd

    def set_max_throttle(self, value):
        """Dynamically adjust speed ceiling (useful for safety limits)."""
        self.max_throttle = max(0.0, min(1.0, value))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stop()

    def __repr__(self):
        vx, vy, omega = self._last_cmd
        return (f"MecanumDrive(vx={vx:.2f}, vy={vy:.2f}, omega={omega:.2f}, "
                f"max_throttle={self.max_throttle:.2f})")


# ------------------------------------------------------------------
# Quick demo / self-test when run directly
# ------------------------------------------------------------------

def demo():
    """Run a brief movement demo to verify mecanum kinematics."""
    import argparse
    parser = argparse.ArgumentParser(description="Mecanum kinematics demo")
    parser.add_argument("--speed", type=float, default=0.3,
                        help="Demo speed (0.0–1.0, default 0.3)")
    parser.add_argument("--duration", type=float, default=1.5,
                        help="Seconds per move (default 1.5)")
    args = parser.parse_args()

    spd = args.speed
    dur = args.duration

    print("=" * 50)
    print("  Robody Mecanum Drive Demo")
    print("=" * 50)
    print(f"  Speed: {spd:.0%}  Duration: {dur}s/move")
    print("  Keep robot clear of obstacles!\n")
    print("  Ctrl+C to abort at any time.\n")

    moves = [
        ("Forward",             lambda d: d.forward(spd)),
        ("Backward",            lambda d: d.backward(spd)),
        ("Strafe right",        lambda d: d.strafe_right(spd)),
        ("Strafe left",         lambda d: d.strafe_left(spd)),
        ("Rotate CW",           lambda d: d.rotate_cw(spd)),
        ("Rotate CCW",          lambda d: d.rotate_ccw(spd)),
        ("Diagonal fwd-right",  lambda d: d.diagonal_forward_right(spd)),
        ("Diagonal fwd-left",   lambda d: d.diagonal_forward_left(spd)),
    ]

    try:
        with MecanumDrive() as drive:
            for label, fn in moves:
                print(f"  {label}...")
                fn(drive)
                time.sleep(dur)
                drive.stop()
                time.sleep(0.4)

        print("\n  Demo complete. All motors stopped.")

    except KeyboardInterrupt:
        print("\n  Aborted.")


if __name__ == "__main__":
    demo()
