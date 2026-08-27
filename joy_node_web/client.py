"""Browser client delivery for joy_node_web.

The web client is served from here so that it is independent of the ROS
node: the same routes are mounted by ``joy_node`` (default) and by the
standalone ``client_server`` executable, which needs no ROS installation.
"""

import json
import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# Port the ROS node serves its WebSocket endpoint (/joys) on.
DEFAULT_NODE_PORT = 8700
# Port the standalone client delivery server listens on. Deliberately not
# the node port, so both can run on one machine without colliding.
DEFAULT_CLIENT_PORT = 8701

CLIENT_HTML_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "client.html")

CFG_PLACEHOLDER = "{{SERVER_CFG}}"


def resolve_client_html_path():
    """Locate client.html next to this module, or in the package share dir.

    The file ships as package data, so the module-relative path covers both
    a plain and a --symlink-install colcon build. The share directory is a
    fallback for installs where the package data did not make it across;
    ament is imported lazily so a ROS-less client server still works.
    """
    if os.path.exists(CLIENT_HTML_PATH):
        return CLIENT_HTML_PATH
    try:
        from ament_index_python.packages import get_package_share_directory
        shared = os.path.join(
            get_package_share_directory("joy_node_web"), "static", "client.html")
    except Exception:
        return CLIENT_HTML_PATH
    return shared if os.path.exists(shared) else CLIENT_HTML_PATH


def render_client_html(ws_url=None, ws_port=None):
    """Return the client page with its server configuration injected.

    ``ws_url`` pins the WebSocket endpoint the page connects to.
    ``ws_port`` only pins the port, the host being the one the browser
    loaded the page from. With neither given, the page falls back to its
    own origin, which is what the node wants when it serves the page
    itself. The page is read per request so edits show up on reload.
    """
    with open(resolve_client_html_path(), encoding="utf-8") as f:
        html = f.read()
    cfg = {"ws_url": ws_url, "ws_port": ws_port}
    return html.replace(CFG_PLACEHOLDER, json.dumps(cfg))


def add_client_routes(app, ws_url=None, ws_port=None):
    """Mount the client delivery routes onto an existing FastAPI app."""

    @app.get("/joy")
    async def get_client():
        return HTMLResponse(render_client_html(ws_url=ws_url, ws_port=ws_port))

    return app


def create_client_app(ws_url=None, ws_port=None):
    """Build a FastAPI app that only delivers the client page."""
    app = FastAPI()
    add_client_routes(app, ws_url=ws_url, ws_port=ws_port)
    return app
