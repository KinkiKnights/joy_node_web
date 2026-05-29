# JoyNodeWeb
Webブラウザ上でゲームコントローラの操作をキャプチャし、`sensor_msgs::msg::Joy`としてPublishします。

ROS2 Humbleでのみ動作確認を行っています。

# 依存関係のインストール
```bash
sudo apt install python3-pip
pip install fastapi websockets "uvicorn[standard]"
```

pip installでエラーが出る場合はpyenv等仮想環境を使用してください。
```
python3 -m venv ~/venv/joy-node-web
source ~/venv/joy-node-web/bin/activate
pip install fastapi websockets "uvicorn[standard]"
```

# 起動
```
ros2 run joy_node_web joy_node
```
ノードの起動後、[http://ドメイン or IP:8700/joy](http://127.0.0.1:8700/joy)へアクセスするとコントローラの情報が`/joy`でPublishされます
コントローラのWebクライアントはCROSに違反しない範囲で自由に作成できます。# camera_joy
