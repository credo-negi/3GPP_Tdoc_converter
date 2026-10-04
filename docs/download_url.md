# ダウンロードURLの確定方法

## 結論

Tdocのzipの URL は、**Tdoc list (xlsx) の `TDoc` 列 (A列) の各セルに設定されたハイパーリンク**をそのまま使う。
URLを規則から組み立てるのは、リンクが無いときの予備(フォールバック)に限る。

```
https://www.3gpp.org/ftp/tsg_ran/WG1_RL1/TSGR1_126b/Docs/R1-2606970.zip
└─────────── ホスト ──────────┘└ WG ┘└ 会議 ┘     └ Tdoc番号 ┘
```

実装: `tdoc_converter/tdoc_list.py` の `load_download_urls()` → `Tdoc.url`、
`tdoc_converter/download.py` の `download_zip(tdoc, url, ...)`。

## xlsx からの取り出し方

- ハイパーリンクはセルの値ではなく、シート定義 (`xl/worksheets/sheet1.xml` の `<hyperlink ref="A2" r:id=…>` と
  `_rels/sheet1.xml.rels` の `Target`) に入っている。
- `pandas.read_excel` はリンクを捨てるので使えない。`openpyxl.load_workbook(path)` を**通常モード**で開き、
  `cell.hyperlink.target` を読む(`read_only=True` ではリンクが読めない)。
- `TDoc_List` シートは最大行数が約104万と申告されているため、実データの終端 (値のある最後の行) で打ち切る。
  通常モードでも読み込みは約1秒。
- そのほかの列 (E, Q-V) のリンクは連絡先 (ETSI TDIR) などで、ダウンロードには無関係。

## リンクの有無とステータス (RAN1#126-bis のxlsxで確認)

| 項目 | 結果 |
|---|---|
| Tdoc 行数 | 1,644 |
| A列にリンクがある行 | 1,470 |
| 「Uploaded」列に日時がある行 | 1,470 |
| 両者の食い違い | 0 件 (リンクあり ⇔ アップロード済みで完全一致) |
| リンクが指す会議フォルダ | 全て `TSGR1_126b` |
| リンクなし | 174 件 (`reserved` 170, `withdrawn` 4。ファイルはサーバーに無い)。なお `withdrawn` でもアップロード済みの 3 件にはリンクがある |

このため、`reserved` などリンクの無い Tdoc は「未アップロード」として取得対象から外し、レポートに一覧する。

## フォールバック規則 (リンクが無い場合のみ)

1. xlsx ファイル名 `TDoc_List_Meeting_RAN1#126-bis.xlsx` から会議を推定する。
   フォルダ名は `bis` → `b`、`ter` → `c` と短縮される (`126-bis` → **`TSGR1_126b`**。`TSGR1_126bis` ではない)。
   候補は `meeting_folder_candidates()` が `TSGR1_126b`, `TSGR1_126bis`, `TSGR1_126-bis` の順に作る。
2. `https://ftp.3gpp.org/tsg_ran/WG1_RL1/` のディレクトリ一覧を取得し、候補のうち実在するものを採用する
   (`resolve_meeting_folder()`)。
3. `{FTP_BASE}/{フォルダ}/Docs/{Tdoc番号}.zip` を URL とする (`zip_url()`)。

リンクがあるときは、フォルダ名もそのリンクから取る (`folder_from_url()`)。複数フォルダにまたがる場合はエラーにする。
`--folder TSGR1_126b` で手動指定もできる。

## サーバー側の挙動 (2026-10-04 に確認)

- **User-Agent**: Python 既定の UA は 403 になる場合があるため、ブラウザ風の UA を付ける (`download.HEADERS`)。
- **ホスト**: `ftp.3gpp.org` と `www.3gpp.org/ftp` のどちらでも同じファイルが取れる。
  存在しない/誤ったフォルダ名は 403 (または 301 → 403) を返し、404 にならないことがある。
  フォルダ名の誤りは「アクセス拒否」に見えるので注意。
- **大文字小文字**: 拡張子は `.zip` でも `.Zip` でも取れる (xlsx には `R1-2607834.Zip` のリンクがある)。
  このため URL は加工せずそのまま使う。
- **エラー応答**: 200 で HTML のエラーページが返ることがあるので、保存後に zip として妥当かを確認し、
  不正なら破棄して再試行する。404 は再試行しない。
- `HEAD` に対応しており、`Content-Type: application/x-zip-compressed` が返る。事前検証に使える。

## 検証結果

1. **全リンクの存在確認** (xlsx の 1,470 件を `HEAD`、約250秒):
   1,469 件が 200 / zip。失敗は 1 件のみ。
   - `R1-2607790` (agenda item 10.4.2, Panasonic): リンクのファイル名が `R1-2607790+.zip` と、
     Tdoc番号に余計な `+` が付いている。`+` のままでも `%2B` でも、`.zip`/`.Zip` に直しても
     403 (`ftp.3gpp.org` では 404)。xlsx 側のデータ異常と判断し、取得失敗として報告される。
     (今回の agenda item 10.5.2.2 には含まれない。)
2. **agenda item 10.5.2.2** (55 件のうち取得対象 49 件):
   - `--check-urls` で全 49 件が 200 / zip。
   - 空の出力先から、xlsx のリンクだけで実際にダウンロード → 解凍 → markdown 変換まで通し、49/49 件成功
     (zip は 49 件とも `zipfile.is_zipfile` を満たす)。
   - 残り 6 件 (`R1-2607731`〜`R1-2607736`, Moderator 提出) は `reserved` でリンクなし。

## 再検証の方法

```
python3 -m tdoc_converter 10.5.2.2 --check-urls   # HEAD で確認するだけ。何もダウンロードしない
python3 -m tdoc_converter 10.5.2.2                # ダウンロード以降を実行
```

全 agenda item を確認したいときは、`tdoc_converter.download.check_urls({Tdoc番号: URL, …})` を直接呼ぶ。
サーバー負荷を考え、並列数は既定で 4 にしている。
