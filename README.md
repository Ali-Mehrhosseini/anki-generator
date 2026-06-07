# AI-Powered Anki Flashcard Generator

A streamlined web application that automatically generates high-quality language learning flashcards and syncs them directly to your local Anki application. 

Instead of manually searching for translations, conjugations, and downloading audio files, you simply type a word, and the AI handles the rest.

## 🚀 Key Features

- **Multi-Language Support**: Currently supports Italian, Spanish, French, German, and Japanese.
- **Smart Generation**: Powered by **Google Gemini 3.1 Flash**, it automatically generates:
  - Direct translations (in English, Persian, or both).
  - Contextual example sentences.
  - Grammatical gender and part of speech.
  - Full verb conjugations.
- **Native Audio**: Automatically generates hyper-realistic, native pronunciation audio files for both the word and the example sentence using **AWS Polly**.
- **Direct Anki Sync**: Integrates flawlessly with AnkiConnect to push the generated HTML card and the audio files directly into your local Anki deck—no manual imports required.

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

2. **Install the Python dependencies:**
   Make sure you have Python installed, then run:
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the Flask server:**
   ```bash
   python app.py
   ```

4. **Open the App:**
   Navigate to `http://localhost:5000` in your web browser.

## ⚙️ Configuration & Usage

Everything is configured directly through the app's web interface. 

1. **Set your API Keys**: Click the **⚙️ Settings** icon in the top right corner. Enter your Gemini API Key and AWS Credentials. These are saved securely in your browser's local storage.
2. **Choose your Target Language**: Select the language you are learning from the dropdown. This ensures the correct AI prompt and AWS Polly voice are used.
3. **Configure Anki Integration**: 
   - Enter your **Target Deck** name (e.g., `Italian`). If the deck doesn't exist, you can create it via the UI.
   - Enter your **Note Type** (e.g., `Italian Vocab`). Ensure your note type in Anki has fields that match what the app generates (e.g., `Front`, `Back`, `Audio`).
4. **Generate a Card**: Go back to the main page, type a word in your target language (or in English), and click **Generate Card**. The app will fetch the data, generate the audio, and inject it straight into your Anki app!

## 🛠️ Advanced: Customizing the AI Prompt

If you want to change how the flashcard is formatted or request specific grammar rules, you can directly edit the AI instructions. 

Go to **Settings** -> Scroll down to **AI Prompt (Advanced)**. You can freely edit the system prompt sent to Gemini. If you ever break it, simply click "Reset to Default".
