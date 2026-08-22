import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile
from rclpy.utilities import remove_ros_args
from sensor_msgs.msg import Joy
from std_msgs.msg import Bool, Empty
from geometry_msgs.msg import PoseStamped
from fastapi import FastAPI, WebSocket
import uvicorn
import argparse
import sys
import threading
import math
import time

from joy_node_web.client import DEFAULT_NODE_PORT, add_client_routes


app = FastAPI()
msg = Joy()
msg2 = Joy()

# ── Command state (shared with the ROS node thread) ────────────────────────
# These globals are written from the WebSocket (uvicorn) thread and read /
# published from the ROS timer thread, mirroring how msg / msg2 are handled.
emergency_stop = False   # continuously published on /emergency_stop
pending_goal = None      # PoseStamped published once on /goal_pose
pending_cancel = False   # published once on /cancel_goal

# Watchdog: monotonic timestamp of the last joy payload received over the
# WebSocket. When stale (no fresh input within JOY_INPUT_TIMEOUT) the ROS
# timer publishes a neutralized (zeroed) Joy instead of the last held
# values, so a dropped/stalled WebSocket can never leave stale non-zero
# input being published on /joy (fail-safe against runaway drive).
last_joy_rx = 0.0
JOY_INPUT_TIMEOUT = 0.5  # seconds


def handle_command(data):
    """Handle a control command received over the WebSocket.

    Command messages are distinguished from joy data by the ``command``
    key, so existing joy clients (which never send it) are unaffected.
    The actual publishing happens in the ROS timer thread; here we only
    update shared state.
    """
    global emergency_stop, pending_goal, pending_cancel
    command = data.get("command")

    if command == "emergency_stop":
        emergency_stop = True
    elif command == "emergency_release":
        emergency_stop = False
    elif command == "cancel_goal":
        pending_cancel = True
    elif command == "set_goal":
        pose = PoseStamped()
        pose.header.frame_id = data.get("frame_id", "map")
        pose.pose.position.x = float(data.get("x", 0.0))
        pose.pose.position.y = float(data.get("y", 0.0))
        pose.pose.position.z = 0.0
        yaw = float(data.get("yaw", 0.0))
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        pending_goal = pose


@app.websocket("/joys")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    global msg, msg2, last_joy_rx
    while True:
        gamepad_info = await websocket.receive_json()

        # Control command (non joy). Backward compatible: existing joy
        # clients send {id, axes, buttons} without a "command" field.
        if isinstance(gamepad_info, dict) and "command" in gamepad_info:
            handle_command(gamepad_info)
            continue

        if "type" in gamepad_info and gamepad_info["type"] == 1:
            msg_in = msg2
        else:
            msg_in = msg

        for i in range(len(gamepad_info["axes"])):
            if len(msg_in.axes) <= i:
                msg_in.axes.append(gamepad_info["axes"][i])
            else:
                msg_in.axes[i] = gamepad_info["axes"][i]

        for i in range(len(gamepad_info["buttons"])):
            if len(msg_in.buttons) <= i:
                msg_in.buttons.append(int(gamepad_info["buttons"][i]))
            else:
                msg_in.buttons[i] = int(gamepad_info["buttons"][i])

        # Fresh joy input arrived: pet the watchdog (see update_joy).
        last_joy_rx = time.monotonic()


def web_start(host="0.0.0.0", port=DEFAULT_NODE_PORT):
    print("boot webserver thread")
    uvicorn.run(app, host=host, port=port)


def exchangeMapping(mapping):
    # comming soon
    return mapping


class JoyNodeWeb(Node):
    def __init__(self):
        super().__init__("joy_node_web")
        qos_profile = QoSProfile(depth=2)
        self.timer = self.create_timer(0.01, self.update_joy)  # 100 Hz low-latency publish
        self.pub  = self.create_publisher(Joy, "/joy",  qos_profile=qos_profile)
        self.pub2 = self.create_publisher(Joy, "/joy2", qos_profile=qos_profile)
        # Command topics (see docs/COMMUNICATION_SPEC.md)
        self.pub_estop = self.create_publisher(
            Bool, "/emergency_stop", qos_profile=qos_profile)
        self.pub_goal = self.create_publisher(
            PoseStamped, "/goal_pose", qos_profile=qos_profile)
        self.pub_cancel = self.create_publisher(
            Empty, "/cancel_goal", qos_profile=qos_profile)

    def update_joy(self):
        global msg, msg2, emergency_stop, pending_goal, pending_cancel
        stamp = self.get_clock().now().to_msg()

        # Fail-safe: if no fresh joy input has arrived over the WebSocket
        # within JOY_INPUT_TIMEOUT (disconnect / stall / browser closed),
        # neutralize the held command so stale non-zero input is never
        # published. /joy keeps publishing at the timer rate (neutral) so
        # downstream stays fed and is driven to a stop rather than runaway.
        if (time.monotonic() - last_joy_rx) > JOY_INPUT_TIMEOUT:
            for i in range(len(msg.axes)):
                msg.axes[i] = 0.0
            for i in range(len(msg.buttons)):
                msg.buttons[i] = 0
            for i in range(len(msg2.axes)):
                msg2.axes[i] = 0.0
            for i in range(len(msg2.buttons)):
                msg2.buttons[i] = 0

        msg.header.stamp = stamp
        self.pub.publish(msg)
        self.pub2.publish(msg2)

        # Emergency stop is broadcast every cycle so any subscriber always
        # knows the current state (fail-safe for late/dropped messages).
        estop_msg = Bool()
        estop_msg.data = emergency_stop
        self.pub_estop.publish(estop_msg)

        # Goal and cancel are edge-triggered: published once per request.
        if pending_goal is not None:
            goal = pending_goal
            pending_goal = None
            goal.header.stamp = stamp
            self.pub_goal.publish(goal)

        if pending_cancel:
            pending_cancel = False
            self.pub_cancel.publish(Empty())


def parse_args(argv=None):
    """Parse the node's own command line options (ROS args already removed)."""
    parser = argparse.ArgumentParser(
        prog="joy_node",
        description="joy_node_web ROS2 node. Serves the browser client as well "
                    "unless --no-client is given.")
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="address to bind (default: 0.0.0.0)")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_NODE_PORT,
        help="port for the WebSocket endpoint /joys, and for the client page "
             "when it is served (default: %d)" % DEFAULT_NODE_PORT)
    parser.add_argument(
        "--no-client", dest="serve_client", action="store_false",
        help="run the node only: do not serve the browser client at /joy")
    return parser.parse_args(argv)


def main(args=None):
    rclpy.init(args=args)
    # The node's own options come from the command line; ROS args
    # (--ros-args ...) are stripped first so argparse never sees them.
    cli = parse_args(remove_ros_args(args=sys.argv)[1:])

    # Client delivery is part of the same web server by default, so the
    # page and the /joys endpoint share one origin and the page needs no
    # configuration. With --no-client, only /joys is served and the client
    # is expected to come from elsewhere (see client_server).
    if cli.serve_client:
        add_client_routes(app)

    thread_web = threading.Thread(target=web_start, args=(cli.host, cli.port))
    thread_web.start()
    joy_node = JoyNodeWeb()
    if cli.serve_client:
        print("please open domain:%d/joy" % cli.port)
    else:
        print("node only (--no-client): websocket endpoint on :%d/joys" % cli.port)
    rclpy.spin(joy_node)


if __name__ == '__main__':
    main()
