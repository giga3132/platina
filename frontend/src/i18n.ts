// UI language (English / 日本語). Every visible string lives here; `ja` has
// the type of `en`, so a missing translation is a compile error. Static
// text in index.html is marked with data-i18n="key" (data-i18n-placeholder,
// -title, -aria-label for attributes) and filled in by applyStatic().

export type Lang = "en" | "ja";

type Kind = "said flat" | "added a drop" | "1 mora off" | "2+ moras off";

const plural = (n: number, one: string, many = `${one}s`) => (n === 1 ? one : many);

const en = {
  // header and navigation
  langToggle: "日本語",
  langToggleTitle: "画面を日本語にする",
  tagline: "Japanese pitch-accent coach",
  navSections: "Sections",
  navMyLessons: "My lessons",
  tabLessons: "Lessons",
  tabProgress: "Progress",
  navWorkshop: "Workshop",
  navWorkshopHint: "one-off recordings and experiments",
  tabQuickCheck: "Quick check",
  tabType: "Type",
  tabNhk: "My NHK accents",
  tabPractice: "Practice",

  // Lessons tab
  lessonsIntro: "Record your class, then review your pitch accent afterwards: your clearest mistakes, the ones you " +
    "repeat, and everything you said. Wear headphones so only your own voice is recorded.",
  lessonRecord: "● Start lesson recording",
  lessonStop: "■ Stop and analyze",
  lessonUpload: "Upload a recording",
  microphone: "Microphone",
  yourLessons: "Your lessons",
  defaultLessonTitle: (d: Date) =>
    `Lesson ${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`,
  cantReach: "Can't reach Platina. Is it running? Start it with ./start.sh.",
  savedUpTo: (t: string) => `Saved up to ${t}`,
  recordingBackground: "Recording. You can leave this tab in the background during class.",
  retrying: (n: number) =>
    `Can't reach Platina — retrying (${n} ${plural(n, "piece")} waiting). Keep this page open.`,
  micUnavailableLesson: (m: string) =>
    `Microphone unavailable: ${m}. Allow microphone access for this page and try again.`,
  nothingSavedYet: "Nothing saved yet (the first piece arrives after 15 seconds)",
  savingLastPiece: "Saving the last piece…",
  lessonSavedAnalyzing: "Saved. Platina is analyzing your lesson; the progress bar below shows how far it is. " +
    "You can close this page meanwhile.",
  couldntFinish: (m: string) => `Couldn't finish the recording: ${m}`,
  recordingNow: "Recording now",
  analyzeSaved: "Analyze what was saved",
  couldnt: (m: string) => `Couldn't: ${m}`,
  interrupted: "The recording was interrupted. ",
  waitingAnalysis: "Waiting to be analyzed…",
  analyzingLine: (done: number, total: number) => `Analyzing: line ${done} of ${total}`,
  findingSpeech: "Finding where you spoke…",
  tryAgain: "Try again",
  somethingWrong: (m: string) => `Something went wrong: ${m} `,
  levelBadge: (l: number) => `Level ${l}`,
  mistakesIn: (m: number, j: number) => ` · ${m} ${plural(m, "mistake")} in ${j} judged phrases`,
  tooShort: "too short to count",
  olderAnalysis: "older analysis",
  noLessons: "No lessons yet. Press “Start lesson recording” before your next class, or upload a recording.",
  recorded: (d: string) => `${d} recorded`,
  youSpokeFor: (d: string) => `you spoke ${d}`,
  delete: "Delete",
  deleteNamed: (t: string) => `Delete ${t}`,
  confirmDelete: (t: string) => `Delete “${t}”? Its recording and review are removed for good.`,
  summary: "Summary",
  levelRange: (lo: number, hi: number) => `Level (range ${lo}–${hi})`,
  mistakes: "Mistakes",
  unclearNotCounted: "Unclear (not counted)",
  youSpoke: "You spoke",
  shortLessonNote: "A short lesson: it is shown here but doesn't count in your progress, because a few phrases " +
    "can't show your level reliably.",
  howLevel: "How is the level worked out?",
  lessonLevelExplain: (judged: number, correct: number, acc: number | null) =>
    `Of the ${judged} phrases Platina could judge, you said ${correct} with the expected accent` +
    (acc === null ? "." : ` (${acc} %).`) +
    " The level is the lowest value that share is likely to be, so it grows with how much you said: two correct" +
    " phrases give about 42, 19 of 20 about 80, 285 of 300 about 92. Unclear phrases and words whose dictionary" +
    " accent is unsure don't count either way.",
  expected: "expected",
  youSaid: "you said",
  mostObvious: "Most obvious mistakes",
  noClearMistakes: "No clear mistakes in this lesson.",
  obviousIntro: "The phrases Platina is surest you said with a different accent.",
  you: "You",
  hearYourselfSayIt: "Hear yourself say it",
  goTo: (t: string) => `Go to ${t}`,
  showLine: "Show this line in the transcript",
  expectedBtn: "Expected",
  hearExpected: "Hear the expected accent",
  repeated: "Repeated mistakes",
  noRepeated: "No mistake came up more than once.",
  hearYourselfAt: (t: string) => `Hear yourself at ${t}`,
  goToLine: "Go to line",
  hearEachTime: "Hear each time",
  hearThisLine: (t: string) => `Hear this line (${t})`,
  skipped: (why: string): string => (why === "not Japanese" ? "not Japanese, not judged" : "no speech, not judged"),
  textFixed: "text fixed by you",
  editText: "Edit text",
  editTextTitle: "The transcript is wrong? Type what you said",
  tutor: "Tutor",
  hearLineExpected: "Hear this line with the expected accent",
  reportSaved: (n: number) => `Saved — thanks. ${n} labelled phrases of your voice so far.`,
  correctedText: "Corrected text of this line",
  saveRecheck: "Save and re-check",
  cancel: "Cancel",
  checkingLine: "Checking this line again…",
  everything: "Everything you said",
  show: "Show",
  allLines: "All lines",
  linesMistakes: "Lines with mistakes",
  linesUnclear: "Lines with unclear phrases",
  keysHelp: ["Click a phrase for details. Keys: ", " next mistake, ", " previous."] as [string, string, string],
  lessonTitle: "Lesson title",
  allLessons: "← All lessons",
  reviewAppears: "The review appears here when the analysis is done.",
  recheckCurrent: "Re-check with the current settings",
  outdatedLesson: "This lesson was analyzed before you changed NHK accents or Platina got a new model. ",
  couldntOpen: (m: string) => `Couldn't open this lesson: ${m}`,
  uploading: (name: string) => `Uploading ${name}…`,
  uploaded: "Uploaded. Platina is analyzing it; the progress bar below shows how far it is.",
  couldntUseFile: (m: string) => `Couldn't use this file: ${m}`,
  minutes: (m: number) => (m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${pad(m % 60)} min`),
  underMinute: "under 1 min",
  zeroMinutes: "0 min",

  // Progress tab
  yourLevel: "Your level",
  levelAppears: (judged: number, min: number) =>
    `Appears after a lesson with at least ${judged} judged phrases and ${min} minutes of your speech.`,
  levelAverage: "Average of your last 3 counted lessons.",
  change: "Change",
  changeLater: "Shown once 4 lessons count.",
  changeSince: "Since your first 3 counted lessons.",
  youveSpoken: "You've spoken",
  inLessons: (n: number) => `In ${n} ${plural(n, "lesson")}.`,
  chartAria: "Your level in each lesson. The same numbers are in the table below.",
  pointTitle: (date: string, title: string, level: number, lo: number, hi: number, judged: number, reliable: boolean) =>
    `${date} · ${title} · level ${level} (likely ${lo}–${hi}) · ${judged} phrases judged` +
    (reliable ? "" : " · too short to count"),
  barsAria: "Minutes you spoke in each lesson.",
  minutesShort: (m: number) => `${m}m`,
  countedKey: "counted lesson (line: likely range)",
  spokeCaption: "Minutes you spoke in each lesson",
  progressHeaders: ["Lesson", "Level", "Likely range", "Correct", "Judged phrases", "You spoke", "Counted"],
  yes: "yes",
  noTooShort: "no, too short",
  showTable: "Show as table",
  wrongBefore: (n: number) => `wrong ${n} ${plural(n, "time")} before, right since`,
  wrongOf: (w: number, total: number, lessons: number) =>
    `wrong ${w} of ${total} times, in ${lessons} ${plural(lessons, "lesson")}`,
  lastMistake: "last mistake",
  latestMistake: "latest mistake",
  kindHeaders: ["Lesson", "Flat phrases right", "Accented phrases right", "Said flat instead of a drop",
    "Added a drop to a flat word", "Drop 1 mora off", "Drop 2+ moras off"],
  byKind: "By kind of mistake",
  byKindIntro: "Which accents give you trouble: flat (平板) words or words with a drop, and what the mistake was.",
  noLessonsProgress: ["No lessons yet. Record your first one in ", "."] as [string, string],
  countsWhen: (judged: number, min: number) =>
    `A lesson counts in your progress once Platina could judge at least ${judged} of your phrases ` +
    `and you spoke for ${min} minutes or more.`,
  recheckThem: "Re-check them",
  queued: (n: number) => `${n} ${plural(n, "lesson")} queued. Progress updates when they're done.`,
  outdatedLessons: (n: number) =>
    `${n} ${plural(n, "lesson was", "lessons were")} analyzed with older NHK accents or an older model, ` +
    "so they aren't fully comparable. ",
  levelPerLesson: "Level per lesson",
  workOn: "Words to work on",
  workOnIntro: "Wrong in two or more lessons, or three or more times.",
  workOnEmpty: "Nothing yet. Words you keep getting wrong show up here.",
  fixed: "Fixed",
  fixedIntro: "Words you used to get wrong and have said right three times in a row since.",
  fixedEmpty: "Nothing yet. Keep going!",
  progressLevelExplain: "Each lesson's level is the lowest value your share of correctly accented phrases is likely " +
    "to be. It grows with how much you said: two correct phrases give about 42, 19 of 20 about 80, 285 of 300 about " +
    "92. So staying quiet can't score high, and speaking a lot only helps when the accents are right. Only phrases " +
    "Platina could judge count. Unclear phrases and words whose dictionary accent is unsure don't count either way.",

  // Quick check and Type tabs
  quickIntro: "One-off recordings to check a sentence or experiment. They aren't saved and don't count in your " +
    "lessons or progress.",
  record: "● Record",
  recordAgain: "● Record again",
  stop: "■ Stop",
  uploadAudio: "Upload audio",
  readingSummary: "Reading a known text? Paste it here (optional, more reliable than transcription)",
  micUnavailable: (m: string) => `Microphone unavailable: ${m}`,
  recordingTalk: "Recording… read aloud or just talk.",
  analyzing: "Analyzing… (the first run loads the speech models, ~30 s)",
  analysisFailed: (m: string) => `Analysis failed: ${m}`,
  noSpeech: "No speech recognized.",
  summaryCount: (n: number, label: string) => `${n} ${label.toLowerCase()}`,
  hearSentenceYourself: "Hear yourself say this sentence",
  hearSentenceExpected: "Hear this sentence with the expected accent",
  recheckRecording: "Re-check this recording",
  showAccents: "Show accents",
  nhkNotation: "NHK notation",
  saveGold: "Save as NHK-checked test sentence",
  goldAdded: "Added to backend/tests/gold/sentences.yaml",
  listen: "Listen",
  slow: "Slow",
  goldSummary: "Checked this sentence in NHK? Save it as a test case",
  goldHelp: "Correct the notation below if NHK differs (＼ after the drop, ━ for flat, spaces between phrases).",

  // My NHK accents tab
  backToLesson: "← Back to lesson",
  nhkIntro: "Accents you checked in the NHK 日本語発音アクセント新辞典 override every other source. Enter the " +
    "dictionary form and its accent number(s); conjugated forms and phrases follow automatically.",
  lemma: "Dictionary form",
  reading: "Reading",
  accentNumbers: "Accent number(s)",
  accentPlaceholder: "0  or  0,2",
  note: "Note",
  optional: "optional",
  save: "Save",
  wordsToCheck: "Words to check",
  wordsToCheckIntro: "Words from your recordings whose accent the dictionaries disagree on.",
  savedHeading: "Saved",
  savedCount: (n: number) => `(${n})`,
  searchSaved: "Search saved words",
  showAllSaved: (n: number) => `Show all ${n}`,
  showFewer: "Show fewer",
  noSavedMatch: "No saved word matches.",
  variantsTitle: "Accents natives use (to review)",
  variantsIntro: "Found in recordings of 100 native speakers but not in the dictionaries. Proposed ones are never " +
    "counted as your mistake (grey). Check them in NHK: approve to accept them, reject to ignore them.",
  unidicSays: (a: string) => `UniDic says ${a}`,
  accentsInvalid: "Accent numbers must be whole numbers like 0 or 0,2.",
  nhkSaved: "Saved. Re-check a recording or text to see it applied.",
  accent: "Accent",
  nothingYetRecord: "Nothing yet — record something first.",
  phrase: "Phrase",
  nativesSay: "Natives say",
  speakers: "Speakers",
  status: "Status",
  approve: "Approve",
  reject: "Reject",
  variantStatus: { proposed: "proposed", approved: "approved", rejected: "rejected" } as Record<string, string>,
  noVariants: "None yet (tools/mine_variants.py).",

  // Practice tab
  practiceIntro: "Say the sentence with the target accent — sometimes the right one, sometimes a deliberate " +
    "mistake. Keep a take only if it sounds like the target (trust your ear and the tutor, not Platina's " +
    "verdict). These labelled takes measure how often Platina misjudges your voice, and train it.",
  anotherSentence: "Another sentence",
  ownSentence: "or type your own sentence",
  useIt: "Use it",
  reviewTitle: "Review native recordings",
  reviewIntro: "Native speakers' phrases that Platina would have flagged. Was it the speaker, Platina, or the " +
    "dictionary?",
  startReviewing: "Start reviewing",
  practiceStats: (n: number, c: number, m: number, s: number) =>
    `${n} labelled phrases of your voice (${c} correct, ${m} deliberate mistakes) ` +
    `over ${s} ${plural(s, "session")}. Aim: ~300 of each.`,
  couldntLoad: (m: string) => `Couldn't load a sentence: ${m}`,
  sayAs: ["Say ", " as "] as [string, string],
  deliberate: (kind: string) => ` — a deliberate mistake (${kind})`,
  kind: { "said flat": "said flat", "added a drop": "added a drop", "1 mora off": "1 mora off",
    "2+ moras off": "2+ moras off" } as Record<Kind, string>,
  theExpected: " — the expected accent",
  hearTarget: "Hear the target",
  hearTargetTitle: "The tutor says the sentence with this accent",
  recordingSentence: "Recording… say the whole sentence.",
  listenBack: "Listen back. Keep it only if it sounds like the target.",
  myTake: "My take",
  keep: "Keep — I said it like the target",
  saving: "Saving…",
  saved: "Saved.",
  couldntSave: (m: string) => `Couldn't save: ${m}`,
  skip: "Skip",
  nothingToReview: "Nothing to review. Build a queue with tools/review_queue.py (needs a corpus cache).",
  phraseBtn: "Phrase",
  wholeSentence: "Whole sentence",
  reviewChoices: { variant: "Native said another accent", misheard: "Platina misheard",
    dictionary: "Dictionary is wrong", unsure: "Can't tell" },
  expectedHeard: ["Expected ", " · Platina heard "] as [string, string],
  left: (n: number) => `${n} left`,

  // phrases, verdicts, details panel
  status_correct: "Correct",
  status_error: "Mistake",
  status_uncertain: "Unclear",
  status_unverified: "Check the dictionary",
  conf_nhk: "checked by you in NHK",
  conf_agree: "UniDic and OpenJTalk agree",
  conf_uncertain: "dictionaries disagree / unknown — not counted as your mistake",
  pitchDrop: "pitch drop",
  flatAria: "flat (heiban)",
  youColon: "you: ",
  likely: (p: number) => ` (${p}% likely you said the expected accent)`,
  vSaidAsOne: "matches, said in one breath with the neighbouring phrase (natives often do).",
  vMatches: (pct: string) => `matches the dictionary${pct}.`,
  vError: (pct: string) => `your accent sounds different from the dictionary${pct}.`,
  vNativeVariant: "differs from the dictionary, but many native speakers say it this way too.",
  vUnconfirmed: (pct: string) =>
    `sounds different, but the dictionary accent itself isn't confirmed — check it in NHK${pct}.`,
  vAlignment: "the moras that decide this didn't line up well with the audio, so it isn't judged.",
  vUnclear: (pct: string) => `no accent was heard clearly enough to call it a mistake${pct}.`,
  vNoPitch: "couldn't measure the pitch here (devoiced vowels, noise, or the words didn't line up with the audio).",
  verdictLine: (label: string, text: string) => `${label}: ${text}`,
  keyMeasured: "your pitch (semitones)",
  keyExpected: "dictionary high/low",
  keyNative: "typical native pitch",
  pitchOf: (t: string) => `pitch of ${t}`,
  high: "high",
  low: "low",
  unvoiced: "unvoiced",
  tooltip: (mora: string, you: string, dict: string) => `${mora}  you: ${you}  ·  dictionary: ${dict}`,
  mora: "Mora",
  dictionary: "Dictionary",
  yourPitch: "Your pitch (semitones)",
  word: "Word",
  source: "Source",
  sourceOverride: "NHK (checked by you)",
  sourceNone: "none",
  setFromNhk: "Set from NHK",
  play: "Play",
  hearPhraseYourself: "Hear yourself say this phrase",
  expectedRow: "Expected",
  hearThisAccent: "Hear this accent",
  alsoOk: "Also OK",
  nativesAlso: "Natives also say",
  youSaidRow: "You said",
  hearYourAccent: "Hear the accent you used, in the tutor's voice",
  expectedSource: (c: string) => `Expected accent: ${c}`,
  wrongVerdict: "Wrong verdict? Tell Platina what you said",
  iSaidThis: "I said this",
  notSure: "Not sure",
  iSaid: "I said:",
  reasonNoData: (words: string) => `no accent data for ${words}`,
  reasonUnknownRule: "unknown accent rule",
  reasonNoReading: "no reading",
  reasonSplit: "dictionaries split this phrase differently",
  reasonReading: "dictionaries disagree on the reading",
  reasonUse: (word: string, use: string) =>
    `NHK accent for ${word} ${({ modified: "after a modifier (優しい人)", unmodified: "without a modifier",
      noun: "as a noun", adverb: "used as an adverb" } as Record<string, string>)[use] ?? use}`,
  reasonForm: (word: string) => `this form of ${word} as NHK lists it`,
  reasonDisagree: (u: string, o: string) => `dictionaries disagree: UniDic ${u}, OpenJTalk ${o}`,
  reasonOtherReading: (word: string, reading: string) => `${word} could also be read ${reading}`,
  reasonHintUnmet: (reading: string, word: string) =>
    `no dictionary reads ${word} as ${reading}; using the dictionary's reading`,
  readAs: "Other readings",
  readAsTitle: (word: string, reading: string) => `Read ${word} as ${reading} (adds ${word}{${reading}} to the text)`,
  typeHint: "Wrong reading? Write it after the kanji in braces: 日本{にっぽん}語",

  // tutor voice
  tutorUnavailable: (m: string) => `Tutor voice unavailable — ${m}`,
  couldntPlay: (m: string) => `Couldn't play: ${m}`,
  tutorCredit: (c: string) => `Tutor voice: ${c}`,

  // legend under every tab
  legendDrop: "pitch drops after this mora",
  legendFlat: "stays high to the end (flat / 平板)",
  legendRed: "red",
  legendRedText: "= your accent differs",
  legendGrey: "grey",
  legendGreyText: "= dictionary unsure, not counted",
};

type Dict = typeof en;

const ja: Dict = {
  langToggle: "English",
  langToggleTitle: "Switch the interface to English",
  tagline: "日本語アクセントコーチ",
  navSections: "メニュー",
  navMyLessons: "マイレッスン",
  tabLessons: "レッスン",
  tabProgress: "上達の記録",
  navWorkshop: "ラボ",
  navWorkshopHint: "その場のチェックや実験に",
  tabQuickCheck: "クイックチェック",
  tabType: "テキストで確認",
  tabNhk: "NHKアクセント登録",
  tabPractice: "練習",

  lessonsIntro: "授業を録音しておけば、終わったあとでアクセントを振り返れます。明らかな間違い、何度も出た間違い、" +
    "話した内容のすべてをチェックできます。録音には自分の声だけが入るよう、ヘッドホンをお使いください。",
  lessonRecord: "● レッスンの録音を開始",
  lessonStop: "■ 停止して分析",
  lessonUpload: "録音ファイルをアップロード",
  microphone: "マイク",
  yourLessons: "これまでのレッスン",
  defaultLessonTitle: (d: Date) =>
    `レッスン ${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`,
  cantReach: "Platinaに接続できません。./start.sh で起動しているか確認してください。",
  savedUpTo: (t: string) => `${t} まで保存済み`,
  recordingBackground: "録音中です。授業中はほかのタブやアプリに切り替えても大丈夫です。",
  retrying: (n: number) => `Platinaに接続できません。再接続しています（未送信 ${n} 件）。このページは閉じないでください。`,
  micUnavailableLesson: (m: string) =>
    `マイクを使用できません（${m}）。このページでのマイクの使用を許可してから、もう一度お試しください。`,
  nothingSavedYet: "まだ保存されていません（最初の保存は15秒後）",
  savingLastPiece: "残りを保存しています…",
  lessonSavedAnalyzing: "保存しました。現在レッスンを分析中です。進行状況は下のバーで確認できます。" +
    "このページは閉じても大丈夫です。",
  couldntFinish: (m: string) => `録音を終了できませんでした：${m}`,
  recordingNow: "録音中",
  analyzeSaved: "保存済みの部分を分析",
  couldnt: (m: string) => `失敗しました：${m}`,
  interrupted: "録音が中断されました。",
  waitingAnalysis: "分析待ち…",
  analyzingLine: (done: number, total: number) => `分析中… ${done} / ${total} 行`,
  findingSpeech: "発話部分を検出しています…",
  tryAgain: "再試行",
  somethingWrong: (m: string) => `エラーが発生しました：${m} `,
  levelBadge: (l: number) => `レベル ${l}`,
  mistakesIn: (m: number, j: number) => ` · ${j}フレーズ中 間違い${m}件`,
  tooShort: "短いため集計対象外",
  olderAnalysis: "旧バージョンで分析",
  noLessons: "まだレッスンがありません。次の授業の前に「レッスンの録音を開始」を押すか、録音ファイルをアップロードしてください。",
  recorded: (d: string) => `録音時間 ${d}`,
  youSpokeFor: (d: string) => `発話時間 ${d}`,
  delete: "削除",
  deleteNamed: (t: string) => `「${t}」を削除`,
  confirmDelete: (t: string) => `「${t}」を削除しますか？ 録音と振り返りの内容はすべて削除され、元に戻せません。`,
  summary: "まとめ",
  levelRange: (lo: number, hi: number) => `レベル（推定範囲 ${lo}〜${hi}）`,
  mistakes: "間違い",
  unclearNotCounted: "判定不可（集計対象外）",
  youSpoke: "発話時間",
  shortLessonNote: "短いレッスンのため、上達の記録には含まれません（フレーズ数が少ないと、レベルを正確に出せないためです）。" +
    "結果はここで確認できます。",
  howLevel: "レベルの決まり方",
  lessonLevelExplain: (judged: number, correct: number, acc: number | null) =>
    `Platinaが判定できた${judged}フレーズのうち、正しいアクセントで言えたのは${correct}フレーズでした` +
    (acc === null ? "。" : `（${acc}%）。`) +
    "レベルは、この正答率を控えめに見積もった値（統計的な下限）です。そのため、たくさん話すほど高くなりやすくなります。" +
    "たとえば、2フレーズすべて正解なら約42、20中19なら約80、300中285なら約92です。" +
    "判定不可のフレーズと、辞書のアクセントがはっきりしない語は計算に含めません。",
  expected: "正解",
  youSaid: "あなた",
  mostObvious: "明らかな間違い",
  noClearMistakes: "このレッスンに明らかな間違いはありませんでした。",
  obviousIntro: "アクセントが違うとPlatinaが強く判断したフレーズです。",
  you: "自分",
  hearYourselfSayIt: "自分の発音を聞く",
  goTo: (t: string) => `${t} へ移動`,
  showLine: "文字起こしでこの行を表示",
  expectedBtn: "正解",
  hearExpected: "正しいアクセントを聞く",
  repeated: "何度も出た間違い",
  noRepeated: "2回以上出た間違いはありません。",
  hearYourselfAt: (t: string) => `${t} の自分の発音を聞く`,
  goToLine: "その行へ",
  hearEachTime: "すべて聞く",
  hearThisLine: (t: string) => `この行を聞く（${t}）`,
  skipped: (why: string) => (why === "not Japanese" ? "日本語以外のため判定なし" : "音声なしのため判定なし"),
  textFixed: "手動で修正済み",
  editText: "テキストを修正",
  editTextTitle: "文字起こしが間違っていますか？ 実際に話した内容を入力してください",
  tutor: "お手本",
  hearLineExpected: "この行を正しいアクセントで聞く",
  reportSaved: (n: number) => `保存しました。ご協力ありがとうございます！ これまでに集まったあなたの音声：${n}フレーズ`,
  correctedText: "この行の正しいテキスト",
  saveRecheck: "保存して再判定",
  cancel: "キャンセル",
  checkingLine: "この行を再判定しています…",
  everything: "話した内容すべて",
  show: "表示",
  allLines: "すべての行",
  linesMistakes: "間違いのある行",
  linesUnclear: "判定不可のフレーズがある行",
  keysHelp: ["フレーズをクリックすると詳細を表示します。ショートカット：", " 次の間違い　", " 前の間違い"] as [string, string, string],
  lessonTitle: "レッスン名",
  allLessons: "← レッスン一覧",
  reviewAppears: "分析が終わると、ここに結果が表示されます。",
  recheckCurrent: "現在の設定で再判定",
  outdatedLesson: "このレッスンは、NHKアクセントの変更前、またはPlatinaのモデル更新前に分析されたものです。",
  couldntOpen: (m: string) => `このレッスンを開けませんでした：${m}`,
  uploading: (name: string) => `${name} をアップロード中…`,
  uploaded: "アップロードしました。現在分析中です。進行状況は下のバーで確認できます。",
  couldntUseFile: (m: string) => `このファイルは読み込めません：${m}`,
  minutes: (m: number) => (m < 60 ? `${m}分` : `${Math.floor(m / 60)}時間${pad(m % 60)}分`),
  underMinute: "1分未満",
  zeroMinutes: "0分",

  yourLevel: "あなたのレベル",
  levelAppears: (judged: number, min: number) =>
    `判定できたフレーズが${judged}以上、発話時間が${min}分以上のレッスンを録音すると表示されます。`,
  levelAverage: "直近3レッスン（集計対象）の平均",
  change: "変化",
  changeLater: "集計対象のレッスンが4回分たまると表示されます。",
  changeSince: "最初の3レッスン（集計対象）との比較",
  youveSpoken: "累計発話時間",
  inLessons: (n: number) => `${n}レッスン分`,
  chartAria: "レッスンごとのレベル。同じ数値を下の表でも確認できます。",
  pointTitle: (date: string, title: string, level: number, lo: number, hi: number, judged: number, reliable: boolean) =>
    `${date} · ${title} · レベル ${level}（推定範囲 ${lo}〜${hi}）· ${judged}フレーズを判定` +
    (reliable ? "" : " · 短いため集計対象外"),
  barsAria: "レッスンごとの発話時間（分）",
  minutesShort: (m: number) => `${m}分`,
  countedKey: "集計対象のレッスン（縦線：推定範囲）",
  spokeCaption: "レッスンごとの発話時間（分）",
  progressHeaders: ["レッスン", "レベル", "推定範囲", "正答率", "判定フレーズ数", "発話時間", "集計"],
  yes: "対象",
  noTooShort: "対象外（短い）",
  showTable: "表で見る",
  wrongBefore: (n: number) => `以前は${n}回間違い、その後は正解が続いています`,
  wrongOf: (w: number, total: number, lessons: number) => `${total}回中${w}回間違い（${lessons}レッスン）`,
  lastMistake: "最後に間違えた箇所",
  latestMistake: "直近の間違い",
  kindHeaders: ["レッスン", "平板型の正答率", "起伏型の正答率", "起伏型を平板で発音",
    "平板型に下がり目を付けた", "下がり目が1モーラずれ", "下がり目が2モーラ以上ずれ"],
  byKind: "間違いの種類別",
  byKindIntro: "平板型と起伏型（下がり目のある語）のどちらが苦手か、どんな間違いが多いかがわかります。",
  noLessonsProgress: ["まだレッスンがありません。まずは「", "」で最初のレッスンを録音しましょう。"] as [string, string],
  countsWhen: (judged: number, min: number) =>
    `判定できたフレーズが${judged}以上で、${min}分以上話したレッスンが上達の記録の対象になります。`,
  recheckThem: "再判定する",
  queued: (n: number) => `${n}件のレッスンを再判定します。完了すると記録が更新されます。`,
  outdatedLessons: (n: number) =>
    `${n}件のレッスンは古いNHKアクセントまたは旧モデルで分析されているため、ほかのレッスンと単純には比較できません。`,
  levelPerLesson: "レッスンごとのレベル",
  workOn: "苦手な語",
  workOnIntro: "2回以上のレッスンで間違えた語、または合計3回以上間違えた語です。",
  workOnEmpty: "まだありません。何度も間違える語があると、ここに表示されます。",
  fixed: "克服した語",
  fixedIntro: "以前は間違えていたけれど、その後3回続けて正しく言えた語です。",
  fixedEmpty: "まだありません。この調子でがんばりましょう！",
  progressLevelExplain: "各レッスンのレベルは、正しいアクセントで言えたフレーズの割合を控えめに見積もった値（統計的な下限）です。" +
    "そのため、たくさん話すほど高くなりやすくなります。たとえば、2フレーズすべて正解なら約42、20中19なら約80、300中285なら約92です。" +
    "黙っていては高いレベルにならず、たくさん話してもアクセントが合っていなければ上がりません。" +
    "計算に使うのはPlatinaが判定できたフレーズだけで、判定不可のフレーズと、辞書のアクセントがはっきりしない語は含めません。",

  quickIntro: "文をさっと確認したり、いろいろ試したりするための録音です。保存されず、レッスンや上達の記録にも影響しません。",
  record: "● 録音",
  recordAgain: "● 録音し直す",
  stop: "■ 停止",
  uploadAudio: "音声をアップロード",
  readingSummary: "読み上げる文が決まっている場合は、ここに貼り付けてください（任意。音声認識より正確になります）",
  micUnavailable: (m: string) => `マイクを使用できません：${m}`,
  recordingTalk: "録音中… 音読でも、自由に話してもOKです。",
  analyzing: "分析中…（初回は音声モデルの読み込みに30秒ほどかかります）",
  analysisFailed: (m: string) => `分析に失敗しました：${m}`,
  noSpeech: "音声を認識できませんでした。",
  summaryCount: (n: number, label: string) => `${label} ${n}`,
  hearSentenceYourself: "この文の自分の発音を聞く",
  hearSentenceExpected: "この文を正しいアクセントで聞く",
  recheckRecording: "この録音を再判定",
  showAccents: "アクセントを表示",
  nhkNotation: "NHK式の表記",
  saveGold: "NHKで確認済みのテスト文として保存",
  goldAdded: "backend/tests/gold/sentences.yaml に追加しました",
  listen: "聞く",
  slow: "ゆっくり",
  goldSummary: "NHKで確認した文をテストケースとして保存",
  goldHelp: "NHKと異なる場合は、下の表記を修正してください（下がり目の直後に＼、平板は━、フレーズの間は半角スペース）。",

  backToLesson: "← レッスンに戻る",
  nhkIntro: "『NHK日本語発音アクセント新辞典』で確認したアクセントは、ほかのどの辞書よりも優先されます。" +
    "辞書形とアクセント型を登録すると、活用形やフレーズにも自動で反映されます。",
  lemma: "辞書形",
  reading: "読み",
  accentNumbers: "アクセント型（数字）",
  accentPlaceholder: "0 または 0,2",
  note: "メモ",
  optional: "任意",
  save: "保存",
  wordsToCheck: "要確認の語",
  wordsToCheckIntro: "録音に出てきた語のうち、辞書によってアクセントが異なるものです。",
  savedHeading: "登録済み",
  savedCount: (n: number) => `（${n}語）`,
  searchSaved: "登録した語を検索",
  showAllSaved: (n: number) => `すべて表示（${n}語）`,
  showFewer: "折りたたむ",
  noSavedMatch: "該当する語はありません。",
  variantsTitle: "ネイティブが使うアクセント（要確認）",
  variantsIntro: "ネイティブ話者100人の録音で見つかったものの、辞書には載っていないアクセントです。「提案中」のものは" +
    "間違いとして数えません（灰色で表示）。NHKで確認して、正しければ承認、そうでなければ却下してください。",
  unidicSays: (a: string) => `UniDic：${a}`,
  accentsInvalid: "アクセント型は 0 や 0,2 のように数字で入力してください。",
  nhkSaved: "保存しました。録音やテキストを再判定すると反映されます。",
  accent: "アクセント",
  nothingYetRecord: "まだありません。まずは何か録音してみましょう。",
  phrase: "フレーズ",
  nativesSay: "ネイティブの発音",
  speakers: "話者数",
  status: "状態",
  approve: "承認",
  reject: "却下",
  variantStatus: { proposed: "提案中", approved: "承認済み", rejected: "却下済み" },
  noVariants: "まだありません（tools/mine_variants.py）。",

  practiceIntro: "指定されたアクセントで文を読んでください。正しいアクセントのときと、わざと間違えるときがあります。" +
    "指定どおりに言えた録音だけを残しましょう（Platinaの判定ではなく、自分の耳とお手本を信じてください）。" +
    "集めた録音は、Platinaがあなたの声をどのくらい誤判定するかの測定と、Platinaの学習に使われます。",
  anotherSentence: "別の文にする",
  ownSentence: "または自分で文を入力",
  useIt: "この文を使う",
  reviewTitle: "ネイティブの録音をチェック",
  reviewIntro: "Platinaが間違いと判定しかけた、ネイティブ話者のフレーズです。原因は話者、Platina、辞書のどれでしょう？",
  startReviewing: "チェックを始める",
  practiceStats: (n: number, c: number, m: number, s: number) =>
    `集まったあなたの音声：${n}フレーズ（正しいアクセント${c}、わざと間違えたもの${m}）・${s}セッション。目標はそれぞれ約300です。`,
  couldntLoad: (m: string) => `文を読み込めませんでした：${m}`,
  sayAs: ["", " を "] as [string, string],
  deliberate: (kind: string) => ` で言ってください（わざと間違える：${kind}）`,
  kind: { "said flat": "平板にする", "added a drop": "下がり目を付ける", "1 mora off": "1モーラずらす",
    "2+ moras off": "2モーラ以上ずらす" },
  theExpected: " で言ってください（正しいアクセント）",
  hearTarget: "お手本を聞く",
  hearTargetTitle: "このアクセントでお手本が読み上げます",
  recordingSentence: "録音中… 文全体を読んでください。",
  listenBack: "再生して、指定どおりに聞こえたら残してください。",
  myTake: "自分の録音",
  keep: "残す（指定どおりに言えた）",
  saving: "保存中…",
  saved: "保存しました。",
  couldntSave: (m: string) => `保存できませんでした：${m}`,
  skip: "スキップ",
  nothingToReview: "チェックするものはありません。tools/review_queue.py でリストを作成してください（コーパスのキャッシュが必要です）。",
  phraseBtn: "フレーズ",
  wholeSentence: "文全体",
  reviewChoices: { variant: "ネイティブが別のアクセントで言った", misheard: "Platinaの聞き間違い",
    dictionary: "辞書の誤り", unsure: "判断できない" },
  expectedHeard: ["正解 ", " · Platinaの判定 "] as [string, string],
  left: (n: number) => `残り ${n}`,

  status_correct: "正解",
  status_error: "間違い",
  status_uncertain: "判定不可",
  status_unverified: "辞書を確認",
  conf_nhk: "あなたがNHKで確認済み",
  conf_agree: "UniDicとOpenJTalkで一致",
  conf_uncertain: "辞書間で一致しない／不明のため、間違いとしては数えません",
  pitchDrop: "下がり目",
  flatAria: "平板",
  youColon: "あなた：",
  likely: (p: number) => `（正しいアクセントで言えた確率 ${p}%）`,
  vSaidAsOne: "OKです。となりのフレーズとひと続きで言っています（ネイティブにもよくある言い方です）。",
  vMatches: (pct: string) => `辞書どおりです${pct}。`,
  vError: (pct: string) => `辞書とは違うアクセントに聞こえます${pct}。`,
  vNativeVariant: "辞書とは違いますが、ネイティブにもよく聞かれる言い方です。",
  vUnconfirmed: (pct: string) => `違って聞こえますが、辞書のアクセント自体が確定していません。NHKで確認してください${pct}。`,
  vAlignment: "判定に必要なモーラの位置を音声の中で特定できなかったため、判定していません。",
  vUnclear: (pct: string) => `アクセントがはっきり聞き取れなかったため、間違いとは判定していません${pct}。`,
  vNoPitch: "この部分はピッチを測定できませんでした（母音の無声化や雑音、または文字と音声の対応づけに失敗したため）。",
  verdictLine: (label: string, text: string) => `${label}：${text}`,
  keyMeasured: "あなたのピッチ（半音）",
  keyExpected: "辞書の高低",
  keyNative: "ネイティブの平均的なピッチ",
  pitchOf: (t: string) => `${t} のピッチ`,
  high: "高",
  low: "低",
  unvoiced: "無声",
  tooltip: (mora: string, you: string, dict: string) => `${mora}  あなた：${you}  ·  辞書：${dict}`,
  mora: "モーラ",
  dictionary: "辞書",
  yourPitch: "あなたのピッチ（半音）",
  word: "語",
  source: "出典",
  sourceOverride: "NHK（自分で確認）",
  sourceNone: "なし",
  setFromNhk: "NHKのアクセントを登録",
  play: "再生",
  hearPhraseYourself: "このフレーズの自分の発音を聞く",
  expectedRow: "正解",
  hearThisAccent: "このアクセントを聞く",
  alsoOk: "これもOK",
  nativesAlso: "ネイティブはこうも言う",
  youSaidRow: "あなた",
  hearYourAccent: "あなたのアクセントをお手本の声で聞く",
  expectedSource: (c: string) => `正解の根拠：${c}`,
  wrongVerdict: "判定が違う？ 実際の発音をPlatinaに教える",
  iSaidThis: "こう言った",
  notSure: "わからない",
  iSaid: "実際の発音：",
  reasonNoData: (words: string) => `${words} のアクセント情報なし`,
  reasonUnknownRule: "アクセント規則が不明",
  reasonNoReading: "読みが不明",
  reasonSplit: "辞書によってフレーズの区切り方が違う",
  reasonReading: "辞書によって読みが違う",
  reasonUse: (word: string, use: string) =>
    `${({ modified: "修飾語を伴う", unmodified: "修飾語を伴わない", noun: "名詞としての",
      adverb: "副詞としての" } as Record<string, string>)[use] ?? use}${word}のNHKアクセント`,
  reasonForm: (word: string) => `NHKに載っている${word}の活用形`,
  reasonDisagree: (u: string, o: string) => `辞書間で不一致：UniDic ${u}、OpenJTalk ${o}`,
  reasonOtherReading: (word: string, reading: string) => `${word}は「${reading}」とも読める`,
  reasonHintUnmet: (reading: string, word: string) => `${word}を「${reading}」と読む辞書がないため、辞書の読みを使用`,
  readAs: "ほかの読み方",
  readAsTitle: (word: string, reading: string) => `${word}を「${reading}」と読む（文に${word}{${reading}}を追加）`,
  typeHint: "読み方が違うときは、漢字の後に { } で書いてください：日本{にっぽん}語",

  tutorUnavailable: (m: string) => `お手本の音声を利用できません：${m}`,
  couldntPlay: (m: string) => `再生できませんでした：${m}`,
  tutorCredit: (c: string) => `お手本の音声：${c}`,

  legendDrop: "このモーラの後で下がる",
  legendFlat: "最後まで下がらない（平板型）",
  legendRed: "赤",
  legendRedText: "＝アクセントが違う",
  legendGrey: "灰色",
  legendGreyText: "＝辞書が不確かなため集計しない",
};

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

const DICTS: Record<Lang, Dict> = { en, ja };
const KEY = "platina-lang";

function initial(): Lang {
  try {
    const l = localStorage.getItem(KEY);
    if (l === "en" || l === "ja") return l;
  } catch { /* storage blocked: browser language */ }
  return navigator.language.toLowerCase().startsWith("ja") ? "ja" : "en";
}

let current: Lang = initial();

export const lang = (): Lang => current;
/** The strings for the current language. */
export const tr = (): Dict => DICTS[current];
/** For toLocaleString and friends. */
export const locale = (): string | undefined => (current === "ja" ? "ja-JP" : undefined);

export function setLang(l: Lang): void {
  current = l;
  try {
    localStorage.setItem(KEY, l);
  } catch { /* storage blocked: not remembered */ }
  applyStatic();
}

/** Fills in every data-i18n* element of the page. */
export function applyStatic(): void {
  const d = tr() as unknown as Record<string, unknown>;
  const text = (key: string | undefined) => (key && typeof d[key] === "string" ? (d[key] as string) : null);
  document.documentElement.lang = current;
  document.querySelectorAll<HTMLElement>("[data-i18n]").forEach((n) => {
    const s = text(n.dataset.i18n);
    if (s !== null) n.textContent = s;
  });
  for (const attr of ["placeholder", "title", "aria-label"]) {
    document.querySelectorAll<HTMLElement>(`[data-i18n-${attr}]`).forEach((n) => {
      const s = text(n.getAttribute(`data-i18n-${attr}`) ?? undefined);
      if (s !== null) n.setAttribute(attr, s);
    });
  }
}

/** The engine's reasons for an uncertain accent (backend/app/accent/engine.py) in the UI language. */
export function reason(r: string): string {
  const d = tr();
  let m: RegExpMatchArray | null;
  if ((m = r.match(/^no accent data for (.+)$/))) return d.reasonNoData(m[1]);
  if ((m = r.match(/^NHK (modified|unmodified|noun|adverb) use of (.+)$/))) return d.reasonUse(m[2], m[1]);
  if ((m = r.match(/^NHK form of (.+)$/))) return d.reasonForm(m[1]);
  if ((m = r.match(/^dictionaries disagree: UniDic (.+), OpenJTalk (.+)$/))) return d.reasonDisagree(m[1], m[2]);
  if ((m = r.match(/^other reading possible: (\S+) (\S+)$/))) return d.reasonOtherReading(m[1], m[2]);
  if ((m = r.match(/^reading (\S+) not in dictionary for (.+)$/))) return d.reasonHintUnmet(m[1], m[2]);
  const fixed: Record<string, string> = {
    "unknown accent rule": d.reasonUnknownRule,
    "no reading": d.reasonNoReading,
    "dictionaries split this phrase differently": d.reasonSplit,
    "dictionaries disagree on the reading": d.reasonReading,
  };
  return fixed[r] ?? r;
}

/** A practice target's kind of mistake (backend/app/main.py practice_next). */
export function kindLabel(k: string): string {
  return (tr().kind as Record<string, string>)[k] ?? k;
}
