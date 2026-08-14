# iwリンク診断カラム

## 目的

従来CSVの32カラムとWeb UI・プロット動作を維持したまま、Linuxの`iw`が返す接続リンク診断情報をCSV末尾へ追加します。

従来の`SignalStrength`と`dBm`は互換性のため変更していません。これらは`nmcli dev wifi`の0～100品質値と、その近似dBm換算値です。絶対RSSIやATT差を詳しく確認するときは、追加された`IwSignal*`を使用してください。

追加カラムは後解析用です。現時点ではWebプロットへ追加していません。

## 追加カラム

| カラム | 内容 |
|---|---|
| `IwSampleValid` | 接続BSSIDと`iw station dump`のStation BSSIDが一致したとき`yes` |
| `IwStationBssid` | `iw`が返した接続先BSSID |
| `IwSignalDbm` | 直近受信フレームのRSSI |
| `IwSignalAvgDbm` | 接続通信フレームの平均RSSI |
| `IwBeaconSignalAvgDbm` | APビーコンの平均RSSI |
| `IwChainSignalDbm` | アンテナチェーン別RSSI。複数値は`|`区切り |
| `IwTxPacketsTotal` | 接続中Stationの累積送信パケット数 |
| `IwTxRetriesTotal` | 累積送信再試行数 |
| `IwTxFailedTotal` | 累積送信失敗数 |
| `IwTxPacketsDelta` | 前回有効サンプルからの送信パケット増分 |
| `IwTxRetriesDelta` | 前回有効サンプルからの再試行増分 |
| `IwTxFailedDelta` | 前回有効サンプルからの送信失敗増分 |
| `IwTxRetryRatePct` | `IwTxRetriesDelta / IwTxPacketsDelta * 100` |
| `IwTxFailedRatePct` | `IwTxFailedDelta / IwTxPacketsDelta * 100` |
| `IwTxBitrate` | 送信ビットレートの`iw`表示 |
| `IwRxBitrate` | 受信ビットレートの`iw`表示 |
| `IwTxMcs` / `IwRxMcs` | 送受信MCS |
| `IwTxNss` / `IwRxNss` | 送受信空間ストリーム数 |
| `IwChannelWidthMhz` | 接続リンクの帯域幅 |
| `IwTxPowerDbm` | インターフェース設定TX power。パケットごとの実送信電力ではない |
| `IwInactiveTimeMs` | Stationの非アクティブ時間 |
| `IwBeaconLoss` | 累積Beacon loss |
| `IwRxDropMisc` | 累積RX misc drop |

## 記録タイミングと値の扱い

- ローカル測定では、従来のPing実行直後に`iw dev wlan0 station dump`と`iw dev wlan0 info`を各1回実行します。
- SSH測定では、従来の1回のSSHプローブ内でPing後に同じ`iw`コマンドを実行します。SSH接続回数は増えません。
- `iw`取得不能、Windows測定、Wi-Fi切断、接続BSSID不一致の場合は追加カラムを空欄にします。
- 前回値による穴埋めは行いません。
- 累積値はドライバが返した値をそのまま記録します。
- 差分と率は、同一BSSIDでカウンタが単調増加した場合のみ記録します。
- 測定開始直後、再接続直後、BSSID変更時、カウンタリセット時は差分と率を空欄にします。
- `IwSignalAvgDbm`と`IwBeaconSignalAvgDbm`は仕様上の移動平均であり、古い値の誤記録ではありません。
- `nmcli`のNeighbor再スキャンは主測定ループとは別スレッドで実行します。再スキャンに時間がかかってもRSSI・Ping・`iw`の記録周期を止めません。
- 通常の接続情報取得は`nmcli dev wifi list --rescan no`を使用し、NetworkManagerの約30秒周期の暗黙再スキャンによる記録欠落を防ぎます。

## プロットについて

追加カラムは診断・比較用であり、現状のマッププロットへは追加していません。既存プロットは従来カラムだけを使用するため、旧ログと新版ログを同じ操作で読み込めます。

将来プロットを追加する場合は、まず次を候補とします。

- `IwSignalAvgDbm`: 接続リンクRSSIの安定した代表値
- `IwTxRetryRatePct`: 干渉や弱電による再送増加
- `IwTxFailedRatePct`: 送信失敗の局所発生
