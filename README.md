# JoyNodeWeb
Webブラウザ上でゲームコントローラの操作をキャプチャし、`sensor_msgs::msg::Joy`としてPublishします。

ROS2 Humbleでのみ動作確認を行っています。

# 依存関係のインストール
```bash
sudo apt install python3-pip
pip3 install fastapi
pip3 install websockets
pip3 install "uvicorn[standard]"
```

# 起動
```
ros2 run joy_node_web joy_node
```
ノードの起動後、[http://127.0.0.1:8700/joy](http://127.0.0.1:8700/joy)へアクセスするとコントローラの情報が`/joy`でPublishされます
