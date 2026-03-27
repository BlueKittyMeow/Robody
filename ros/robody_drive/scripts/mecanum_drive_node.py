#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
mecanum_drive_node.py — ROS Melodic drive node (Python 2.7)

Bridges ROS /cmd_vel → motor_server.py (Python 3) via local TCP socket.
This split is necessary because ROS Melodic's rospy is Python 2.7-only,
while the Adafruit MotorKit requires Python 3.

Architecture:
    [ROS teleop / nav] → /cmd_vel (Twist)
        → mecanum_drive_node.py (Python 2.7, this file)
            → TCP socket 127.0.0.1:9877
                → motor_server.py (Python 3, owns MotorKit + hardware)
                    → Adafruit Motor HAT → wheels

Subscribes:  /cmd_vel       (geometry_msgs/Twist)
Publishes:   /robody/drive/status   (std_msgs/String)  JSON wheel state
             /robody/battery        (std_msgs/String)  JSON battery state

Parameters:
    ~max_linear_speed   (float, default 0.4)   m/s at full throttle
    ~max_angular_speed  (float, default 1.2)   rad/s at full throttle
    ~cmd_vel_timeout    (float, default 0.5)   stop if no cmd_vel
    ~battery_interval   (float, default 30.0)  seconds between batt reads
    ~motor_server_port  (int,   default 9877)  TCP port of motor_server

Usage:
    # Start motor server first (Python 3):
    python3 ~/catkin_ws/src/robody_drive/scripts/motor_server.py &

    # Then start this ROS node:
    roslaunch robody_drive drive.launch
"""

import json
import socket
import time
import threading

import rospy
from geometry_msgs.msg import Twist
from std_msgs.msg import String

HOST = '127.0.0.1'


class MotorClient(object):
    """Thin TCP client for motor_server.py."""

    def __init__(self, port):
        self._port    = port
        self._sock    = None
        self._lock    = threading.Lock()
        self._connect()

    def _connect(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect((HOST, self._port))
            self._sock = s
            rospy.loginfo("Connected to motor_server on port %d", self._port)
        except Exception as e:
            rospy.logwarn("motor_server not reachable (port %d): %s", self._port, e)
            self._sock = None

    def send(self, msg_dict):
        """Send a dict, get a response dict. Returns None on failure."""
        with self._lock:
            payload = (json.dumps(msg_dict) + "\n").encode()
            for attempt in range(2):
                if self._sock is None:
                    self._connect()
                if self._sock is None:
                    return None
                try:
                    self._sock.sendall(payload)
                    resp = b""
                    while b"\n" not in resp:
                        chunk = self._sock.recv(512)
                        if not chunk:
                            raise socket.error("connection closed")
                        resp += chunk
                    return json.loads(resp.split(b"\n")[0].decode())
                except Exception as e:
                    rospy.logwarn_throttle(5, "motor_server send failed: %s", e)
                    try:
                        self._sock.close()
                    except Exception:
                        pass
                    self._sock = None
        return None

    def stop(self):
        self.send({"cmd": "stop"})


class MecanumDriveNode(object):

    def __init__(self):
        rospy.init_node('mecanum_drive', anonymous=False)

        # Parameters
        self.max_linear    = rospy.get_param('~max_linear_speed',  0.4)
        self.max_angular   = rospy.get_param('~max_angular_speed', 1.2)
        self.cmd_timeout   = rospy.get_param('~cmd_vel_timeout',   0.5)
        self.batt_interval = rospy.get_param('~battery_interval',  30.0)
        port               = int(rospy.get_param('~motor_server_port', 9877))

        self._client           = MotorClient(port)
        self._last_cmd_time    = rospy.Time.now()
        self._last_batt_time   = 0.0
        self._last_status      = None

        # Publishers
        self._status_pub  = rospy.Publisher('/robody/drive/status', String, queue_size=1)
        self._battery_pub = rospy.Publisher('/robody/battery',       String, queue_size=1)

        # Subscriber
        rospy.Subscriber('/cmd_vel', Twist, self._cmd_vel_cb, queue_size=1)

        rospy.on_shutdown(self._shutdown)
        rospy.loginfo("robody_drive node ready. Listening on /cmd_vel")

    def _cmd_vel_cb(self, msg):
        self._last_cmd_time = rospy.Time.now()

        vx    = max(-1.0, min(1.0, msg.linear.x  / max(self.max_linear,  0.001)))
        vy    = max(-1.0, min(1.0, msg.linear.y  / max(self.max_linear,  0.001)))
        omega = max(-1.0, min(1.0, msg.angular.z / max(self.max_angular, 0.001)))

        resp = self._client.send({"vx": vx, "vy": vy, "omega": omega})
        if resp:
            self._last_status = resp

    def _check_timeout(self):
        elapsed = (rospy.Time.now() - self._last_cmd_time).to_sec()
        if elapsed > self.cmd_timeout:
            self._client.send({"cmd": "stop"})

    def _publish_status(self):
        resp = self._client.send({"cmd": "status"})
        if resp:
            self._status_pub.publish(String(data=json.dumps(resp)))

    def _poll_battery(self):
        now = time.time()
        if now - self._last_batt_time < self.batt_interval:
            return
        resp = self._client.send({"cmd": "battery"})
        if resp and resp.get("ok"):
            self._battery_pub.publish(String(data=json.dumps(resp)))
            pct = resp.get("battery_pct", "?")
            chg = "charging" if resp.get("charging") else "discharging"
            rospy.loginfo("Battery: %s%%  %s  %.2fV",
                          pct, chg, resp.get("battery_v_mv", 0) / 1000.0)
            if resp.get("battery_low"):
                rospy.logwarn("BATTERY LOW — seek dock!")
        self._last_batt_time = now

    def spin(self):
        rate          = rospy.Rate(20)
        status_tick   = 0

        while not rospy.is_shutdown():
            self._check_timeout()

            status_tick += 1
            if status_tick >= 10:     # ~2 Hz
                self._publish_status()
                status_tick = 0

            self._poll_battery()
            rate.sleep()

    def _shutdown(self):
        rospy.loginfo("Stopping motors on shutdown.")
        self._client.stop()


if __name__ == '__main__':
    try:
        node = MecanumDriveNode()
        node.spin()
    except rospy.ROSInterruptException:
        pass
