# 電測スクリプト統合版

ブラウザのWebダッシュボードから、次の3通りで測定できる統合版です。

- Windows ローカル: Windows PC自身のWi-Fiを測定
- Windows SSHリモート: Windows PCからJetsonへSSH接続してJetsonのWi-Fiを測定
- Jetson ローカル: Jetson自身でダッシュボードを動かしてWi-Fiを測定

測定開始後は、現在の接続状態・Ping・BSSID・ネイバー情報を同じCSV形式で記録します。SSHリモートでは、通信断やBSSID変化時の障害解析JSONLも任意で取得できます。マップ表示ではBest Neighbor RSSI/BSSIDを含めてPNG出力できます。

## Windowsで使う

1. `install_windows.bat` を初回だけ実行します。
2. `start_windows.bat` を実行します。
3. 開いたダッシュボードで測定方式を選びます。
   - `ローカル`: Windows PC自身を測定
   - `Jetson(SSH)`: JetsonのIPアドレス・ユーザーを設定して測定

## Jetsonで使う

1. このフォルダをJetsonへコピーします。展開先は空白を含まないパスにしてください。
2. Jetsonで以下を実行します。

   ```bash
   chmod +x *.sh
   ./install_jetson.sh
   ./start_jetson.sh
   ```

3. 同じネットワークのPCから `http://<JetsonのIPアドレス>:9000` を開き、測定方式を `ローカル` にして使います。

電源投入時に自動起動する場合は、起動確認後に `./install_service_jetson.sh` を実行します。

## 配布内容

- `web_measurement_app/`: ダッシュボードと測定処理
- `*_windows.*`: Windowsセットアップ・起動・停止
- `*_jetson.sh`: Jetsonセットアップ・起動・自動起動設定

ログ、SSH秘密鍵、Python仮想環境、Git管理情報はこのフォルダに含めていません。

詳細な対応機能は `FEATURES.md` を参照してください。
