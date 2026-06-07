# 🌌 Ethereal Anki Generator

A beautiful, high-performance web application designed to automatically generate high-quality language flashcards. Built with an **Awwwards-inspired "Ethereal Glass" UI**, it offers an incredibly smooth, premium experience for language learners.

It leverages **Google Gemini 3.1 Flash** to generate contextually accurate vocabulary, conjugations, and examples, and **AWS Polly** to instantly synthesize native, hyper-realistic audio for your cards. Everything syncs instantly to your local Anki app!

## ✨ Features

- **🏆 Awwwards Ethereal UI**: A deep obsidian background with an animated, soft-glowing aurora canvas. Ultra-refined glassmorphism panels with 24px border radiuses, translucent edges, and elegant typography (`Cormorant Garamond` & `Inter`).
- **🧠 Gemini AI Powered**: Simply type a word in your target language (or in English), and the AI will generate the translation, contextual example sentences, grammatical gender, and verb conjugations.
- **🗣️ AWS Polly Native Audio**: The app automatically triggers AWS Polly to generate flawless native audio pronunciation for the main word and the example sentences.
- **⚡ Zero-Click Anki Sync**: Integrates directly with AnkiConnect to push the generated HTML and Audio files straight into your local Anki deck. No downloading or importing required.
- **🌍 Multi-Language Support**: Supports learning Italian, Spanish, French, German, and Japanese. The AI prompt and AWS Polly neural voice dynamically adapt based on your selection!
- **🌗 Ambient Light/Dark Mode**: The UI seamlessly transitions between a deep obsidian night mode and an ethereal light mode, with the ambient aurora orbs adapting automatically.

## ⚙️ In-App Settings Panel

Say goodbye to messy `.env` files. You can configure everything directly from the sleek in-app Settings Panel (⚙️):

1. **API Keys**: Securely enter your Google Gemini API key and AWS Credentials directly into the UI. Keys are saved locally in your browser for privacy.
2. **Target Language**: Switch between supported languages. This changes the AI logic and the text-to-speech engine.
3. **Target Deck**: Choose which Anki deck to add the flashcards to. You can even create a completely new Anki deck directly from the web interface!
4. **Note Type**: Select your custom Anki Note Type.
5. **Translation Language**: Choose your native/translation language (English, Persian, or Both). Persian translations render with beautiful RTL typography using the `Vazirmatn` font.
6. **Advanced AI Prompts**: Power users can directly edit the system instructions sent to Gemini. Want to force a specific HTML layout or grammar explanation rule? Just edit the prompt and save!

## 🚀 Setup & Installation

### 1. Prerequisites
- **Anki Desktop** must be installed and running.
- Install the **[AnkiConnect](https://ankiweb.net/shared/info/2055492159)** add-on in your Anki app (Code: `2055492159`).
- Ensure you have a Note Type configured in Anki with the appropriate fields (e.g., `Front`, `Back`, `Audio`, `Conjugation`).

### 2. Run the Web Server
1. Clone the repository and navigate to the project directory.
2. Install the required Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the Flask server:
   ```bash
   python app.py
   ```
4. Open your browser and navigate to `http://localhost:5000`.

### 3. Configure
1. Click the **⚙️ Settings** icon in the top right.
2. Enter your Gemini API Key and AWS Access/Secret keys.
3. Select your Deck and Note Type.
4. Go back to the main page, type a word, and watch the ethereal loader spin as your flashcard is instantly created and synced!
