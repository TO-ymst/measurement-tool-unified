# 計測ツール統合

Windowsローカル、WindowsからJetsonへのSSHリモート、Jetsonローカルを一つのWebダッシュボードで扱うWi-Fi電波測定ツールです。

ネイバーAP測定、マップ可視化、PNG出力、SSHリモート時の障害解析ログに対応します。

詳細は [README_統合版.md](README_統合版.md) と [FEATURES.md](FEATURES.md) を参照してください。

2026-08-12版では、従来CSVカラムとプロット動作を維持したまま、Linux `iw`の接続RSSI、平均RSSI、チェーン別RSSI、送信再試行・失敗、ビットレート等をCSV末尾に追加しています。詳細は [IW_DIAGNOSTICS.md](IW_DIAGNOSTICS.md) を参照してください。

2026-07-28のJetson実機改修を前バージョンへ反映する場合は、[HANDOFF_20260728.md](HANDOFF_20260728.md)を参照してください。
