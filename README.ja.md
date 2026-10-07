[English](README.md) | 日本語

# platina
日本語のピッチアクセントを練習するためのアプリです。

> **レッスンでPlatinaを使う方は、まずこちら：[LESSONS.ja.md](LESSONS.ja.md)**。授業の録音、間違いの振り返り、上達の記録までを
> 順を追って説明しています。プログラミングの知識は必要ありません。

話してください（本を音読しても、自由に話してもかまいません）。Platinaは音声を書き起こし、すべてのアクセント句について、語がつながるときのアクセントの変化も含めて
正しいアクセントを求めます。そして、実際に発音したアクセントを測り、違うところに印を付けます。

```
音を聞いた。  →  オト＼オ キイタ━
```

`＼` = このモーラの後で音程が下がる、`━` = 最後まで高いまま（平板）。
違って発音した句は赤で表示され、あなたの発音も示されます（`あなた：オ＼トオ`）。

画面は右上のボタンで英語と日本語を切り替えられます（「日本語」/「English」）。選んだ言語はブラウザに保存されます。初回はブラウザの言語設定に従います。

アプリには2つのエリアがあります。

- **自分のレッスン**（*レッスン*、*上達の記録*）。授業全体を録音し、あとで振り返り（はっきりした間違い、くり返す間違い、書き起こし全体）、
  レッスンごとのレベルを追います。[LESSONS.ja.md](LESSONS.ja.md) を参照してください。
  コード：`backend/app/{lessons,progress}.py`、`frontend/src/{lessons,progress}.ts`。
- **ワークショップ**（*クイックチェック*、*入力して確認*、*NHKアクセント*、*練習*）。単発の録音、入力した文、自分で確認したNHKアクセント、
  学習用のラベル付き録音。ここでの操作はレッスンや上達の記録を変えません。

UIの文言はすべて `frontend/src/i18n.ts` にあります（`en` と、同じ型を持つ `ja`。訳し漏れはコンパイルエラーになります）。

## しくみ

| 段階 | 内容 | 場所 |
|---|---|---|
| 正しいアクセント | UniDic 3.1 のアクセント（`aType` / `aConType` / `aModType`）を、OpenJTalk のアクセント句・アクセント結合規則の Python 移植と組み合わせます。OpenJTalk 自身の辞書も同じ規則を通し、独立した照合に使います。**あなたがNHKで確認した上書きが、どちらよりも優先されます。** | `backend/app/accent/{sources,rules,engine}.py` |
| 規則の修正 | 辞書の規則が標準的な東京アクセントと食い違う箇所：動詞の後の「た」、平板動詞の後の「なく/なけれ/なかっ」、意志の「ましょう/でしょう」。どれもゴールド文で裏付けています。 | `rules.py` |
| 音声 → テキスト | silero-vad で録音を間で区切り、kotoba-whisper v2.0 で発話ごとに書き起こします | `backend/app/audio/asr.py` |
| タイミング | モーラ単位の CTC 強制アラインメント（wav2vec2、ひらがな） | `backend/app/audio/align.py` |
| ピッチ | アクセントモデルには FCPE（torchfcpe）、予備に Praat（parselmouth）。話者の中央値からの半音で表します | `backend/app/audio/pitch.py` |
| 音声特徴 | 自己教師ありの日本語 HuBERT（ReazonSpeech `japanese-hubert-base-k2`）：各モーラのフレームを4つの層から取り、平均して圧縮（PCA）します。ピッチの軌跡だけではわからない、各モーラの発音のされ方（有声・無声化・明瞭さ）を表します。 | `backend/app/audio/ssl.py` |
| あなたのアクセント | 小さなニューラルネット（双方向 GRU）が発話のすべてのモーラ（自分の声域でのピッチの形、有声性、長さ、エネルギー、音の種類、HuBERT 特徴）を読み、各句がとりうるすべてのアクセントに確率を付けます。音声から区別できないアクセント（無声化したモーラ、ずれたモーラ、文末の疑問の上昇）はまとめるので、判定を左右しません。ネイティブ話者101人（JSUT + JVS）と、その音声をわざと間違ったアクセントに変えたコピーで学習しています。`accent_model.pt` がない場合は、以前の勾配ブースティングのモデルを使います。 | `backend/app/accent/{model,detect}.py` |
| 判定 | 正しい／**間違い**（赤）／判定不可／辞書を確認（灰色）。間違いと判定するには、正しいアクセントの可能性が低く、**かつ**別のアクセントがはっきり聞こえる必要があります。 | `backend/app/analyze.py` |
| ネイティブ | 辞書に載っていないが多くのネイティブが使うアクセント（JVSの話者100人から抽出）は、受け入れるか灰色で示し、赤にはしません。ひと息で言った句（読んで\|います）は受け入れます。ピッチのグラフには、高低の段差だけでなくネイティブの典型的な軌跡も示します。 | `accent/{variants,contour}.py`、`engine.py` |

正しいアクセントには、それぞれ出どころが記録されます。
- **NHK**：句の中の内容語すべてに、あなたの上書きがある。
- **agree**：UniDic と OpenJTalk が一致している。
- **uncertain**：一致していない。uncertain の句は、あなたの間違いとして数えません。

### 精度（学習に使っていない話者と文で評価）

コーパスの句はすべてネイティブが正しく発音したものなので、「誤検出」は正しいアクセントを間違いとしてしまった割合です。
「検出」は、辞書がほかのとりうるアクセントを正解としていたと仮定したとき、その間違いを指摘できた割合です。
旧 = JSUT だけで学習した勾配ブースティングの検出器と、以前の判定規則。

| テストセット | 誤検出（旧 → 新） | 検出（旧 → 新） | 判定不可（旧 → 新） | 1モーラずれの検出 |
|---|---|---|---|---|
| JSUT（話者1人、正確なラベル） | 2.5 % → **0.8 %** | 58 % → **72 %** | 31 % → 9 % | 37 % → 52 % |
| JVS nonpara30（ほかの話者、JSUT のラベル） | 6.1 % → **4.2 %** | 55 % → **68 %** | 33 % → 11 % | 42 % → 58 % |
| JVS parallel100（辞書によるラベル） | 10.8 % → **6.0 %** | 55 % → **68 %** | 28 % → 18 % | 42 % → 59 % |
| ネイティブの声を間違ったアクセントに変えたもの | 2.4–3.5 % → **0.3–1.3 %** | 54–60 % → **66–77 %** | 34–42 % → 9–13 % | 40–46 % → 58–73 % |

注：JVS の誤検出には、ネイティブが実際に別のアクセントを使った場合と、辞書の誤り（parallel100 は手作業ではなくエンジンでラベル付けしています）が含まれます。
「練習」タブの確認待ちリストで、原因ごとに分けられます。*あなたの*声での精度は、「練習」タブでラベル付きの録音を作るまでわかりません
（`tools/evaluate.py user.pkl`）。

## セットアップ

```sh
# backend (Python 3.12)
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/python -m unidic download

# frontend
cd frontend && npm install
```

## 起動

```sh
./start.sh            # API + フロントエンド（VOICEVOX がインストールされていればそれも）。http://localhost:5173/#lessons を開きます
```

手動で起動する場合：

```sh
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000     # API
cd frontend && npm run dev                                       # http://localhost:5173
```

`PLATINA_API_PORT` / `PLATINA_WEB_PORT` でポートを変更できます。レッスンは `backend/data/lessons.sqlite` と
`backend/data/lessons/`（`PLATINA_LESSONS_DB` / `PLATINA_LESSONS_DIR`）に保存され、どちらも git の管理外です。

最初の分析では音声モデル（約2.5 GB）をダウンロードし、GPU に読み込みます（使用量は約2.3 GB）。

## 「練習」タブ：Platinaにあなたの声を教える

*あなたの*声での精度は、ラベル付きの録音があって初めてわかります。

- **練習**：Platinaが句と目標のアクセントを選びます。正しいアクセントのときも、わざとの間違い（平板にする、下がり目を付ける、1〜2モーラずらす）のときもあります。
  お手本で聞いてから文を言い、目標どおりに聞こえたときだけ残してください。数回のセッションに分けて、正しいものとわざとの間違いをそれぞれ約300個集めるのが目標です。
- **判定が違いますか？**（句の詳細）：実際にどのアクセントで言ったかをPlatinaに伝えます。
- **ネイティブの録音を確認**：Platinaが間違いと判定しそうだったネイティブ話者の句です。原因は話者、Platina、辞書のどれでしょうか？

音声は `backend/data/recordings/` に、ラベルは `backend/data/labels.sqlite` に保存されます（どちらも git の管理外）。
`tools/build_cache.py user` で、これらを評価用セット（セッション単位で分離）と学習データに変換します。

## NHKに合わせる

NHK日本語発音アクセント新辞典は同梱できないので、自分で入力します。

- 「**NHKアクセント**」タブ：灰色で表示された語や「*確認したい語*」にある語を NHK のアプリで調べ、アクセント核の番号を入力します。
  上書きは辞書形ごとに保存されるので、活用形や句にも自動で反映されます。保存先は `backend/data/overrides.sqlite` で、git の管理外です。
- 「**入力して確認**」タブ → *NHKで確認済みのテスト文として保存*：文を `backend/tests/gold/sentences.yaml` に追加します。
  `verified: false` の項目は一般的な知識で埋めたもので、まだ NHK で確認する必要があります。

## お手本の音声

▶（「入力して確認」タブ、各録音の横、句の詳細）を押すと、画面に表示されたアクセントで文や句を聞けます。
あなたの NHK の上書きや別のアクセントも含まれ、*あなた*が使ったアクセントも同じ声で聞けます。

アクセントは常にPlatinaが決め、音声合成には任せません。各句を VOICEVOX のカナ（`音を聞いた。` → `オト'オ/キイタ'`）にし、
句の高低パターンからすべてのモーラのピッチをPlatinaが設定します。VOICEVOX 自身の抑揚は、学習に使うには弱すぎることが多いためです（`backend/app/tutor.py`）。

[VOICEVOX エンジン](https://github.com/VOICEVOX/voicevox_engine/releases)をローカルで起動してください
（Linux CPU 版、ダウンロード約1.8 GB）。

```sh
~/.local/share/voicevox/linux-cpu-x64/run          # http://127.0.0.1:50021
```

| 環境変数 | 既定値 | |
|---|---|---|
| `PLATINA_VOICEVOX_URL` | `http://127.0.0.1:50021` | |
| `PLATINA_VOICEVOX_SPEAKER` | `30`（No.7 アナウンス） | `/speakers` のスタイル ID。男性の声なら `11`（玄野武宏）がおすすめです |

Platinaが指定したピッチに従わない声もあります。たとえば青山龍星は、どの文も最後のモーラできしむように下がります。声を切り替える前に確認してください。

```sh
cd backend && ../.venv/bin/python -m tools.check_tutor --speaker 30 11 --out /tmp/tutor
```

ゴールド文では、No.7 は指定したピッチから平均0.6半音以内で、Platina自身の検出器は確信度の高い句の96 %を正しいと判定します（玄野武宏：100 %）。
VOICEVOX の利用規約ではクレジット表記 `VOICEVOX:<キャラクター名>` が必要です。アプリはページの下部に表示しています。

## テストとツール

```sh
cd backend
../.venv/bin/python -m pytest tests          # エンジンのゴールドセット、検出器、モデル、ラベル、API、エンドツーエンド
```

学習データ（リポジトリには含まれていません。JSUT と JVS は**非商用**なので、学習済みモデルも非商用です）：

```sh
../.venv/bin/python -m tools.fetch_jsut ~/datasets/jsut16k                  # JSUT basic5000 を HTTP range リクエストで取得
git clone https://github.com/sarulab-speech/jsut-label ~/datasets/jsut-label  # 正確なアクセントラベル
../.venv/bin/python -m tools.jvs prepare jvs_ver1.zip ~/datasets/jvs16k      # JVS（zip は自分でダウンロード）

# アラインメントとピッチ抽出を一度だけ行う（先にアプリを止めてください。GPU が小さいため）
../.venv/bin/python -m tools.build_cache jsut ~/datasets/jsut16k ~/datasets/jsut-label/labels/basic5000 jsut.pkl
../.venv/bin/python -m tools.build_cache jvs  ~/datasets/jvs16k  ~/datasets/jsut-label/labels/basic5000 jvs.pkl
../.venv/bin/python -m tools.build_cache user - - user.pkl --f0 fcpe        # あなたのラベル付き録音

../.venv/bin/python -m tools.add_f0 jsut.pkl fcpe --out jsut_fcpe.pkl     # FCPE のピッチ（jvs も同様）

# アクセントを変えた間違い（HuBERT 用に音声も保存）、分割ごと：train、dev、test
PLATINA_F0=fcpe ../.venv/bin/python -m tools.repitch jsut.pkl jvs.pkl --out repitch_train.pkl --split train \
    --max 8000 --identity 0.3 --wav-dir ~/datasets/repitch_wav/train

# HuBERT 特徴：PCA の基底を作り、各キャッシュの横に CACHE.ssl.pkl を作る
../.venv/bin/python -m tools.ssl_feats fit jsut_fcpe.pkl jvs_fcpe.pkl --pca ssl_pca.npz
../.venv/bin/python -m tools.ssl_feats extract jsut_fcpe.pkl jvs_fcpe.pkl repitch_*.pkl --pca ssl_pca.npz

# 学習、しきい値（チェックポイントに保存）、評価
../.venv/bin/python -m tools.train_accent jsut_fcpe.pkl jvs_fcpe.pkl repitch_train.pkl [user.pkl] \
    --f0 fcpe --epochs 15 --ssl ssl_pca.npz --ssl-drop 0.6 --save
../.venv/bin/python -m tools.tune_thresholds jsut_fcpe.pkl jvs_fcpe.pkl repitch_dev.pkl --f0 fcpe --kinds exact,label,repitch
../.venv/bin/python -m tools.set_thresholds app/accent/accent_model.pt 0.05 0.05 0.5
../.venv/bin/python -m tools.evaluate jsut_fcpe.pkl jvs_fcpe.pkl [user.pkl] --f0 fcpe --split test --detector new

# ネイティブ：抑揚モデル、アクセントの揺れ、確認待ちリスト（「練習」タブ）
../.venv/bin/python -m tools.train_contour jsut.pkl jvs.pkl --save
../.venv/bin/python -m tools.mine_variants jvs.pkl
../.venv/bin/python -m tools.review_queue jsut.pkl jvs.pkl --split dev
```

`PLATINA_ACCENT_MODEL` で別のチェックポイントを使えます。`PLATINA_F0=fcpe` でピッチ抽出器を切り替えます
（チェックポイントには、学習に使った抽出器が記録されています）。
`PLATINA_TUTOR_CONTOUR=1` にすると、お手本がネイティブの抑揚モデルに従います。
