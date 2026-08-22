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
        │  ・ジョイスティックデータ（JSON テキストフレーム）
        ▼
[FastAPI WebSocket エンドポイント /joys]
        │  受信 JSON を共有状態へ反映
        ▼
[JoyNodeWeb ノード]  100Hz タイマで Publish
        ├─ /joy            sensor_msgs/Joy
        └─ /joy2           sensor_msgs/Joy   （`type == 1` のとき）
```

- クライアント配信（`GET /joy`）とノード（`/joys` + Publish）は分離されており、単体でも起動できる。起動方法は [README](../README.md#起動) を参照。
  - `ros2 run joy_node_web joy_node` … ノード + 配信（既定）。同一オリジンになるため接続先設定は不要
  - `ros2 run joy_node_web joy_node --no-client` … ノード単体（`/joy` は 404）
  - `ros2 run joy_node_web client_server` … 配信単体（`:8701`。ROS2 環境不要）
- 配信を分離した場合、ページが接続する `/joys` の場所は配信サーバが注入する（`--ws-url` / `--ws-port`）か、`?ws=` で指定する。

---

## 2. WebSocket メッセージ仕様（クライアント → サーバ）

エンドポイント: `ws://<host>:8700/joys`（JSON テキストフレーム）

```jsonc
{
  "id": "Xbox Controller (STANDARD GAMEPAD ...)",  // 表示用・任意
  "axes":    [0.0, 0.0, 0.0, 0.0],                 // number[]
  "buttons": [0, 0, 1, 0],                         // number[]（0/1 または 0.0-1.0）
  "type": 1                                        // 任意。1 のとき /joy2 へ、それ以外/無しは /joy へ
}
```

- `axes` は `Joy.axes`（float）へ、`buttons` は `Joy.buttons`（int）へ格納される。
- `buttons` は **整数へ切り捨て**られる。アナログ値（トリガ等）をボタンスロットに割り当てた場合、`1.0` に達しない限り `0` になる。
- `type == 1` の場合のみ `/joy2` に振り分けられ、それ以外（未指定を含む）は `/joy`。
- 配列長は可変。受信した要素数だけ `Joy` メッセージが伸長される。

サーバ → クライアントの送信は行わない（クライアント側は `source == "can"` のメッセージを表示に反映する実装のみ持つ）。

---

## 3. ROS2 トピック仕様（ノード → 他ノード）

| トピック | 型 | 配信方式 | QoS | 説明 |
|---|---|---|---|---|
| `/joy` | `sensor_msgs/Joy` | 常時 100Hz | depth=2 | コントローラ 1 |
| `/joy2` | `sensor_msgs/Joy` | 常時 100Hz | depth=2 | コントローラ 2（`type == 1`） |

- `header.stamp` は配信時刻をノードが付与する。
- 入力が **0.5 秒**（`JOY_INPUT_TIMEOUT`）途絶えた場合、保持値をゼロ化した中立値を配信し続ける（WebSocket 断絶時の暴走防止）。配信自体は止めない。

---

## 4. キーマップ仕様（g2e 互換）

ブラウザクライアントのキーマップは [g2e (ESP-NOW Gamepad Bridge)](https://g2e.s-phere.dev) とファイル形式・解釈を揃えてあり、双方で相互に読み込める。

### 4.1 ファイル形式

```jsonc
{
  "version": 1,
  "gamepadId": "Xbox Controller (STANDARD GAMEPAD ...)",
  "mapping": {
    "stick_l_x": { "kind": "axis", "index": 0 },
    "stick_l_y": { "kind": "axis", "index": 1, "invert": true, "deadzone": 0.1 },
    "face_down": { "kind": "button", "index": 0 },
    "trigger_r": { "kind": "axis_trigger", "index": 5, "rest": -1, "full": 1 },
    "select":    { "kind": "axis_dir", "index": 9, "positive": true, "threshold": 0.5 }
  },
  "exportedAt": "2026-08-22T09:00:00.000Z"
}
```

- 読み込み時に必要なのは `mapping` のみ。`gamepadId` は文字列であれば採用し、それ以外は空文字。`version` / `exportedAt` は読み飛ばす。
- 保存ファイル名は `gamepad-mapping-<gamepadId>.json`（英数・`_`・`-` 以外は `_` に置換、60文字まで）。
- 未知のスロット名、および検証を通らないバインドは**破棄**される（読み込み自体は成功する）。

### 4.2 スロット名

| 種別 | スロット |
|---|---|
| ボタン | `face_down` `face_right` `face_left` `face_up` `shoulder_l` `shoulder_r` `trigger_l` `trigger_r` `select` `start` `home` `stick_l_click` `stick_r_click` `dpad_up` `dpad_down` `dpad_left` `dpad_right` |
| 軸 | `stick_l_x` `stick_l_y` `stick_r_x` `stick_r_y` |

標準割り当て（W3C standard gamepad）は
`face_down`=btn0, `face_right`=btn1, `face_left`=btn2, `face_up`=btn3,
`shoulder_l`=btn4, `shoulder_r`=btn5, `trigger_l`=btn6, `trigger_r`=btn7,
`select`=btn8, `start`=btn9, `stick_l_click`=btn10, `stick_r_click`=btn11,
`dpad_up`=btn12, `dpad_down`=btn13, `dpad_left`=btn14, `dpad_right`=btn15, `home`=btn16,
`stick_l_x`=axis0, `stick_l_y`=axis1, `stick_r_x`=axis2, `stick_r_y`=axis3。

### 4.3 バインドの種別と解釈

| `kind` | 必須フィールド | 任意フィールド | 出力値 |
|---|---|---|---|
| `button` | `index` | - | `buttons[index]`（0.0-1.0） |
| `axis` | `index` | `invert`(bool) / `deadzone`(number) | `axes[index]`。`\|v\| < deadzone` で 0、`invert` で符号反転 |
| `axis_trigger` | `index` `rest` `full` | - | `clamp01((v - rest) / (full - rest))`。`full == rest` なら 0 |
| `axis_dir` | `index` `positive` `threshold` | - | `r = positive ? v : -v`。`r < threshold` で 0、以降 `min(1, (r - threshold) / (1 - threshold))` |

- `index` は 0 以上の整数のみ有効。`threshold` は `[0, 0.99]` にクランプされる。
- 未割り当てスロットの出力は 0。
- キーマップ未設定（「キーマップ解除」状態）のときは、ゲームパッドの生データをそのまま送信する。

### 4.4 バインド操作

クライアント画面の「設定変更」で開くモーダル内で操作する。

- 「順に割り当て」: スロット表示順（下表の順）に先頭から点滅し、対応する入力を操作するとバインドして次のスロットへ進む。スキップ・中断が可能。
- 個別バインド: スロットをクリックして待受状態にし、割り当てたい入力を操作する。
- 「インポート」で JSON 読み込み、「リセット」で割り当て解除（生データ送信に戻る）。

入力の判定は g2e と同じ:

| 対象スロット | 判定 |
|---|---|
| `trigger_l` / `trigger_r` | ボタンが 0.3 未満→0.3 以上に変化 → `button`。無ければバインド開始時の値から 0.4 以上動いた軸 → `axis_trigger`（`rest` = 開始時の値、`full` = 増加方向なら 1、減少方向なら -1） |
| その他のボタンスロット | ボタン押下 → `button`。無ければ絶対値 0.3 未満→0.3 以上に動いた軸 → `axis_dir`（`positive` は符号、`threshold` = 0.5） |
| 軸スロット | 絶対値 0.3 未満→0.3 以上に動いた軸 → `axis` |

---

## 5. 座標系・フィールドの取り決め

`/joy`・`/joy2` の内容はコントローラ入力そのものであり、座標系の解釈は購読側（走行制御・自律側）に委ねる。

---

## 6. 後方互換性

- WebSocket エンドポイント（`/joys`）・ポート（`8700`）・トピック（`/joy`, `/joy2`）・メッセージ形式は**変更なし**。
- クライアント配信を分離しても、オプションを付けずに `ros2 run joy_node_web joy_node` を起動すれば `http://<host>:8700/joy` で従来通りクライアントが得られる。分離は `--no-client` を指定したときだけ起こる。
- キーマップファイルは従来の `{gamepadId, mapping}` 形式をそのまま読み込める（`kind: button` / `kind: axis` は同じ意味）。ただし従来の「軸をボタンスロットに割り当てたときに `(v+1)/2` を返す」挙動は廃止し、g2e と同じ `axis_dir` / `axis_trigger` の解釈に変更した。

### 削除された機能

以下は削除済みで、トピックの Publish も WebSocket コマンドの受理も行わない。

- 非常停止・解除（`/emergency_stop`）
- 自動ゴール設定（`/goal_pose`、XY/Yaw 入力）
- ゴールのキャンセル（`/cancel_goal`）

---

## 7. 動作確認例

```bash
ros2 run joy_node_web joy_node
# 別端末で購読確認
ros2 topic echo /joy
ros2 topic hz /joy
```

ブラウザで `http://<host>:8700/joy` を開き、ゲームパッドを操作すると `/joy` に反映される。

分離構成の確認例:

```bash
# 端末1: ノード単体
ros2 run joy_node_web joy_node --no-client
# 端末2: クライアント配信単体（ノードと同じホストの 8700 を指す）
ros2 run joy_node_web client_server --ws-port 8700
```

ブラウザで `http://<host>:8701/joy` を開くと、ヘッダー右側の接続先が `ws://<host>:8700/joys` になり接続される。
