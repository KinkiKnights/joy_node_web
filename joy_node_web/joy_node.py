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
@app.get("/joy")
async def get():
    htm = """
    <!DOCTYPE html>
<html lang="JP">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JoyNodeWebClient</title>
    <style>
        body{
            background-color: #353333;
            color: #eee;
            font-weight: bold;
            font-size: 18px;
        }
    </style>
</head>
<body></body>
<script>
const pad_info = {
    id:"unknown",
    buttons:[],
    axes:[],
};
const status = {
    pad_index :0,
    pad_connect: false,
    node_connect: false,
};

function updateGamepad(){
    if (!status.pad_connect)
        return;
    const gp = navigator.getGamepads()[status.pad_index];
    pad_info.axes = gp.axes;
    pad_info.buttons = [];
    for(let i = 0; i < gp.buttons.length;i++){
        pad_info.buttons.push(gp.buttons[i].value);
    }
    
    if (!status.node_connect)
        return;
    status.ws.send(JSON.stringify(pad_info));
}

window.addEventListener("gamepadconnected", (e)=>{
    console.log("Connect new GamePad", e.gamepad.id);
    pad_info.id = e.gamepad.id;
    status.pad_index = e.gamepad.index;
    status.pad_connect = true;
    document.body.innerHTML += "Connect Gamepad "+ pad_info.id +"<br>";
});

window.addEventListener("gamepaddisconnected", (e)=>{
    if (e.gamepad == status.pad)
        status.pad_connect = false;
        document.body.innerHTML += "Disconnect Gamepad "+ pad_info.id +"<br>";
    });

function webSocketInit(){
    const ws = new WebSocket("ws://127.0.0.1:8700/joy");
    ws.onopen = ()=>{
        status.node_connect = true;
        status.ws = ws;
        document.body.innerHTML += "Open ws://127.0.0.1:8700/joy<br>";
    };
    ws.onclose = ()=>{
        status.node_connect = false;
        document.body.innerHTML += "Close ws://127.0.0.1:8700/joy<br>";
        status.trying = false;
    }
    ws.onerror = (err) =>{
        console.log("Websocket error!! ", err);
        document.body.innerHTML += "Error ws://127.0.0.1:8700/joy<br>";
    }
    status.trying = true;
}

function retryWebsocket(){
    if (status.node_connect || status.trying)
        return;
    webSocketInit();
    document.body.innerHTML += "Retrying ws://127.0.0.1:8700/joy<br>";

}

setInterval(updateGamepad,50);
setInterval(retryWebsocket,5000);
webSocketInit();
</script>
</html>
    
    """
    return HTMLResponse(htm)
    
@app.websocket("/joy")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    global msg
    while True:
        gamepad_info = await websocket.receive_json()

        for i in range(len(gamepad_info["axes"])):
            if (len(msg.axes) <= i):
                msg.axes.append(gamepad_info["axes"][i])
            else:
                msg.axes[i] = gamepad_info["axes"][i]

        for i in range(len(gamepad_info["buttons"])):
            if (len(msg.buttons) <= i):
                msg.buttons.append(int(gamepad_info["buttons"][i]))
            else:
                msg.buttons[i] = int(gamepad_info["buttons"][i])
        
def web_start():
    print("boot webserver thread")
    uvicorn.run(app, host="127.0.0.1", port=8700)

def exchangeMapping(mapping):
    # comming soon
    return mapping

class JoyNodeWeb(Node):
    def __init__(self):
        super().__init__("joy_node_web")
        qos_profile = QoSProfile(depth=10)
        self.timer = self.create_timer(0.05, self.update_joy)
        self.pub = self.create_publisher(Joy, "/joy", qos_profile=qos_profile)
    
    def update_joy(self):
        global msg;
        msg.header.stamp = self.get_clock().now().to_msg()
        self.pub.publish(msg)

def main(args = None):
    rclpy.init(args=args)
    thread_web = threading.Thread(target=web_start)
    thread_web.start()
    joy_node = JoyNodeWeb()
    print("please open http://127.0.0.1:8700/joy")
    rclpy.spin(joy_node)

if __name__ == '__main__':
    main()
