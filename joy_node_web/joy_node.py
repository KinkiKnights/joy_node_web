import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile
from sensor_msgs.msg import Joy
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
import uvicorn
import threading


app = FastAPI()
msg = Joy()
msg2 = Joy()

HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JoyNodeWebClient</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #1e1e1e; color: #ccc; font-family: monospace; font-size: 14px; padding: 16px; }
    h1 { color: #58a6ff; font-size: 1.1em; margin-bottom: 12px; }

    .conn-panel {
      background: #2a2a2a; border: 1px solid #444;
      border-radius: 6px; padding: 12px; margin-bottom: 12px;
    }
    .conn-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .conn-row label { color: #888; font-size: 0.85em; white-space: nowrap; }
    .conn-row input {
      flex: 1; min-width: 220px;
      background: #111; border: 1px solid #444; border-radius: 4px;
      color: #ccc; font-family: monospace; font-size: 0.85em; padding: 5px 8px;
    }
    .conn-row input:focus { outline: none; border-color: #58a6ff; }
    .conn-row button {
      padding: 5px 12px; border-radius: 4px; border: 1px solid;
      cursor: pointer; font-family: monospace; font-size: 0.82em; background: transparent;
    }
    .btn-connect    { color: #3fb950; border-color: #3fb950; }
    .btn-disconnect { color: #f85149; border-color: #f85149; }
    .btn-connect:hover    { background: #1f4e23; }
    .btn-disconnect:hover { background: #3d1f1f; }
    .dot {
      width: 10px; height: 10px; border-radius: 50%;
      background: #555; flex-shrink: 0; transition: background 0.3s;
    }
    .dot.connected    { background: #3fb950; }
    .dot.connecting   { background: #d29922; }
    .dot.disconnected { background: #f85149; }

    .log {
      background: #111; border: 1px solid #333; border-radius: 4px;
      padding: 8px; height: 150px; overflow-y: auto;
      font-size: 0.78em; color: #888; margin-top: 10px;
    }
    .log .ts  { color: #484f58; margin-right: 6px; }
    .log .ok  { color: #3fb950; }
    .log .err { color: #f85149; }
    .log .inf { color: #58a6ff; }

    .gp-panel {
      background: #2a2a2a; border: 1px solid #444;
      border-radius: 6px; padding: 12px;
    }
    .gp-title { color: #888; font-size: 0.78em; margin-bottom: 8px; }
    .axes-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
      gap: 6px; margin-bottom: 8px;
    }
    .axis-item { font-size: 0.78em; }
    .axis-label { color: #555; }
    .axis-bar { height: 5px; background: #333; border-radius: 3px; overflow: hidden; margin-top: 2px; }
    .axis-fill { height: 100%; background: #58a6ff; width: 50%; transition: width 0.05s; }
    .btns { display: flex; flex-wrap: wrap; gap: 4px; }
    .btn-badge {
      width: 26px; height: 26px; border-radius: 4px;
      background: #333; border: 1px solid #444;
      display: flex; align-items: center; justify-content: center;
      font-size: 0.7em; color: #666; transition: background 0.05s;
    }
    .btn-badge.pressed { background: #58a6ff; color: #000; border-color: #58a6ff; }
  </style>
</head>
<body>
  <h1>&#9881; JoyNodeWebClient</h1>

  <div class="conn-panel">
    <div class="conn-row">
      <span class="dot" id="dot"></span>
      <label>WebSocket URL:</label>
      <input type="text" id="ws-url" placeholder="ws://hostname/joys">
      <button class="btn-connect"    onclick="doConnect()">Connect</button>
      <button class="btn-disconnect" onclick="doDisconnect()">Disconnect</button>
    </div>
    <div class="log" id="log"></div>
  </div>

  <div class="gp-panel">
    <div class="gp-title" id="gp-name">Gamepad: not connected</div>
    <div class="axes-grid" id="axes-grid"></div>
    <div class="btns"      id="btns-grid"></div>
  </div>

<script>
const uri_obj    = new URL(window.location.href);
const defaultUrl = 'ws://' + uri_obj.host + '/joys';

document.getElementById('ws-url').value = defaultUrl;

const pad_info = { id: 'unknown', buttons: [], axes: [] };
const status   = { pad_index: 0, pad_connect: false, ws: null, trying: false };

function log(msg, cls) {
  const el  = document.getElementById('log');
  const now = new Date().toTimeString().slice(0, 8);
  el.innerHTML += '<div><span class="ts">' + now + '</span><span class="' + (cls||'') + '">' + msg + '</span></div>';
  el.scrollTop = el.scrollHeight;
}

function setDot(state) {
  document.getElementById('dot').className = 'dot ' + state;
}

function doConnect() {
  if (status.ws && status.ws.readyState === WebSocket.OPEN) { log('Already connected','inf'); return; }
  const url = document.getElementById('ws-url').value.trim();
  if (!url) return;
  wsInit(url);
}

function doDisconnect() {
  if (status.ws) { status.ws.onclose = null; status.ws.close(); status.ws = null; }
  status.trying = false;
  setDot('disconnected');
  log('Disconnected by user','err');
}

function wsInit(url) {
  if (status.trying) return;
  status.trying = true;
  setDot('connecting');
  log('Connecting to ' + url + ' …','inf');
  const ws = new WebSocket(url);
  ws.onopen = () => {
    status.ws = ws; status.trying = false;
    setDot('connected'); log('Connected: ' + url,'ok');
  };
  ws.onclose = () => {
    status.ws = null; status.trying = false;
    setDot('disconnected'); log('Connection closed','err');
  };
  ws.onerror = () => { log('WebSocket error','err'); };
  ws.onmessage = (e) => {
    try { const d = JSON.parse(e.data); if (d.source==='can') updateDisplay(d.axes,d.buttons); } catch(_){}
  };
}

function retryWebsocket() {
  if (status.ws && status.ws.readyState === WebSocket.OPEN) return;
  if (status.trying) return;
  const url = document.getElementById('ws-url').value.trim();
  if (!url) return;
  log('Retrying …','inf'); wsInit(url);
}

window.addEventListener('gamepadconnected', (e) => {
  pad_info.id = e.gamepad.id; status.pad_index = e.gamepad.index; status.pad_connect = true;
  document.getElementById('gp-name').textContent = 'Gamepad: ' + pad_info.id;
  log('Gamepad connected: ' + pad_info.id,'ok');
});
window.addEventListener('gamepaddisconnected', (e) => {
  if (e.gamepad.index === status.pad_index) {
    status.pad_connect = false;
    document.getElementById('gp-name').textContent = 'Gamepad: disconnected';
    log('Gamepad disconnected','err');
  }
});

function updateGamepad() {
  if (!status.pad_connect) return;
  const gp = navigator.getGamepads()[status.pad_index];
  if (!gp) return;
  pad_info.axes    = Array.from(gp.axes);
  pad_info.buttons = gp.buttons.map(b => b.value);
  updateDisplay(pad_info.axes, pad_info.buttons);
  if (status.ws && status.ws.readyState === WebSocket.OPEN) {
    status.ws.send(JSON.stringify(pad_info));
  }
}

function updateDisplay(axes, buttons) {
  const ag = document.getElementById('axes-grid');
  if (ag.children.length !== axes.length) {
    ag.innerHTML = axes.map(function(_,i){
      return '<div class="axis-item"><div><span class="axis-label">axis['+i+']</span> <span id="av'+i+'">0.000</span></div>'
           + '<div class="axis-bar"><div class="axis-fill" id="ab'+i+'"></div></div></div>';
    }).join('');
  }
  axes.forEach(function(v,i){
    var el=document.getElementById('av'+i), br=document.getElementById('ab'+i);
    if(el) el.textContent=parseFloat(v).toFixed(3);
    if(br) br.style.width=((parseFloat(v)+1)*50)+'%';
  });
  const bg = document.getElementById('btns-grid');
  if (bg.children.length !== buttons.length) {
    bg.innerHTML = buttons.map(function(_,i){
      return '<div class="btn-badge" id="bb'+i+'">'+i+'</div>';
    }).join('');
  }
  buttons.forEach(function(v,i){
    var el=document.getElementById('bb'+i);
    if(el) el.className='btn-badge'+(v?' pressed':'');
  });
}

setInterval(updateGamepad,     50);
setInterval(retryWebsocket,  5000);
wsInit(defaultUrl);
</script>
</body>
</html>"""


@app.get("/joy")
async def get():
    return HTMLResponse(HTML)


@app.websocket("/joys")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    global msg, msg2
    while True:
        gamepad_info = await websocket.receive_json()
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


def web_start():
    print("boot webserver thread")
    uvicorn.run(app, host="0.0.0.0", port=8700)


def exchangeMapping(mapping):
    # comming soon
    return mapping


class JoyNodeWeb(Node):
    def __init__(self):
        super().__init__("joy_node_web")
        qos_profile = QoSProfile(depth=2)
        self.timer = self.create_timer(0.05, self.update_joy)
        self.pub  = self.create_publisher(Joy, "/joy",  qos_profile=qos_profile)
        self.pub2 = self.create_publisher(Joy, "/joy2", qos_profile=qos_profile)

    def update_joy(self):
        global msg, msg2
        msg.header.stamp = self.get_clock().now().to_msg()
        self.pub.publish(msg)
        self.pub2.publish(msg2)


def main(args=None):
    rclpy.init(args=args)
    thread_web = threading.Thread(target=web_start)
    thread_web.start()
    joy_node = JoyNodeWeb()
    print("please open domain:8700/joy")
    rclpy.spin(joy_node)


if __name__ == '__main__':
    main()
