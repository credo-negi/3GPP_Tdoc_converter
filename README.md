# 3GPP Tdoc converter

Tdoc list (xlsx) → zip のダウンロード → 解凍 → docx/pptx → Markdown → Observation/Proposal の一覧、を順に行うツール。

```
python3 -m tdoc_converter 10.5.2.2               # Tdoc_List/ にあるxlsxを使う
python3 -m tdoc_converter 10.5.2.2 --limit 3     # 先頭3件だけ試す
python3 -m tdoc_converter 10.5.2.2 --check-urls  # ダウンロードリンクをHEADで確認するだけ
python3 -m unittest discover -s tests -t .       # オフラインで動くテスト
```

必要なもの: pandas, openpyxl, requests, markitdown, python-docx, python-pptx, Pillow (テストのみ)。

## 出力

`output/<会議フォルダ>/<agenda item>/{zip,extracted,markdown,results}`

- `markdown/<Tdoc番号>.md`: 図は `images/<Tdoc番号>/imgNNN.png` として隣に保存し、相対パスでリンクする。同じ画像は1ファイルにまとめる。
- `results/observations_proposals.{md,json}`: 抽出した Observation / Proposal。

## 補足

- ダウンロードURLは、xlsxのTDoc列のセルに設定されたハイパーリンクを使う。
  読み方、フォールバック規則、サーバー側の挙動、検証結果は [docs/download_url.md](docs/download_url.md) を参照。
- EMF/WMF形式の図は、ブラウザやMarkdownビューアでは表示できないため、LibreOffice(無ければInkscape)でPNGに変換し、
  余白を切り詰めて保存する。macOSでは `/Applications/LibreOffice.app` を自動で探す。
  LibreOfficeが空白を描く「ビットマップだけのEMF+」は、埋め込まれたビットマップを取り出してPNGにする。
  変換できなかった場合は元の `.emf` / `.wmf` を保存してリンクする。
  変換ツールを入れる前に作った出力は、`python3 -m tdoc_converter.fix_images output/<会議>/<agenda item>/markdown` で
  PNGに変換し、mdのリンクも張り替えられる(118枚で約4分)。
- 多くのTdocは「Proposal N:」をWordの自動番号で持っている。`numbering.py` が変換前にそのラベルを本文に書き出す。
- 表の中の記述(過去の合意の引用など)は読み飛ばす。Conclusionに再掲された同じ記述は1件にまとめる。
- 旧形式の `.doc` の変換には、macOSの `textutil` またはLibreOfficeが必要。
