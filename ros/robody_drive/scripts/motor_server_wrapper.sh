#!/usr/bin/env bash
# Wrapper so roslaunch can start the Python 3 motor server as a node.
# roslaunch needs a single executable; this bridges to python3.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "${SCRIPT_DIR}/motor_server.py" "$@"
