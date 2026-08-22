# joy_node_web 通信仕様

Webブラウザ ⇄ ROS2 ノード間の通信仕様と、ノードが Publish する ROS2 トピックの仕様をまとめる。

- 動作確認: ROS2 **Humble**
- Web サーバ: FastAPI + uvicorn（ノード: `0.0.0.0:8700` / クライアント配信単体: `0.0.0.0:8701`）
- ノード名: `joy_node_web`
- Publish 周期: **100 Hz**（10 ms タイマ）

---

## 1. 全体構成

```
[クライアント配信]  GET /joy          … static/client.html を配信（ROS 非依存）
        │  ノード同梱（既定・同一ポート） or client_server 単体
        ▼
[ブラウザ / 任意の WebSocket クライアント]
        │  ws://<host>:8700/joys
        │  ・ジョイスティックデータ（既存）
        │  ・コマンド                ← どちらも同一の WebSocket 接続
        ▼
[FastAPI WebSocket エンドポイント /joys]
        │  受信 JSON を共有状態へ反映
        ▼
[JoyNodeWeb ノード]  100Hz タイマで Publish
        ├─ /joy            sensor_msgs/Joy      （既存）
        ├─ /joy2           sensor_msgs/Joy      （既存）
        ├─ /emergency_stop std_msgs/Bool        （常時配信）
        ├─ /goal_pose      geometry_msgs/PoseStamped （都度配信）
        └─ /cancel_goal    std_msgs/Empty       （都度配信）
```

- クライアント配信（`GET /joy`）とノード（`/joys` + Publish）は分離されており、単体でも起動できる。起動方法は [README](../README.md#起動) を参照。
  - `ros2 run joy_node_web joy_node` … ノード + 配信（既定）。同一オリジンになるため接続先設定は不要
  - `ros2 run joy_node_web joy_node --no-client` … ノード単体（`/joy` は 404）
  - `ros2 run joy_node_web client_server` … 配信単体（`:8701`。ROS2 環境不要）
- 配信を分離した場合、ページが接続する `/joys` の場所は配信サーバが注入する（`--ws-url` / `--ws-port`）か、`?ws=` で指定する。
- コマンドは **ジョイスティックデータと同じ WebSocket 接続（`/joys`）** を使って送信する。新たな接続は不要。

---

## 2. WebSocket メッセージ仕様（クライアント → サーバ）

エンドポイント: `ws://<host>:8700/joys`（JSON テキストフレーム）

受信メッセージは **`command` フィールドの有無**で 2 種類に分岐する。

| メッセージ種別 | 判定条件 | 処理 |
|---|---|---|
| ジョイスティックデータ（既存） | `command` フィールドが無い | `/joy`・`/joy2` へ反映 |
| コマンド（追加） | `command` フィールドがある | 対応するトピックへ反映 |

> **後方互換性**: 既存クライアントは `{id, axes, buttons}`（＋任意の `type`）を送信し、`command` フィールドを含まない。したがって既存クライアントの挙動は一切変わらない。

### 2.1 ジョイスティックデータ（既存・変更なし）

```jsonc
{
  "id": "Xbox Controller (STANDARD GAMEPAD ...)",  // 表示用・任意
  "axes":    [0.0, 0.0, 0.0, 0.0],                 // number[]
  "buttons": [0, 0, 1, 0, ...],                    // number[]（0/1 または 0.0-1.0）
  "type": 1                                         // 任意。1 のとき /joy2 へ、それ以外/無しは /joy へ
}
```

- `axes` は `Joy.axes`（float）へ、`buttons` は `Joy.buttons`（int）へ格納される。
- `type == 1` の場合のみ `/joy2` に振り分けられ、それ以外（未指定を含む）は `/joy`。

### 2.2 コマンド（追加）

いずれも `command` フィールドで種別を指定する。

#### 非常停止

```json
{ "command": "emergency_stop" }
```

#### 非常停止の解除

```json
{ "command": "emergency_release" }
```

#### 自動ゴールの設定

```json
{ "command": "set_goal", "x": 1.5, "y": 0.8, "yaw": 1.57, "frame_id": "map" }
```

| フィールド | 型 | 既定値 | 説明 |
|---|---|---|---|
| `x` | number | `0.0` | ゴール位置 X [m] |
| `y` | number | `0.0` | ゴール位置 Y [m] |
| `yaw` | number | `0.0` | ゴール姿勢（Z 軸まわり回転）[rad]。反時計回りが正 |
| `frame_id` | string | `"map"` | 座標フレーム |

- `yaw` は内部で四元数へ変換される（`z = sin(yaw/2)`, `w = cos(yaw/2)`, `x = y = 0`）。
- `position.z` は常に `0.0`（平面移動）。

#### ゴールのキャンセル

```json
{ "command": "cancel_goal" }
```

> 未知の `command` は無視される（既存動作に影響なし）。

---

## 3. ROS2 トピック仕様（ノード → 他ノード）

| トピック | 型 | 配信方式 | QoS | 説明 |
|---|---|---|---|---|
| `/joy` | `sensor_msgs/Joy` | 常時 100Hz | depth=2 | コントローラ 1（既存） |
| `/joy2` | `sensor_msgs/Joy` | 常時 100Hz | depth=2 | コントローラ 2（既存, `type==1`） |
| `/emergency_stop` | `std_msgs/Bool` | 常時 100Hz | depth=2 | 非常停止状態。`true`=停止中 / `false`=解除中 |
| `/goal_pose` | `geometry_msgs/PoseStamped` | コマンド受信時のみ 1 回 | depth=2 | 自動ゴール座標 |
| `/cancel_goal` | `std_msgs/Empty` | コマンド受信時のみ 1 回 | depth=2 | ゴールのキャンセル指示 |

### 3.1 `/emergency_stop`（std_msgs/Bool）

- **常時配信（100Hz）**。フェイルセーフのため、状態を毎周期ブロードキャストする。1 メッセージを取りこぼしても受信側は現在状態を把握できる。
- `data = true`: 非常停止中 / `data = false`: 解除中。
- 初期状態は `false`（解除）。

### 3.2 `/goal_pose`（geometry_msgs/PoseStamped）

`set_goal` コマンド受信時に 1 回だけ配信（エッジトリガ）。

```
PoseStamped
├─ header
│   ├─ stamp     … 配信時刻（ノードが付与）
│   └─ frame_id  … 既定 "map"
└─ pose
    ├─ position
    │   ├─ x     … コマンドの x
    │   ├─ y     … コマンドの y
    │   └─ z     … 0.0 固定
    └─ orientation   … yaw から生成した四元数
        ├─ x = 0.0
        ├─ y = 0.0
        ├─ z = sin(yaw/2)
        └─ w = cos(yaw/2)
```

### 3.3 `/cancel_goal`（std_msgs/Empty）

- `cancel_goal` コマンド受信時に 1 回だけ配信（エッジトリガ）。中身を持たないトリガー信号。

---

## 4. 座標系・フィールドの取り決め

`/goal_pose` の `x`, `y`, `yaw` は `frame_id`（既定 `map`）の座標系で解釈する。フィールドは 2 種類あり、原点と軸の向きが異なる。

### 青フィールド
- 原点 O(0, 0): 左上コーナー（スタート地点）
- X 軸: 下向きが正
- Y 軸: 右向きが正

### 赤フィールド
- 原点 O(0, 0): 右上コーナー（スタート地点）
- X 軸: 下向きが正
- Y 軸: 左向きが正

> 青／赤は点対称の関係（原点が対角、Y 軸の向きが左右反転）。

### 回転（Yaw）
- Z 軸まわりの回転（yaw）。
- **反時計回り（左回り）が正**。

> どちらのフィールドを基準に `map` フレームを取るか（あるいは変換を挟むか）は運用側で確定すること。

---

## 5. 後方互換性

- WebSocket エンドポイント（`/joys`）・ポート（`8700`）・既存トピック（`/joy`, `/joy2`）・既存メッセージ形式は**すべて変更なし**。
- クライアント配信の分離後も、オプションを付けずに `ros2 run joy_node_web joy_node` を起動すれば `http://<host>:8700/joy` で従来通りクライアントが得られる。分離は `--no-client` を指定したときだけ起こる。
- コマンドは `command` フィールドの有無で判別するため、既存クライアントの送信データ（`command` を含まない）は従来通り `/joy`・`/joy2` として処理される。
- 追加トピック（`/emergency_stop`, `/goal_pose`, `/cancel_goal`）は新規で、既存の購読者には影響しない。

---

## 6. 動作確認例

```bash
ros2 run joy_node_web joy_node
# 別端末で購読確認
ros2 topic echo /emergency_stop
ros2 topic echo /goal_pose
ros2 topic echo /cancel_goal
```

ブラウザで `http://<host>:8700/joy` を開き、「非常停止 / 解除 / ゴール送信 / キャンセル」ボタンを操作すると、上記トピックに反映される。

分離構成の確認例:

```bash
# 端末1: ノード単体
ros2 run joy_node_web joy_node --no-client
# 端末2: クライアント配信単体（ノードと同じホストの 8700 を指す）
ros2 run joy_node_web client_server --ws-port 8700
```

ブラウザで `http://<host>:8701/joy` を開くと、接続先欄が `ws://<host>:8700/joys` になり接続される。
