# joy_node_web 通信仕様

Webブラウザ ⇄ ROS2 ノード間の通信仕様と、ノードが Publish する ROS2 トピックの仕様をまとめる。

- 動作確認: ROS2 **Humble**
- Web サーバ: FastAPI + uvicorn（ノード: `0.0.0.0:8700` / クライアント配信単体: `0.0.0.0:8701`）
- ノード名: `joy_node_web`
- Publish 周期: **100 Hz**（10 ms タイマ）

---

## 1. 全体構成

```
[クライアント配信]  GET /joy          … static/client.html を配信（PC・ゲームパッド）
                    GET /joysp        … static/client_sp.html を配信（スマホ・タッチ）
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

- どちらのページも同じ `/joys` へ、同じメッセージ形式（2章）で送信する。受信側から見た違いは無い。
- クライアント配信（`GET /joy` / `GET /joysp`）とノード（`/joys` + Publish）は分離されており、単体でも起動できる。起動方法は [README](../README.md#起動) を参照。
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

### 2.1 スマホ版クライアント (`/joysp`) の割り当て

スマホ版はキーマップを持たず、画面のコントロールから **固定の割り当て** で `axes` / `buttons` を組み立てる。**配列長は `axes` 4 / `buttons` 16**（並びは W3C standard gamepad と同じ）で、使わないスロットは 0。ノードは配列長を可変に扱うため、PC 版（`buttons` 17）と同じパーサでそのまま処理できる。

| コントロール | 送信先 | 値 |
|---|---|---|
| スティック 左右 | `axes[0]` (`stick_l_x`) | -1.0（左）〜 +1.0（右） |
| スティック 上下 | `axes[1]` (`stick_l_y`) | -1.0（上）〜 +1.0（下）※W3C Gamepad API と同じ符号 |
| 左旋回 | `buttons[5]` (`shoulder_r`) | 押下 1 / 離すと 0 |
| 右旋回 | `buttons[4]` (`shoulder_l`) | 押下 1 / 離すと 0 |
| 上 | `buttons[3]` (`face_up`) | 押下 1 / 離すと 0 |
| 下 | `buttons[0]` (`face_down`) | 押下 1 / 離すと 0 |

- `axes[2]` / `axes[3]` は使用せず常に 0。

- スティックは移動量を円内にクランプし、`|(x, y)| <= 1.0` に正規化する。半径方向の不感帯（既定 0.05）を超えた分を 0〜1 に引き伸ばす。指を離すと中央（0, 0）へ戻る。
- ページが非表示になる（アプリ切り替え・画面ロック）と全コントロールを中立へ戻す。
- 送信周期・接続先の決定順・接続タイムアウト（5 秒）・自動再接続は PC 版と同一。複数台モード（`?num=`）は持たない。
- 割り当ては `static/client_sp.html` 冒頭の `MAP` 定数のみで決まる。実機側の割り当てに合わせる場合はここを変更する。

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
| `button_axis` | `index` `rest` `full` | `invert`(bool) | `clamp(-1..1, (buttons[index] - rest) / (full - rest))`。`full == rest` なら 0 |
| `button_pair` | `plus` `minus`（各 `{index, rest, full}`） | `invert`(bool) | `clamp01(plus) - clamp01(minus)`（各辺を自分の `rest`→`full` で 0-1 正規化） |

- `button_axis` / `button_pair` は **軸をボタンとして報告するブラウザ向け**（Ubuntu の Chrome で確認）。ボタンのアナログ値（0.0-1.0）から軸値（-1.0-1.0）を作る。
  - `button_axis`: 1つのボタンが軸の全域を持つ場合（静止値が中央付近）。片方向のみの確定にも使う（`rest` が端の場合、出力は 0-1）。
  - `button_pair`: 1軸が方向ごとに2ボタンへ分かれている場合。
  - この2種別は g2e には無いため、これらを含むファイルは g2e 側では読めない（`button` / `axis` / `axis_trigger` / `axis_dir` のみのファイルは従来どおり相互利用可）。
- `index` は 0 以上の整数のみ有効。`threshold` は `[0, 0.99]` にクランプされる。
- 未割り当てスロットの出力は 0。
- キーマップ未設定（「キーマップ解除」状態）のときは、ゲームパッドの生データをそのまま送信する。

### 4.4 バインド操作

クライアント画面の「設定変更」で開くモーダル内で操作する。

- 「割当開始」: スロット表示順（下表の順）に先頭から点滅し、対応する入力を操作するとバインドして次のスロットへ進む。スキップ・中断が可能。
- 個別バインド: スロットをクリックして待受状態にし、割り当てたい入力を操作する。
- 軸スロット（`stick_*_x` / `stick_*_y`）の判定順は「実軸 → ボタン」。ボタンが動いた場合:
  - 待受開始時の静止値が中央付近（0.25-0.75）なら、その1ボタンで全域とみなし `button_axis` を確定。
  - 静止値が端なら片方向として保持し、バナーが「— 反対方向」表示に変わる。別のボタンが動けば `button_pair`、「片方向で確定」を押せばその方向だけの `button_axis` になる。
- 「インポート」で JSON 読み込み、「クリア」で割り当て解除（生データ送信に戻る）。

### 4.5 複数台接続時の独立性

`?num=N` で N 枚のカードを表示した場合、各カードは独立した WebSocket 接続・コントローラ選択・キーマップ・表示状態を持つ。カード間で共有されるのは以下のみ。

| 共有されるもの | 理由 |
|---|---|
| キーマップ保存領域 (`localStorage["joy_keymaps"]`) | キーマップはコントローラ名に紐付くため（カードに紐付かない） |
| Gamepad API のフレーム | 1周期に1回だけ読み、各カードへ同じスナップショットを渡す（各カードは読むだけ） |

- 既定の選択は「カード #n → n 番目に検出されたコントローラ」。同一コントローラを複数カードから送ることも手動選択で可能。
- あるカードでキーマップを変更しても、同じコントローラを選んでいる別カードの適用中キーマップは即時には変わらない（次にそのカードでコントローラを選び直した時点で保存内容が反映される）。

### 4.6 保存と自動適用

キーマップはブラウザの localStorage に **コントローラ名（`Gamepad.id`）をキーとした辞書** で保存される。

```jsonc
// localStorage["joy_keymaps"]
{
  "Xbox Controller (STANDARD GAMEPAD ...)": { /* 4.1 のファイル形式と同一 */ },
  "8BitDo Pro 2 (Vendor: ...)":            { /* … */ }
}
```

- コントローラを選択した時点で、その名前のエントリがあれば自動適用する。無ければ生データ送信に戻る。
- 割り当ての変更・インポートは、選択中コントローラ名のエントリとして保存される（インポートしたファイルの `gamepadId` が別名でも、使用中のコントローラに紐付け直す）。
- 「クリア」は選択中コントローラのエントリを削除する。

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
