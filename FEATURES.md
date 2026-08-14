# 機能一覧

## 測定モード

| モード | 実行場所 | Wi-Fi情報の取得方法 | 主な用途 |
| --- | --- | --- | --- |
| Windowsローカル | Windows PC | `netsh` | PC自身の無線状態を測定 |
| Jetsonローカル | Jetson | `nmcli` / `ping` | Jetsonを単体で測定 |
| Jetson SSHリモート | Windows PC | SSH経由でJetsonの `nmcli` / `ping` を実行 | PCからJetsonを操作・記録 |

## ダッシュボード

- ブラウザで測定開始・停止、ポイント進行・戻しを操作
- 測定中のPointクリックはロガーのPoint更新を再描画より優先し、更新中の重複クリックを防止
- 新しい測定開始時は前セッションのPoint座標・区間を自動クリア
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

## Jetson Wi-Fi接続 / SSID・BSSID固定

- 通常操作では、周辺Wi-Fi一覧からSSIDを指定して接続。未保存SSIDはパスワード入力が必要で、保存済みSSIDは入力不要
- SSID固定では、対象以外の保存済みWi-Fiプロファイルを`autoconnect=no`にして他SSIDへの自動接続を禁止
- SSID固定前の自動接続設定と優先度は`logs/ssid_lock_state.json`へ保存し、解除時に元の値へ復元
- 「測定中は対象SSID以外へ自動接続しない」がONの場合、測定開始時に自動固定し、停止時に自動復元
- 手動でSSID固定した場合は測定停止後も維持し、「SSID固定を解除・復元」で解除
- サーバー異常終了後もスナップショットが残るため、再起動後に解除・復元可能
- ローカルWi-Fi接続中は、測定の開始前または測定中に同一SSID内のBSSIDを指定可能
- BSSID切替時は、確実に再接続するため選択BSSIDを接続プロファイルへ固定。固定解除も可能
- 切替中は測定ループと `nmcli` 操作を排他し、ログの競合を防止
- SSID接続・SSID固定・BSSID切替・BSSID固定と各解除の結果を `*_events.csv` に記録
- ダッシュボードの確認ダイアログを通過した場合だけ実行
- USBまたは有線LAN経由でダッシュボードへ接続中にのみ使用すること。Wi-Fi経由で実行するとブラウザとの通信が切断されます。

## Wi-Fi自動再接続

- 測定対象SSIDから切断された場合、保存済みのNetworkManager接続プロファイルを使って再接続を試行
- 試行間隔はダッシュボードで設定でき、再接続の成功・失敗は `*_events.csv` に記録
- BSSID固定中は、切断中だけ周辺Wi-Fiを再スキャンし、固定先が見えた場合だけ固定済みプロファイルを再接続
- 固定先が見えない場合は長い接続待ちを行わず、次の試行間隔で再確認
- NetworkManagerがすでにスキャン中の場合は、再スキャンなしの候補キャッシュを確認して固定先を判定
- 再スキャン要求直後は最大3秒キャッシュをポーリングし、復帰直後の固定BSSIDを古いスキャン結果で見逃さない
- 同じSSIDへ復帰していても保存済みBSSID固定と一致するまで再接続成功として扱わない
- BSSID固定中は別BSSIDへ接続する汎用フォールバックを行わない
- Jetson SSHリモート測定でもJetson側で再接続を試行
- 未保存SSIDへはパスワードなしで接続できないため、事前にSSIDへ接続して接続情報を保存しておく
