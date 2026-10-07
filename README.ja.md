[English](README.md) | 日本語

# platina
日本語のピッチアクセントを練習するためのアプリです。

> **授業でPlatinaを使いたい方は、まずこちらをお読みください：[LESSONS.ja.md](LESSONS.ja.md)**。授業の録音から、間違いの振り返り、
> 上達の記録まで、順を追って説明しています。プログラミングの知識は必要ありません。

話すだけでOKです（本の音読でも、自由な会話でもかまいません）。Platinaが音声を文字に起こし、アクセント句ごとに正しいアクセントを求めます
（語と語がつながるときのアクセントの変化も考慮します）。そのうえで実際の発音のアクセントを測定し、違っている箇所に印を付けます。

```
音を聞いた。  →  オト＼オ キイタ━
```

`＼` はそのモーラの後で音が下がること、`━` は最後まで下がらないこと（平板型）を表します。
アクセントが違っていたフレーズは赤で表示され、実際の発音も併記されます（`あなた：オ＼トオ`）。

画面の言語は、右上のボタン（「日本語」/「English」）で切り替えられます。選んだ言語はブラウザに保存され、初回はブラウザの言語設定に合わせて表示されます。

アプリは大きく2つに分かれています。

- **マイレッスン**（*レッスン*、*上達の記録*）：授業全体を録音して、あとから振り返ります（明らかな間違い、何度も出た間違い、文字起こし全文）。
  レッスンごとのレベルの推移も確認できます。詳しくは [LESSONS.ja.md](LESSONS.ja.md) をご覧ください。
  コード：`backend/app/{lessons,progress}.py`、`frontend/src/{lessons,progress}.ts`。
- **ラボ**（*クイックチェック*、*テキストで確認*、*NHKアクセント登録*、*練習*）：単発の録音、入力した文の確認、NHKで確認したアクセントの登録、
  学習用のラベル付き録音。ここでの操作は、レッスンや上達の記録には影響しません。

UIの文言はすべて `frontend/src/i18n.ts` にまとめています（`en` と、それと同じ型の `ja`。訳し漏れがあるとコンパイルエラーになります）。

## しくみ

| 段階 | 内容 | 場所 |
|---|---|---|
| 正しいアクセント | UniDic 3.1 のアクセント情報（`aType` / `aConType` / `aModType`）に、OpenJTalk のアクセント句・アクセント結合規則を Python に移植したものを組み合わせます。OpenJTalk 自身の辞書も同じ規則に通し、独立したクロスチェックに使います。**あなたがNHKで確認して登録したアクセントは、どちらよりも優先されます。** | `backend/app/accent/{sources,rules,engine}.py` |
| 規則の修正 | 辞書の規則が標準的な東京アクセントと食い違う箇所を修正しています：動詞に続く「た」、平板型動詞に続く「なく/なけれ/なかっ」、意志の「ましょう/でしょう」。いずれもゴールド文で裏付けを取っています。 | `rules.py` |
| 音声 → テキスト | silero-vad で無音部分を区切りに録音を分割し、kotoba-whisper v2.0 で発話ごとに文字起こしします | `backend/app/audio/asr.py` |
| タイミング | モーラ単位の CTC 強制アラインメント（wav2vec2、ひらがな） | `backend/app/audio/align.py` |
| ピッチ | アクセントモデルには FCPE（torchfcpe）、予備として Praat（parselmouth）を使用。話者ごとの中央値からの半音で表します | `backend/app/audio/pitch.py` |
| 音声特徴 | 自己教師あり学習の日本語 HuBERT（ReazonSpeech `japanese-hubert-base-k2`）：各モーラのフレームを4つの層から取り出し、平均したうえで PCA で圧縮します。ピッチの軌跡だけではわからない、各モーラの発音の様子（有声か、無声化しているか、はっきりしているか）を捉えます。 | `backend/app/audio/ssl.py` |
| あなたのアクセント | 小さなニューラルネット（双方向 GRU）が、発話中のすべてのモーラの情報（自分の声域でのピッチの形、有声性、長さ、エネルギー、音の種類、HuBERT 特徴）を読み取り、各フレーズで考えられるすべてのアクセントに確率を割り当てます。音声からは区別できないアクセント（無声化したモーラ、ずれたモーラ、文末の疑問の上昇）はひとまとめに扱うため、判定には影響しません。学習データはネイティブ話者101人（JSUT + JVS）の音声と、それをわざと間違ったアクセントに加工したコピーです。`accent_model.pt` がない場合は、以前の勾配ブースティングのモデルを使います。 | `backend/app/accent/{model,detect}.py` |
| 判定 | 正解／**間違い**（赤）／判定不可／辞書を確認（灰色）。「間違い」と判定するのは、正しいアクセントである可能性が低く、**しかも**別のアクセントがはっきり聞き取れた場合だけです。 | `backend/app/analyze.py` |
| ネイティブ | 辞書には載っていないものの多くのネイティブが使うアクセント（JVSの話者100人の音声から抽出）は、正解として扱うか灰色で表示し、赤にはしません。ひと続きに言ったフレーズ（読んで\|います）も正解として扱います。ピッチのグラフには、高低の段差だけでなく、ネイティブの平均的な軌跡も表示します。 | `accent/{variants,contour}.py`、`engine.py` |

正しいアクセントには、それぞれ根拠が記録されます。
- **NHK**：フレーズ内のすべての内容語について、あなたが登録したアクセントがある。
- **agree**：UniDic と OpenJTalk の結果が一致している。
- **uncertain**：一致していない。uncertain のフレーズは、あなたの間違いとして数えません。

### 精度（学習に使っていない話者・文で評価）

コーパスのフレーズはすべてネイティブが正しく発音したものなので、「誤検出」は正しいアクセントを間違いと判定してしまった割合です。
「検出」は、辞書が別のアクセントを正解としていたと仮定した場合に、その違いを指摘できた割合です。
旧 = JSUT のみで学習した勾配ブースティングの検出器と、以前の判定規則。

| テストセット | 誤検出（旧 → 新） | 検出（旧 → 新） | 判定不可（旧 → 新） | 1モーラずれの検出 |
|---|---|---|---|---|
| JSUT（話者1人、正確なラベル） | 2.5 % → **0.8 %** | 58 % → **72 %** | 31 % → 9 % | 37 % → 52 % |
| JVS nonpara30（別の話者、JSUT のラベル） | 6.1 % → **4.2 %** | 55 % → **68 %** | 33 % → 11 % | 42 % → 58 % |
| JVS parallel100（辞書によるラベル） | 10.8 % → **6.0 %** | 55 % → **68 %** | 28 % → 18 % | 42 % → 59 % |
| ネイティブの音声を間違ったアクセントに加工したもの | 2.4–3.5 % → **0.3–1.3 %** | 54–60 % → **66–77 %** | 34–42 % → 9–13 % | 40–46 % → 58–73 % |

注：JVS の誤検出には、ネイティブが実際に別のアクセントで発音したケースと、辞書の誤り（parallel100 のラベルは人手ではなくエンジンで付けています）が含まれます。
どちらが原因かは「練習」タブのチェックリストで仕分けできます。*あなたの*声での精度は、「練習」タブでラベル付きの録音を集めるまでわかりません
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

個別に起動する場合：

```sh
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000     # API
cd frontend && npm run dev                                       # http://localhost:5173
```

ポートは `PLATINA_API_PORT` / `PLATINA_WEB_PORT` で変更できます。レッスンは `backend/data/lessons.sqlite` と
`backend/data/lessons/`（`PLATINA_LESSONS_DB` / `PLATINA_LESSONS_DIR`）に保存されます。どちらも git の管理対象外です。

初回の分析時に音声モデル（約2.5 GB）をダウンロードし、GPU に読み込みます（使用メモリは約2.3 GB）。

## 「練習」タブ：Platinaにあなたの声を覚えさせる

*あなたの*声での精度は、ラベル付きの録音がなければわかりません。

- **練習**：Platinaが文と目標のアクセントを選びます。正しいアクセントのときと、わざと間違えるとき（平板にする、下がり目を付ける、1〜2モーラずらす）があります。
  お手本を聞いてから文を読み、指定どおりに言えた録音だけを残してください。何回かのセッションに分けて、正しいものとわざと間違えたものをそれぞれ約300ずつ集めるのが目標です。
- **判定が違う？**（フレーズの詳細）：実際にどのアクセントで言ったかをPlatinaに教えます。
- **ネイティブの録音をチェック**：Platinaが間違いと判定しかけたネイティブ話者のフレーズです。原因は話者、Platina、辞書のどれかを選びます。

音声は `backend/data/recordings/` に、ラベルは `backend/data/labels.sqlite` に保存されます（どちらも git の管理対象外）。
`tools/build_cache.py user` を実行すると、これらが評価用セット（セッション単位で分割）と学習データに変換されます。

## NHKのアクセントに合わせる

『NHK日本語発音アクセント新辞典』はアプリに同梱できないため、必要なアクセントは自分で登録します。

- 「**NHKアクセント登録**」タブ：灰色で表示された語や「*要確認の語*」にある語を NHK のアプリで調べ、アクセント型を入力します。
  登録は辞書形ごとに保存されるので、活用形やフレーズにも自動で反映されます。保存先は `backend/data/overrides.sqlite`（git の管理対象外）です。
- 「**テキストで確認**」タブ → *NHKで確認済みのテスト文として保存*：文を `backend/tests/gold/sentences.yaml` に追加します。
  `verified: false` の項目は一般的な知識をもとに入力したもので、まだ NHK での確認が必要です。

## お手本の音声

▶ ボタン（「テキストで確認」タブ、各録音の横、フレーズの詳細）を押すと、画面に表示されているアクセントで文やフレーズを読み上げます。
登録したNHKのアクセントや別のアクセントも反映され、*あなた*が実際に使ったアクセントも同じ声で聞き比べられます。

アクセントは必ずPlatinaが決め、音声合成エンジン任せにはしません。各フレーズを VOICEVOX のカナ表記（`音を聞いた。` → `オト'オ/キイタ'`）に変換し、
フレーズの高低パターンに沿って、すべてのモーラのピッチをPlatinaが指定します。VOICEVOX 自身の抑揚は、学習用としては高低の差が小さすぎることが多いためです（`backend/app/tutor.py`）。

[VOICEVOX エンジン](https://github.com/VOICEVOX/voicevox_engine/releases)をローカルで起動してください
（Linux CPU 版、ダウンロードサイズは約1.8 GB）。

```sh
~/.local/share/voicevox/linux-cpu-x64/run          # http://127.0.0.1:50021
```

| 環境変数 | デフォルト | |
|---|---|---|
| `PLATINA_VOICEVOX_URL` | `http://127.0.0.1:50021` | |
| `PLATINA_VOICEVOX_SPEAKER` | `30`（No.7 アナウンス） | `/speakers` のスタイル ID。男性の声なら `11`（玄野武宏）がおすすめです |

声によっては、Platinaが指定したピッチどおりに話してくれないものがあります。たとえば青山龍星は、どの文でも最後のモーラで声がきしむように下がります。声を変える前に、次のコマンドで確認してください。

```sh
cd backend && ../.venv/bin/python -m tools.check_tutor --speaker 30 11 --out /tmp/tutor
```

ゴールド文で確認したところ、No.7 は指定したピッチとの差が平均0.6半音以内で、確信度の高いフレーズの96 %をPlatina自身の検出器が正解と判定しました（玄野武宏は100 %）。
VOICEVOX の利用規約により `VOICEVOX:<キャラクター名>` のクレジット表記が必要です。アプリではページ下部に表示しています。

## テストとツール

```sh
cd backend
../.venv/bin/python -m pytest tests          # エンジンのゴールドセット、検出器、モデル、ラベル、API、エンドツーエンド
```

学習データ（リポジトリには含まれていません。JSUT と JVS は**非商用ライセンス**のため、学習済みモデルも非商用です）：

```sh
../.venv/bin/python -m tools.fetch_jsut ~/datasets/jsut16k                  # JSUT basic5000 を HTTP range リクエストで取得
git clone https://github.com/sarulab-speech/jsut-label ~/datasets/jsut-label  # 正確なアクセントラベル
../.venv/bin/python -m tools.jvs prepare jvs_ver1.zip ~/datasets/jvs16k      # JVS（zip は各自でダウンロード）

# アラインメントとピッチ抽出は一度だけ実行（GPU のメモリが少ないので、先にアプリを止めておく）
../.venv/bin/python -m tools.build_cache jsut ~/datasets/jsut16k ~/datasets/jsut-label/labels/basic5000 jsut.pkl
../.venv/bin/python -m tools.build_cache jvs  ~/datasets/jvs16k  ~/datasets/jsut-label/labels/basic5000 jvs.pkl
../.venv/bin/python -m tools.build_cache user - - user.pkl --f0 fcpe        # あなたのラベル付き録音

../.venv/bin/python -m tools.add_f0 jsut.pkl fcpe --out jsut_fcpe.pkl     # FCPE のピッチ（jvs も同様）

# アクセントを加工した「間違い」データ（HuBERT 用に音声も保存）。train、dev、test の分割ごとに作成
PLATINA_F0=fcpe ../.venv/bin/python -m tools.repitch jsut.pkl jvs.pkl --out repitch_train.pkl --split train \
    --max 8000 --identity 0.3 --wav-dir ~/datasets/repitch_wav/train

# HuBERT 特徴：PCA の基底を作成し、各キャッシュの隣に CACHE.ssl.pkl を作成
../.venv/bin/python -m tools.ssl_feats fit jsut_fcpe.pkl jvs_fcpe.pkl --pca ssl_pca.npz
../.venv/bin/python -m tools.ssl_feats extract jsut_fcpe.pkl jvs_fcpe.pkl repitch_*.pkl --pca ssl_pca.npz

# 学習、しきい値の調整（チェックポイントに保存）、評価
../.venv/bin/python -m tools.train_accent jsut_fcpe.pkl jvs_fcpe.pkl repitch_train.pkl [user.pkl] \
    --f0 fcpe --epochs 15 --ssl ssl_pca.npz --ssl-drop 0.6 --save
../.venv/bin/python -m tools.tune_thresholds jsut_fcpe.pkl jvs_fcpe.pkl repitch_dev.pkl --f0 fcpe --kinds exact,label,repitch
../.venv/bin/python -m tools.set_thresholds app/accent/accent_model.pt 0.05 0.05 0.5
../.venv/bin/python -m tools.evaluate jsut_fcpe.pkl jvs_fcpe.pkl [user.pkl] --f0 fcpe --split test --detector new

# ネイティブ関連：抑揚モデル、アクセントのゆれ、チェックリスト（「練習」タブ）
../.venv/bin/python -m tools.train_contour jsut.pkl jvs.pkl --save
../.venv/bin/python -m tools.mine_variants jvs.pkl
../.venv/bin/python -m tools.review_queue jsut.pkl jvs.pkl --split dev
```

`PLATINA_ACCENT_MODEL` で別のチェックポイントを指定できます。ピッチ抽出器は `PLATINA_F0=fcpe` で切り替えられます
（チェックポイントには、学習時に使った抽出器が記録されています）。
`PLATINA_TUTOR_CONTOUR=1` にすると、お手本の音声がネイティブの抑揚モデルに沿って話します。
