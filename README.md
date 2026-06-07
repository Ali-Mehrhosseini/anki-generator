# Italian Anki Generator 🇮🇹

A sleek, minimal web application to automatically generate Italian Anki flashcards. 

It uses **Google Gemini** to fetch accurate Italian vocabulary, context examples, and verb conjugations, and **AWS Polly** to generate ultra-realistic native Italian pronunciations.

## Prerequisites

1. **Anki Desktop** installed and open.
2. The **[AnkiConnect](https://ankiweb.net/shared/info/2055492159)** add-on installed in Anki.
3. An existing deck in your Anki named `Italian`.
4. An existing note type named `Italian Vocab` (Ensure it has fields like Word, Front, Back, WordAudio, Audio, Conjugation).

## API Keys Required

Create a `.env` file in the root directory and add your API keys:

```env
GEMINI_API_KEY="your_gemini_key"
AWS_ACCESS_KEY="your_aws_key"
AWS_SECRET_KEY="your_aws_secret"
AWS_REGION="us-east-1"
DECK_NAME="Italian"
NOTE_TYPE="Italian Vocab"
POLLY_VOICE="Beatrice"
ANKICONNECT="http://localhost:8765"
```

## Running Locally (Python)

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the Flask server:
   ```bash
   python app.py
   ```
3. Open `http://localhost:5000` in your browser.

## Running with Docker

1. Change `ANKICONNECT` in your `.env` to `http://host.docker.internal:8765` so Docker can communicate with Anki on your host machine.
2. Build the image:
   ```bash
   docker build -t anki-generator .
   ```
3. Run the container:
   ```bash
   docker run -p 5000:5000 --env-file .env anki-generator
   ```
