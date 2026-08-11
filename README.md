# AI-Powered Anki Flashcard Generator

A streamlined web application that automatically generates high-quality language learning flashcards and syncs them directly to your local Anki application. 

Instead of manually searching for translations, conjugations, and downloading audio files, you simply type a word, and the AI handles the rest.

## 🚀 Key Features

- **Multi-Language Support**: Currently supports Italian, Spanish, French, German, and Japanese.
- **Smart Generation**: Powered by a quality-first Gemini fallback chain, it automatically generates:
  - Direct translations (in English, Persian, or both).
  - Contextual example sentences.
  - Grammatical gender and part of speech.
  - Full verb conjugations.
  - Common noun, verb, adjective, and adverb word-family forms, each with its own example.
  - A clear note when a related part of speech has no natural common form.
  - One or two common collocations and a compact part-of-speech-specific Italian grammar summary.
- **Active Recall**: Optionally creates a second card from the same Anki note, with a meaning cue and sentence gap on the Front and the Italian answer on the Back.
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

The website's **Revert added features in Anki…** button handles same-note
features created by the normal generator. It does not undo these isolated CLI
migrations; use `--undo-production-backfill RUN_ID` for them.

## 🛠️ Advanced: Customizing the AI Prompt

If you want to change how the flashcard is formatted or request specific grammar rules, you can directly edit the AI instructions. 

Go to **Settings** -> Scroll down to **AI Prompt (Advanced)**. You can freely edit the system prompt sent to Gemini. If you ever break it, simply click "Reset to Default".
