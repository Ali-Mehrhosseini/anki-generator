const ANKICONNECT_URL = 'http://127.0.0.1:8765';

async function invokeAnki(action, params = {}) {
    const payload = { action, version: 6, params };
    const response = await fetch(ANKICONNECT_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (result.error) {
        throw new Error(result.error);
    }
    return result.result;
}

async function createAnkiNote(data, audios, deckName, modelName, language) {
    const word = data.data.word;

    // Auto-create deck if it doesn't exist
    const existingDecks = await invokeAnki('deckNames');
    if (!existingDecks.includes(deckName)) {
        await invokeAnki('createDeck', { deck: deckName });
    }

    // store every audio file
    for (const [suffix, base64Data] of Object.entries(audios)) {
        const filename = `${word}${suffix}.mp3`;
        await invokeAnki('storeMediaFile', { filename: filename, data: base64Data });
    }

    // Add note
    const noteId = await invokeAnki('addNote', {
        note: {
            deckName: deckName,
            modelName: modelName,
            fields: {
                "Word": word,
                "Front": data.data.front_html,
                "Back": data.data.back_html,
                "WordAudio": `[sound:${word}.mp3]`,
                "Audio": `[sound:${word}_example.mp3]`,
                "Conjugation": data.data.conjugation_field
            },
            tags: ["auto", language.toLowerCase()],
            options: { allowDuplicate: false }
        }
    });

    return noteId;
}

document.addEventListener('DOMContentLoaded', () => {


    const form = document.getElementById('wordForm');
    const wordInput = document.getElementById('wordInput');
    const generateBtn = document.getElementById('generateBtn');
    const statusMessage = document.getElementById('statusMessage');
    const progressContainer = document.getElementById('progressContainer');
    const mainTitle = document.getElementById('mainTitle');

    const previewSection = document.getElementById('previewSection');
    const frontHtml = document.getElementById('frontHtml');
    const backHtml = document.getElementById('backHtml');
    const frontAudioControls = document.getElementById('frontAudioControls');
    const backAudioControls = document.getElementById('backAudioControls');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const word = wordInput.value.trim();
        if (!word) return;

        // Reset UI
        previewSection.classList.add('hidden');
        statusMessage.classList.add('hidden');
        statusMessage.className = '';
        frontAudioControls.innerHTML = '';
        backAudioControls.innerHTML = '';

        let deckName = localStorage.getItem('isCreatingNewDeck') === 'true' 
            ? (localStorage.getItem('newDeckName') || 'Default') 
            : (localStorage.getItem('deckName') || 'Italian');
        let modelName = localStorage.getItem('modelName') || 'Italian Vocab';
        let language = localStorage.getItem('language') || 'Italian';
        let translationLang = localStorage.getItem('translationLang') || 'Both (English + Persian)';

        // Check for duplicate instantly before loading
        try {
            wordInput.disabled = true;
            generateBtn.disabled = true;

            const query = `"${word}" "deck:${deckName}"`;
            const notes = await invokeAnki('findNotes', { query });

            if (notes && notes.length > 0) {
                wordInput.disabled = false;
                generateBtn.disabled = false;
                generateBtn.classList.remove('hidden');
                showError("This word is already in your Anki deck!");
                return;
            }
        } catch (e) {
            // Ignore error and proceed to let main logic handle it
            console.error("Duplicate check failed:", e);
        }

        function showEtherealLoading() {
            if (!window.gsap) return;

            const loader = document.createElement('div');
            loader.id = 'etherealLoader';
            loader.style.position = 'fixed';
            loader.style.top = '50%';
            loader.style.left = '50%';
            loader.style.transform = 'translate(-50%, -50%)';
            loader.style.zIndex = '9999';
            loader.style.display = 'flex';
            loader.style.gap = '16px';
            
            for (let i = 0; i < 3; i++) {
                const dot = document.createElement('div');
                dot.style.width = '12px';
                dot.style.height = '12px';
                dot.style.background = 'var(--text-primary)';
                dot.style.borderRadius = '50%';
                dot.style.boxShadow = '0 0 12px var(--text-primary)';
                loader.appendChild(dot);
                
                gsap.to(dot, {
                    y: -15,
                    opacity: 0.2,
                    scale: 0.8,
                    duration: 0.8,
                    repeat: -1,
                    yoyo: true,
                    ease: 'sine.inOut',
                    delay: i * 0.2
                });
            }
            
            document.body.appendChild(loader);
            gsap.from(loader, { opacity: 0, duration: 1 });
        }

        showEtherealLoading();
        setLoading(true);
        try {
            const apiKeys = {
                gemini: localStorage.getItem('geminiKey') || '',
                aws_access: localStorage.getItem('awsAccessKey') || '',
                aws_secret: localStorage.getItem('awsSecretKey') || ''
            };

            if (!apiKeys.gemini || !apiKeys.aws_access || !apiKeys.aws_secret) {
                setLoading(false, false);
                showError("Please enter your API Keys in the Settings panel.");
                return;
            }

            const promptValue = localStorage.getItem('customPrompt') || '';
            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ word, deckName, modelName, language, prompt: promptValue, translationLang, apiKeys })
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            const activityLog = document.getElementById('activityLog');
            activityLog.innerHTML = '';

            let finalData = null;
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                let lines = buffer.split('\n\n');
                buffer = lines.pop(); // keep the incomplete part in buffer

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const payloadStr = line.substring(6);
                        try {
                            const parsed = JSON.parse(payloadStr);
                            if (parsed.error) {
                                throw new Error(parsed.error);
                            }
                            if (parsed.status) {
                                const prev = activityLog.lastElementChild;
                                if (prev) {
                                    prev.classList.remove('loading');
                                    prev.classList.add('completed');
                                }

                                const item = document.createElement('div');
                                item.className = 'activity-item loading';
                                item.textContent = parsed.status;
                                activityLog.appendChild(item);
                                activityLog.scrollTop = activityLog.scrollHeight;
                            }
                            if (parsed.result) {
                                finalData = parsed.result;
                            }
                        } catch (e) {
                            if (e.message !== "Unexpected end of JSON input" && !e.message.startsWith("JSON")) {
                                throw e; // throw real errors, ignore json parse errors
                            }
                        }
                    }
                }
            }

            // Mark last one completed
            const lastItem = activityLog.lastElementChild;
            if (lastItem) {
                lastItem.classList.remove('loading');
                lastItem.classList.add('completed');
            }

            if (!finalData) {
                throw new Error("Stream closed without final result.");
            }

            const data = finalData;

            if (data.success) {
                try {
                    // Now save it to Anki locally!
                    const noteId = await createAnkiNote(data, data.audios, deckName, modelName, language);

                    setLoading(false, true);
                    showSuccess(`Successfully generated and added note ID: ${noteId}`);

                    // Strip [sound:...] tags from the front entirely
                    const cleanFront = data.data.front_html.replace(/\[sound:.*?\.mp3\]/g, '');

                    let cleanBack = data.data.back_html;
                    const word = data.data.word;

                    // Replace conjugation audio tags [sound:word_1.mp3] with inline play buttons!
                    const playIconSvg = `<svg viewBox="0 0 24 24" width="20" height="20" style="vertical-align: text-bottom; cursor: pointer; fill: var(--accent-color); margin-left: 6px; transition: transform 0.2s;"><path d="M8 5v14l11-7z"/></svg>`;
                    for (let i = 1; i <= 6; i++) {
                        const soundTag = `[sound:${word}_${i}.mp3]`;
                        if (data.audios[`_${i}`]) {
                            const btnHtml = `<span class="inline-audio" data-suffix="_${i}" title="Play">${playIconSvg}</span>`;
                            cleanBack = cleanBack.replace(soundTag, btnHtml);
                        }
                    }

                    // Strip any remaining sound tags from the back
                    cleanBack = cleanBack.replace(/\[sound:.*?\.mp3\]/g, '');

                    frontHtml.innerHTML = cleanFront;
                    backHtml.innerHTML = cleanBack;

                    // Attach click handlers
                    window.__audioMap = data.audios;
                    backHtml.querySelectorAll('.inline-audio').forEach(btn => {
                        btn.onclick = (e) => {
                            e.stopPropagation();
                            playBase64Audio(window.__audioMap[btn.dataset.suffix]);
                        };
                    });

                    renderAudioControls(data.audios);

                    previewSection.classList.remove('hidden');
                    wordInput.classList.remove('error-shake');

                    // Clear the input for the next word
                    wordInput.value = '';

                    // Scroll smoothly to the preview section
                    setTimeout(() => {
                        previewSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }, 100);
                } catch (ankiErr) {
                    setLoading(false, false);
                    showError("Failed to add to Anki: " + ankiErr.message);
                }
            } else {
                setLoading(false, false);
                if (data.error && data.error.includes("duplicate")) {
                    showError("This word is already in your Anki deck!");
                    wordInput.classList.add('error-shake');
                    setTimeout(() => wordInput.classList.remove('error-shake'), 600);
                } else {
                    let errMsg = data.error || "An unknown error occurred";
                    if (errMsg.includes("503") || errMsg.includes("UNAVAILABLE") || errMsg.includes("high demand")) {
                        errMsg = "The AI is experiencing high demand. ⏳ Please wait a moment and try again.";
                    }
                    showError(errMsg);
                    wordInput.classList.remove('error-shake');
                }
            }
        } catch (err) {
            console.error("Generate error:", err);
            setLoading(false, false);
            let msg = err.message || "Oops! Connection lost. 🔌 Please ensure the Python server is running.";
            if (msg === "Failed to fetch") msg = "Oops! Connection lost. 🔌 Please ensure the Python server is running.";
            showError(msg);
        }
    });

    let progressInterval;
    function setLoading(isLoading, success = true) {
        wordInput.disabled = isLoading;
        generateBtn.disabled = isLoading;
        if (isLoading) {
            generateBtn.classList.add('hidden');
            progressContainer.classList.remove('hidden');
            statusMessage.classList.add('hidden');
        } else {
            const loader = document.getElementById('etherealLoader');
            if (loader) {
                gsap.to(loader, {
                    opacity: 0,
                    duration: 0.5,
                    onComplete: () => loader.remove()
                });
            }
            if (success) {
                setTimeout(() => {
                    progressContainer.classList.add('hidden');
                    generateBtn.classList.remove('hidden');
                }, 500);
            } else {
                progressContainer.classList.add('hidden');
                generateBtn.classList.remove('hidden');
            }
        }
    }

    let statusTimeout;
    let fadeOutTimeout;

    function showSuccess(msg) {
        clearTimeout(statusTimeout);
        clearTimeout(fadeOutTimeout);

        statusMessage.textContent = msg;
        statusMessage.className = 'success show-status';
        statusMessage.classList.remove('hidden');

        statusTimeout = setTimeout(() => {
            statusMessage.classList.add('hide-status');
            fadeOutTimeout = setTimeout(() => {
                statusMessage.classList.add('hidden');
                statusMessage.classList.remove('show-status', 'hide-status');
            }, 400);
        }, 3500);
    }

    function showError(msg) {
        clearTimeout(statusTimeout);
        clearTimeout(fadeOutTimeout);
        statusMessage.textContent = msg;
        statusMessage.className = 'error show-status';
        statusMessage.classList.remove('hidden');
    }

    function renderAudioControls(audios) {
        if (!audios) return;

        const playIcon = `<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>`;

        if (audios[""]) {
            const btn = document.createElement('button');
            btn.className = 'play-audio-btn';
            btn.innerHTML = `${playIcon} Word`;
            btn.onclick = () => playBase64Audio(audios[""]);
            frontAudioControls.appendChild(btn);
        }

        if (audios["_example"]) {
            const btn = document.createElement('button');
            btn.className = 'play-audio-btn';
            btn.innerHTML = `${playIcon} Example`;
            btn.onclick = () => playBase64Audio(audios["_example"]);
            backAudioControls.appendChild(btn);
        }

        // Verb conjugation audios are now beautifully inlined!
        // We no longer render them here at the bottom.
    }

    function playBase64Audio(base64Str) {
        const audio = new Audio("data:audio/mp3;base64," + base64Str);
        audio.play().catch(e => console.error("Error playing audio:", e));
    }

    // Anki Status Polling
    const ankiStatusIndicator = document.getElementById('ankiStatus');

    const flagCodes = {
        "Italian": "it",
        "Spanish": "es",
        "French": "fr",
        "German": "de",
        "Japanese": "jp"
    };

    const updateLanguageUI = (lang) => {
        mainTitle.textContent = `${lang} Anki Generator`;
        document.title = `${lang} Anki Generator`;
        wordInput.placeholder = `Enter a ${lang} word or English phrase...`;

        // Update cute banner
        const flagImageEl = document.getElementById('flagImage');
        const flagTextEl = document.getElementById('flagText');
        const flagBannerEl = document.getElementById('flagBanner');

        if (flagImageEl && flagTextEl && flagBannerEl) {
            const code = flagCodes[lang] || "it";
            flagImageEl.src = `https://flagcdn.com/w160/${code}.png`;
            flagImageEl.alt = `${lang} Flag`;
            flagTextEl.textContent = lang;

            // Retrigger cute bounce animation
            flagBannerEl.classList.remove('bounce-anim');
            void flagBannerEl.offsetWidth; // trigger reflow
            flagBannerEl.classList.add('bounce-anim');
        }
    };

    // Initialize on load
    const savedLang = localStorage.getItem('language') || 'Italian';
    updateLanguageUI(savedLang);

    // Custom Dropdown Logic
    const flagBannerEl = document.getElementById('flagBanner');
    const languageDropdown = document.getElementById('languageDropdown');

    if (flagBannerEl && languageDropdown) {
        flagBannerEl.addEventListener('click', (e) => {
            e.stopPropagation();
            languageDropdown.classList.toggle('hidden');
        });

        document.addEventListener('click', () => {
            if (!languageDropdown.classList.contains('hidden')) {
                languageDropdown.classList.add('hidden');
            }
        });

        document.querySelectorAll('.dropdown-item').forEach(item => {
            item.addEventListener('click', () => {
                const newLang = item.getAttribute('data-lang');
                localStorage.setItem('language', newLang);
                updateLanguageUI(newLang);
            });
        });
    }



    async function checkAnkiStatus() {
        try {
            await invokeAnki('version');

            const isGenerating = !progressContainer.classList.contains('hidden');

            if (ankiStatusIndicator.className.includes('status-offline')) {
                // Just came online
            }
            ankiStatusIndicator.className = 'status-indicator status-online';
            ankiStatusIndicator.title = 'Anki is connected and running';

            document.getElementById('wordForm').classList.remove('anki-offline');
            if (!isGenerating) {
                wordInput.disabled = false;
                generateBtn.disabled = false;
                wordInput.placeholder = "Enter a word or phrase...";
            }
        } catch (err) {
            console.error("Anki polling error:", err);
            ankiStatusIndicator.className = 'status-indicator status-offline';
            ankiStatusIndicator.title = "AnkiConnect Offline";

            document.getElementById('wordForm').classList.add('anki-offline');
            const isGenerating = !progressContainer.classList.contains('hidden');
            if (!isGenerating) {
                wordInput.disabled = true;
                generateBtn.disabled = true;
                wordInput.placeholder = "Please open Anki first... 🔌";
            }
        }
    }



    // Check immediately on load, then every 5 seconds
    checkAnkiStatus();
    setInterval(checkAnkiStatus, 5000);
});
