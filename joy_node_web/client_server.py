"""Standalone browser client delivery server (no ROS dependency).

Serves only the web client. The ROS node is reached over its own
WebSocket endpoint, whose location is handed to the page with
``--ws-url`` / ``--ws-port``.
"""

import argparse

import uvicorn

from joy_node_web.client import (
    DEFAULT_CLIENT_PORT,
    DEFAULT_NODE_PORT,
    create_client_app,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="client_server",
        description="Serve the joy_node_web browser client only.")
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="address to bind (default: 0.0.0.0)")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_CLIENT_PORT,
        help="port to serve the client on (default: %d)" % DEFAULT_CLIENT_PORT)
    parser.add_argument(
        "--ws-url", default=None,
        help="full WebSocket URL of the node, e.g. ws://192.168.10.135:8700/joys. "
             "Overrides --ws-port.")
    parser.add_argument(
        "--ws-port", type=int, default=DEFAULT_NODE_PORT,
        help="node WebSocket port, on the host the page was loaded from "
             "(default: %d)" % DEFAULT_NODE_PORT)
    return parser.parse_args(argv)


def main(args=None):
    cli = parse_args(args)
    app = create_client_app(ws_url=cli.ws_url, ws_port=cli.ws_port)
    print("serving web client on http://%s:%d/joy" % (cli.host, cli.port))
    print("client will connect to %s" % (cli.ws_url or "ws://<this host>:%d/joys" % cli.ws_port))
    uvicorn.run(app, host=cli.host, port=cli.port)


if __name__ == "__main__":
    main()
