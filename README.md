# AI-Powered Anki Flashcard Generator

A streamlined web application that automatically generates high-quality language learning flashcards and syncs them directly to your local Anki application. 

Instead of manually searching for translations, conjugations, and downloading audio files, you simply type a word, and the AI handles the rest.

## 🚀 Key Features

- **Multi-Language Support**: Currently supports Italian, Spanish, French, German, and Japanese.
- **Five-Stage Grammar Mastery**: Interpretation (Processing Instruction), recognition, controlled production, free use, and speaking — with scenario roleplay, mistake-category explanations, and error-driven topic recommendations.
- **Smart Generation**: Powered by a quality-first Gemini fallback chain, it automatically generates:
  - Direct translations (in English, Persian, or both).
  - Contextual example sentences.
  - Grammatical gender and part of speech.
  - Full verb conjugations.
  - Common noun, verb, adjective, and adverb word-family forms, each with its own example.
  - A clear note when a related part of speech has no natural common form.
  - One or two common collocations and a compact part-of-speech-specific Italian grammar summary.
- **Active Recall**: Optionally creates a second card from the same Anki note, with a meaning cue and sentence gap on the Front and the Italian answer on the Back.
- **Card graduation — recognition first, production when ready**: research on retrieval formats shows production cards stick better but cost about twice the review time, so the evidence-backed sequence is recognition first. The Grammar Deck's Today panel ("Cards that grow up") holds back each new word's production card until Anki's own review data shows the recognition card is maturing (3+ reviews), then releases it. Anki/FSRS scheduling is never modified — graduation only toggles the app-owned production cards' suspension state, with a read-only preview before applying.
- **Personal-ownership nudge**: the Today panel also counts how many of your cards still carry the untouched "✏️ My sentence" placeholder, because learner-edited cards are retained better than read-only AI cards.
- **Card learning boosters**: every new card carries an **emoji pictogram** for dual coding of concrete senses and a **spoken-frequency chip** (📊 top 500/1000/3000) so you always know whether a word deserves priority. Each Back also ends with a static **"✏️ My sentence"** box: edit the note in Anki and replace it with a sentence from your own life — self-generated examples are retained far better than read ones. (Keyword-method mnemonics are available on demand in the Speaking Lab's word-help 🧠 button rather than on the card.)
- **Native Audio**: Generates the target-language word, example, conjugations, related forms, and related examples with **AWS Polly**, plus the English Back meaning with the US-English Tiffany generative voice.
- **Focused Playback**: On answer reveal, automatically plays only the main word for non-verbs or the conjugations for verbs; English meanings, examples, and Word Family clips are click-to-play.
- **Persian Typography**: Bundles Vazirmatn for consistent offline Persian text and right-to-left rendering in Anki.
- **Direct Anki Sync**: Integrates flawlessly with AnkiConnect to push the generated HTML card and the audio files directly into your local Anki deck—no manual imports required.
- **Clipboard Reading Teacher**: On macOS, copy an Italian article and run `anki teach` to receive a focused summary, vocabulary, grammar, and comprehension lesson before optionally selecting cards.
- **Reversible Additions**: Production recall, common phrases, and smart grammar each have their own Settings switch. You can disable them for future words or safely remove the app-owned additions from existing notes.

## 📋 Prerequisites

Before running this application, you must have the following:

1. **Anki Desktop** installed and running on your computer.
2. The **[AnkiConnect](https://ankiweb.net/shared/info/2055492159)** add-on installed in Anki (Install Code: `2055492159`).
3. An active **Google Gemini API Key**.
4. An **AWS Account** with Access and Secret Keys (for Polly TTS).

## 💻 Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Ali-Mehrhosseini/anki-generator.git
   cd anki-generator
   ```

2. **Install Python and pip (if not already installed):**
   - **Ubuntu/Debian**: `sudo apt update && sudo apt install python3 python3-pip python3-venv`
   - **CentOS/RHEL**: `sudo yum install python3 python3-pip`
   - **Mac**: `brew install python`

3. **Create a Virtual Environment (Recommended):**
   It's best practice to use a virtual environment so dependencies don't conflict:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

4. **Install the Python dependencies:**
   ```bash
   pip3 install -r requirements.txt
   ```

5. **Start the Flask server:**
   ```bash
   python3 app.py
   ```

6. **Open the App:**
   Navigate to `http://localhost:5001` in your web browser.

## ⚙️ Configuration & Usage

Everything is configured directly through the app's web interface. 

1. **Set your API Keys**: Click the **⚙️ Settings** icon in the top right corner. Enter your Gemini API Key and AWS Credentials. These are saved securely in your browser's local storage.
2. **Choose your Target Language**: Select the language you are learning from the dropdown. This ensures the correct AI prompt and AWS Polly voice are used.
3. **Configure Anki Integration**: 
   - Enter your **Target Deck** name (e.g., `Italian`). If the deck doesn't exist, you can create it via the UI.
   - Enter your **Note Type** (e.g., `Italian Vocab`). Ensure your note type in Anki has fields that match what the app generates (e.g., `Front`, `Back`, `Audio`).
   - When Production recall is enabled, the app safely adds two app-owned fields and one conditional card type to that note type. Old notes do not receive a production card because those fields are empty.
4. **Generate a Card**: Go back to the main page, type a word in your target language (or in English), and click **Generate Card**. The app will fetch the data, generate the audio, and inject it straight into your Anki app!

### Learn from copied Italian text in the CLI

Copy an article or passage on macOS, then run:

```bash
anki teach
```

The CLI reads the clipboard with `pbpaste`, sends the text to Gemini, and shows
a guided section-by-section lesson plus a summary. Longer sources automatically
receive more vocabulary, grammar, and comprehension coverage, up to 120,000
characters. This analysis does not open Anki, synthesize audio, or
create cards. After the lesson, enter card numbers such as `1,3,5`, use `a` for
all suggestions, or `q` to finish without adding anything. Selected items use
the same context-aware card pipeline as `anki WORD`.

Persian lesson paragraphs default to original, selectable Unicode terminal text.
For correct iTerm2 display, enable right-to-left support and Ligatures, then use
Vazirmatn as the profile's non-ASCII font. Exact Vazirmatn image rendering is
also available through iTerm2 inline images: set
`ANKI_TEACH_PERSIAN_MODE="image"` in `.env`. Image mode is visually exact but
its Persian paragraphs cannot be selected as text.

Reading lessons also apply **input enhancement**: in color-capable terminals,
the vocabulary and grammar forms taught in each part are bolded inside the
Italian source text, so your eye meets the target forms while reading.

The normal commands remain unchanged:

```bash
anki entro
anki entro --context "Il servizio è disponibile entro i 27 anni."
```

### Reverting the optional learning features

- Turn off any Learning feature in **Settings** to stop adding it to newly generated notes.
- **Use original cards for new words** turns all three additions off together.
- **Revert added features in Anki…** removes the app-owned grammar/phrase block from existing notes in the selected note type, deletes Production recall cards and their review history, and removes the two production fields. Original recognition cards, Word Family, and audio remain.
- For a single CLI run, use `--no-production-card`, `--no-common-phrases`, `--no-smart-grammar`, or `--original-card`.

### Safely adding Production recall to existing cards from the CLI

Existing cards use a stricter migration path than newly generated cards. The
source notes are read-only: the CLI creates recall notes in the reserved
`AG Production Recall v1` note type. This keeps every original field, template,
card ID, interval, ease, lapse count, due date, and review-history entry
unchanged. Each new recall card starts with fresh review history. The isolated
note type also makes selective rollback possible.

The CLI reads these values from `.env`:

```dotenv
GEMINI_API_KEY="..."
GEMINI_TEACH_API_KEY="..." # optional: dedicated key for `anki teach`
AWS_ACCESS_KEY="..."
AWS_SECRET_KEY="..."
DECK_NAME="Italian"
NOTE_TYPE="Italian Vocab"
ANKICONNECT="http://localhost:8765"
```

When `GEMINI_TEACH_API_KEY` is set, the complete `anki teach` workflow uses
that dedicated key, including any cards selected from the lesson. Normal
`anki WORD` commands continue to use `GEMINI_API_KEY`. If the teaching key is
not set, teaching safely falls back to the normal Gemini key.

Keep Anki Desktop open. Carefully verify the deck and note type printed by the
preview before using `--apply`.

Preview all eligible notes (this is read-only and makes no AI or Polly calls):

```bash
python3 cli.py --backfill-production
```

Start with a small batch. `--apply` is required, the CLI asks for a typed
confirmation, and Anki exports a scheduled `.apkg` backup before any recall
note is created:

```bash
python3 cli.py --backfill-production --limit 10 --apply
```

The safest first test is one known note. Copy its note ID from Anki's Browse
window or from the preview:

```bash
python3 cli.py --backfill-production --note-id NOTE_ID
python3 cli.py --backfill-production --note-id NOTE_ID --apply
```

For a non-interactive shell, add `--yes` only after reviewing the preview:

```bash
python3 cli.py --backfill-production --limit 10 --apply --yes
```

The CLI prints a rollback ID and stores an atomic migration journal under
`.anki-generator/migrations/production-backfill-v1/`. If a run is interrupted,
preview or resume it with:

```bash
python3 cli.py --resume-production-backfill RUN_ID
python3 cli.py --resume-production-backfill RUN_ID --apply
```

Resume always uses the language and translation saved in the journal.

Preview and then undo only that run:

```bash
python3 cli.py --undo-production-backfill RUN_ID
python3 cli.py --undo-production-backfill RUN_ID --apply
```

Rollback exports another scheduled backup, verifies ownership, and deletes only
the app-created recall notes and their recall-card review history. It never
deletes or updates a source note or original-card history. Unique production
audio is left for Anki's **Tools → Check Media** cleanup so rollback cannot
accidentally remove media referenced elsewhere.

AnkiConnect does not expose Anki's actual note-type sort index. Install the
bundled, restricted helper once, then restart Anki:

```bash
python3 cli.py --install-recall-sort-helper
python3 cli.py --install-recall-sort-helper --apply
```

The helper is locked to `AG Production Recall v1` and can change only between
`Word` and `AG_SourceNoteID`. It cannot edit content, cards, scheduling, or
review history.

After restarting Anki, show the Italian word instead of the source note ID in
Anki's **Sort Field** browser column:

```bash
python3 cli.py --recall-sort-field word
python3 cli.py --recall-sort-field word --apply
```

This changes only the separate app-owned recall note type. Reverse it with:

```bash
python3 cli.py --recall-sort-field source-id --apply
```

Enable the visible word-audio button on production-recall cards created by
older versions without recreating notes or changing review history:

```bash
anki --upgrade-production-audio
anki --upgrade-production-audio --apply
```

This updates only the app-owned card templates. It reuses each note's existing
word recording and makes no Gemini or Polly request.

## Five-stage adaptive grammar practice

The Grammar Deck implements the current evidence-based grammar acquisition
loop. Each curriculum topic moves through five stages, and mastery now
weights all of them:

1. **Recognition** — Anki/FSRS review strength on the saved cards.
2. **Interpretation (Structured Input)** — before producing anything, you
   answer a meaning question that can only be resolved by processing the
   target form. Generate these with the new **Structured Input** mode in the
   Card Studio; topics that own interpretation cards are gated on this stage
   for mastery. This is VanPatten's Processing Instruction: every card is
   built so word order and the first noun cannot give the answer away.
3. **Controlled** — typed form production with one retry before reveal.
4. **Free use** — transfer writing evaluated against the target grammar only.
5. **Speaking** — the same targets under conversational time pressure.

Additional 2026-era workspace features:

- **Clickable word help (hint ladder)** — in the Speaking Sprint, tap any
  English word in the prompt. A popover offers a first-letter shape hint with
  a guess box; after two wrong guesses (or on demand) it reveals the Italian
  lemma, gender, a one-line English/Persian meaning, and a short example.
  The Gemini hint describes the concept without ever containing the Italian
  answer, so the retrieval attempt stays honest. The reveal has a **Play it**
  button (temporary Polly audio) and **Add to Anki** — a one-click jump to
  the generator with the word prefilled and generation started
  (`/?word=…`). Every peek, guess, and reveal is stored in the Learning Lab
  history; words looked up two or more times surface on the Fossilization
  watch dashboard, while words you keep guessing correctly stay off it.
- **Contextual deep dive on the same click** — while the hint loads, a second
  parallel request explains *why this word is the natural choice for this
  exact sentence*, *which inflected form you need and why* (person, tense,
  agreement, or a required subjunctive), and *one important beginner note*
  (register, common mistake, or collocation) — all in parallel English and
  Persian. It never writes the full translated sentence for you.
- **Keyword-method memory tricks** — after a word is revealed, the
  **🧠 Memory trick** button generates a two-stage keyword mnemonic: a
  Persian sound-alike keyword plus one vivid mental picture linking it to
  the meaning (meta-analytically supported for beginner vocabulary).
- **Guess before you learn (pretesting)** — when a freshly generated card
  preview opens, the Back is covered by a guess prompt: lock in a guess
  (even a wrong one) or skip. Attempting before studying measurably
  improves retention; the one-click `?word=` flow skips the gate because
  the Speaking Lab's word-help reveal was already its retrieval moment.

## Dictogloss — listen and reconstruct

The Grammar Deck's Today view includes a dictogloss (grammar dictation)
mode, the evidence-backed listening→grammar bridge: pick a studied topic,
and the app generates a 12–45 word Italian text that uses the target
grammar at least twice, reads it aloud with AWS Polly, and keeps the
original server-side. Play the audio as often as needed, reconstruct the
text from memory, then check: Gemini compares your reconstruction with the
original grammar-first, gives one focused retry with the original still
hidden, and reveals the true text after the final attempt. Results feed the
topic stats and the delayed-review queue.

## Reading coverage in `anki teach`

Before building a lesson from a pasted article, `anki teach` now measures
your **lexical coverage**: it reads every `Word` field in your deck and
reports what percentage of the article's unique words you already know.
Research puts comfortable unassisted reading at ~98% coverage, so the
report tells you whether the article is ideal reading, manageable (with the
unknown words listed — they will repeat across articles on the same topic,
so stay on that topic for narrow reading), or above your level.

- **Explain my answer** — after a wrong controlled, transfer, or speaking
  attempt, a button asks Gemini to name the mistake category and give a
  self-check hint. It never reveals the correct form, so retrieval practice
  survives the explanation.
- **Scenario roleplay** — the conversation stage offers six situational
  roleplays (meeting a classmate, the market, telling your weekend, finding a
  room, the doctor, plans and dreams) woven around your session's target
  grammar. Pick a scenario chip before the first turn; your choice persists
  for the session.
- **Session report** — the session summary now shows per-stage accuracy,
  the session's error patterns, and per-topic outcomes with one-tap
  **Repair cards** buttons that open the Card Studio in mistake mode for the
  failed topic.
- **Fossilization watch** — a merged view of recurring errors across grammar
  practice, the Speaking Lab, and word practice (`/api/insights/errors`),
  so repeated mistakes from any surface appear in one place.
- **Error-driven recommendations** — topic cards in the curriculum browser
  show a **Study next** badge when your recent error evidence deterministically
  maps to that topic (mastered topics are never recommended).

## Adaptive production practice

After reviewing some production-recall cards, run:

```bash
anki practice
```

The CLI selects three already-studied words using production-card review data,
rotates recently practiced words, and asks for a short real-life Italian
response. One Gemini teaching request checks meaning, word form, grammar,
collocation, and naturalness. If a target is wrong or missing, the CLI asks for
one retry before revealing the model correction.

Practice history is stored locally under `.anki-generator/practice/`. Original
notes, scheduling, and review history remain read-only. When the same error
occurs twice, the CLI offers an optional correction card in
`Italian::Practice Corrections`; it is created only after an explicit `y`.

## Voice-only Speaking Sprint

Open **Speaking Lab** from the website home page after reviewing some
production-recall cards. Each sprint contains three short English-to-Italian
translations built from verified examples on already-studied cards. Each round
uses one English sentence and one required Italian target word. Typing is
unavailable and live captions show your recognized words on screen while you
talk. The captions are display-only: when recording ends, the checked
transcript still comes from Gemini's direct audio review.
After evaluation, a persistent **What you said · transcription** panel shows
the recognized Italian beside the feedback and correct model sentence. It
remains visible while the learner reviews a mistake and prepares a retry.

Gemini checks whether every target was used naturally. A missed or incorrect
target requires one complete spoken retry. After two unsuccessful attempts,
the lab plays a corrected model and requires spoken repetition before the next
round unlocks. The app stores the transcript, duration, and feedback in
`.anki-generator/learning-lab/`; it never stores the raw microphone recording.
Microphone permission is required. Gemini evaluates and transcribes the
temporary in-memory clip directly because embedded browser speech services
are unreliable. Before any upload, the browser measures the microphone signal
locally and rejects silent recordings. A silent attempt is not sent to Gemini,
is not added to practice time, and does not count toward the daily goal. The
clip is discarded immediately after the request.

The three rounds form an adaptive ladder: round one shows a short Italian
starting phrase, while rounds two and three hide it behind an optional hint.
Failed target words enter a repair queue and are prioritized until used
correctly. If the browser transcript looks wrong, the learner can ask Gemini
to judge the temporary audio directly. Audio fallback combines transcription
and teaching feedback in one request, and the screen tracks a five-sentence
daily goal without storing raw audio.

After every evaluated response, the lab displays the verified correct Italian
sentence from the source card. Its **Play with AWS Polly** button generates
temporary Italian audio with the Beatrice voice; the MP3 is played in the
browser and is not added to Anki or written to the learning history.

Authentic source sentences are not simplified merely to avoid unfamiliar
grammar. Gemini compares each sentence with the learner's grammar-card history
and locally remembered pattern exposures. A genuinely new structure appears
as a concise **New pattern** notice with English/Persian explanation, register
guidance, and an everyday alternative. A first-exposure grammar mistake does
not cause a failed vocabulary attempt; the learner listens with Polly and
repeats the correct sentence once. Repeated or explicitly studied patterns can
then be graded normally.

The learner can choose **Change sentence** before recording to skip a prompt
without penalty. The replacement comes from a different verified, previously
studied Anki card, and skipped sentences are not repeated during that sprint.

Every successful round also offers an optional **fluency lap (4/3/2 drill)**:
say the same sentence three more times, each lap with 75% of the previous
one's time. Laps are pure pace work — the clock is the only judge, nothing is
sent to Gemini, and they never affect scoring or the daily goal. When a
pattern needs repair, the model-audio step became **true shadowing**: the
recorder opens while Polly is still speaking, so the learner speaks along
with the model from the first word instead of after it, and the take is kept
for playback when the model ends.

The website's **Revert added features in Anki…** button handles same-note
features created by the normal generator. It does not undo these isolated CLI
migrations; use `--undo-production-backfill RUN_ID` for them.

## 🛠️ Advanced: Customizing the AI Prompt

If you want to change how the flashcard is formatted or request specific grammar rules, you can directly edit the AI instructions. 

Go to **Settings** -> Scroll down to **AI Prompt (Advanced)**. You can freely edit the system prompt sent to Gemini. If you ever break it, simply click "Reset to Default".

### Deck statistics

Run `anki stats` (or `anki --stats`) to see your configured deck's vocabulary
and study counts. Use `anki stats --deck "Italian"` to inspect another deck.
Keep Anki Desktop open with AnkiConnect enabled; no AI or audio keys are needed.

The generator home page also has a **Deck overview** for the deck selected in
Settings. It refreshes after adding a word, when returning to the page, or with
**Refresh**. It connects to Anki on your computer, including when the generator
website is hosted remotely.

The overview includes unique vocabulary entries, notes, cards, due now,
new, learning/relearning, review, mature (21+ day interval), suspended, buried,
and cards added in the last seven days. All counts include subdecks.
Vocabulary is counted from distinct non-empty `Word` fields, ignoring case,
HTML formatting, and extra whitespace. A phrase counts as one entry;
recognition and production cards for the same word do not inflate this count.
Notes without a `Word` field contribute to note/card totals only. Categories
overlap: mature cards are review cards, and suspended cards may also be new or
review. Saved vocabulary is not a measurement of how many words you know.
