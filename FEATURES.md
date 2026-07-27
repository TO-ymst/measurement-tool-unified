# 機能一覧

## 測定モード

| モード | 実行場所 | Wi-Fi情報の取得方法 | 主な用途 |
| --- | --- | --- | --- |
| Windowsローカル | Windows PC | `netsh` | PC自身の無線状態を測定 |
| Jetsonローカル | Jetson | `nmcli` / `ping` | Jetsonを単体で測定 |
| Jetson SSHリモート | Windows PC | SSH経由でJetsonの `nmcli` / `ping` を実行 | PCからJetsonを操作・記録 |

## ダッシュボード

- ブラウザで測定開始・停止、ポイント進行・戻しを操作
- 接続中SSID、BSSID、チャネル、通信レート、RSSI、Pingをリアルタイム表示
- 背景マップ上への測定ポイント配置、プロット、表示倍率・色・凡例の調整
- PCログCSVとJetsonログCSVの読込・時間合わせ・重ね合わせ
- Ping、RSSI、BSSID、Best Neighbor RSSI、Best Neighbor BSSIDの表示
- 現在のプロット、または全モードのレジェンド付きPNG書出し

## ネイバーAP測定

- 指定間隔で周辺APをスキャン
- 接続中AP以外の同一SSID候補から、最良ネイバーAPを選定
- 最良ネイバーのBSSID、チャネル、通信レート、RSSI、現在APとの信号差をメインCSVへ記録
- 全ネイバーAPの詳細を `*_neighbors.csv` へ別途記録
- Jetson SSHリモートとJetsonローカルで同じネイバーCSV形式を出力
- Windowsローカルでは `netsh` の結果からネイバー一覧を取得

## 出力ファイル

| ファイル | 内容 |
| --- | --- |
| `*.csv` | ポイント、接続AP、Ping、最良ネイバーを含む測定ログ |
| `*_neighbors.csv` | スキャン時に見つかった全ネイバーAPの詳細 |
| `*_events.csv` | JetsonローカルのBSSID切替イベント、接続結果、接続後BSSIDを記録 |
| `*_remote_advanced_*.jsonl` | SSHリモート測定中の障害解析ログ。有効化時のみ出力 |
| `*.png` | ダッシュボードで書き出したプロット画像 |

## SSHリモートの障害解析

SSHリモート測定では、必要に応じて次のタイミングで追加のJSONLログを採取できます。

- BSSIDが切り替わった時
- Pingタイムアウトが指定回数連続した時
- SSH接続やネイバースキャンが失敗した時

採取項目は `ip neigh`、`ip route`、`ip addr`、Wi-Fi詳細、`journalctl` から選択できます。

## 導入と起動

- Windows: `install_windows.bat` を一度実行し、`start_windows.bat` で起動
- Jetson: `install_jetson.sh` を一度実行し、`start_jetson.sh` で起動
- Jetson自動起動: `install_service_jetson.sh`

## Jetson AP切替 / BSSIDテスト

- 通常操作では、周辺AP一覧からSSIDだけを指定して接続先を切替。未保存APはパスワード入力で接続し、保存済みAPはパスワード不要
- AP固定では、選択SSIDの接続プロファイルを自動接続の最優先に設定。固定解除では優先度を通常値へ戻す
- AP切替に成功したSSIDに限り、ローカル測定中だけ同一SSID内のBSSID切替を有効化
- BSSID切替後は、現在の接続プロファイルへBSSIDを固定でき、固定解除も可能
- 切替中は測定ループと `nmcli` 操作を排他し、ログの競合を防止
- AP切替・AP固定・BSSID切替・BSSID固定と各解除の結果を `*_events.csv` に記録
- ダッシュボードの確認チェックと確認ダイアログを通過した場合だけ実行
- USBまたは有線LAN経由でダッシュボードへ接続中にのみ使用すること。Wi-Fi経由で実行するとブラウザとの通信が切断されます。
