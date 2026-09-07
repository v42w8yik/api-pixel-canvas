# API Pixel Canvas

座標と色をHTTP APIで指定すると、ブラウザ上の64×64ドットキャンバスへほぼリアルタイムに反映される、ローカル実験用アプリです。AIとの直接連携や認証、データベースは含みません。

## 動作イメージ

- Web UI: 64×64の画像を10倍に拡大表示
- API: 1ピクセル・一括ピクセル描画、全消去、PNG取得
- 更新: Web UIがAPIを250ミリ秒ごとにポーリング
- 状態: 1つのPythonプロセス内でAPIサーバーを正本として保持

## 必要環境

- Python 3.10以降
- LinuxまたはWSL（標準ライブラリのみ。追加パッケージ不要）

## インストールと起動

```bash
git clone https://github.com/YOUR_ACCOUNT/api-pixel-canvas.git
cd api-pixel-canvas
python3 app.py
```

ブラウザで <http://localhost:8000> を開きます。APIは `http://localhost:8001` です。終了は `Ctrl+C` です。

既定では両サーバーとも `127.0.0.1` のみにbindし、LANやインターネットには公開しません。bind先を意図的に変更する場合のみ `python3 app.py --host ADDRESS` を使用してください。

## API仕様

座標は左上が `(0, 0)`、右下が `(63, 63)` です。色は `#RRGGBB` 形式です。

### `POST /pixel`

```bash
curl -X POST http://localhost:8001/pixel \
  -H "Content-Type: application/json" \
  -d '{"x":10,"y":20,"color":"#ff0000"}'
```

### `POST /pixels`

1回で最大4096ピクセルを描画できます。この上限は `app.py` の `MAX_PIXELS_PER_REQUEST` で変更できます。1件でも不正なら全件を反映しません。

```bash
curl -X POST http://localhost:8001/pixels \
  -H "Content-Type: application/json" \
  -d '{"pixels":[{"x":10,"y":20,"color":"#ff88aa"},{"x":11,"y":20,"color":"#ff88aa"},{"x":12,"y":21,"color":"#000000"}]}'
```

### `POST /clear`

```bash
curl -X POST http://localhost:8001/clear \
  -H "Content-Type: application/json" \
  -d '{}'
```

### `GET /image`

```bash
curl http://localhost:8001/image --output pixel-canvas.png
```

### `GET /state`

Web UI同期用です。キャンバスサイズ、更新version、全ピクセルの色配列をJSONで返します。

## エラー

- 不正JSON: `400 Bad Request`
- 不正な座標・色・形式: `422 Unprocessable Entity`
- ピクセル数上限超過: `413 Request Entity Too Large`
- リクエスト本文は最大512 KiB（`MAX_REQUEST_BYTES` で変更可能）

ブラウザ向けCORSは `http://localhost:8000` と `http://127.0.0.1:8000` のみ許可します。

## テスト

```bash
python3 -m unittest discover -s tests -v
```

## ライセンス

[MIT License](LICENSE)
