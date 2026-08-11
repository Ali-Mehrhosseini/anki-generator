const ANKICONNECT_URL = 'http://127.0.0.1:8765';
const PRODUCTION_FRONT_FIELD = 'AG_ProductionFront_v1';
const PRODUCTION_BACK_FIELD = 'AG_ProductionBack_v1';
const PRODUCTION_TEMPLATE_NAME = 'AG Production Recall';
const PRODUCTION_TEMPLATE_MARKER = 'anki-generator-production-v1';
const PRODUCTION_TEMPLATE_FRONT =
    `{{#${PRODUCTION_FRONT_FIELD}}}<!-- ${PRODUCTION_TEMPLATE_MARKER} -->`
    + `{{${PRODUCTION_FRONT_FIELD}}}{{/${PRODUCTION_FRONT_FIELD}}}`;
const PRODUCTION_TEMPLATE_BACK =
    `{{FrontSide}}<hr id="answer"><!-- ${PRODUCTION_TEMPLATE_MARKER} -->`
    + `{{${PRODUCTION_BACK_FIELD}}}`
    + '<span style="display:none">{{WordAudio}}</span>';
const LEGACY_DEFAULT_PROMPT_FINGERPRINTS = new Set(['b8580232']);
const REQUIRED_ANKI_FIELDS = [
    'Word',
    'Front',
    'Back',
    'WordAudio',
    'Audio',
    'Conjugation'
];
const ANKI_FONT_ASSETS = [
    {
        filename: '_Vazirmatn-Regular.ttf',
        url: '/fonts/_Vazirmatn-Regular.ttf'
    },
    {
        filename: '_Vazirmatn-SemiBold.ttf',
        url: '/fonts/_Vazirmatn-SemiBold.ttf'
    }
];

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

function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    const chunkSize = 0x8000;
    let binary = '';

    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
        binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
    }

    return btoa(binary);
}

async function ensureAnkiFontAssets() {
    let existingFiles = [];

    try {
        existingFiles = await invokeAnki('getMediaFilesNames', {
            pattern: '_Vazirmatn-*.ttf'
        });
    } catch (error) {
        console.warn('Could not check existing Anki font media:', error);
    }

    const existing = new Set(existingFiles || []);
    for (const asset of ANKI_FONT_ASSETS) {
        if (existing.has(asset.filename)) continue;

        const response = await fetch(asset.url);
        if (!response.ok) {
            throw new Error(`Could not load bundled font: ${asset.filename}`);
        }

        const data = arrayBufferToBase64(await response.arrayBuffer());
        await invokeAnki('storeMediaFile', {
            filename: asset.filename,
            data
        });
    }
}

function getLearningFeatures(language = 'Italian') {
    return {
        production_card: localStorage.getItem('featureProductionCard') !== 'false',
        common_phrases: localStorage.getItem('featureCommonPhrases') !== 'false',
        smart_grammar:
            String(language).trim().toLowerCase() === 'italian'
            && localStorage.getItem('featureSmartGrammar') !== 'false'
    };
}

function isOwnedProductionTemplate(template) {
    if (!template) return false;
    const front = String(template.Front || '');
    const back = String(template.Back || '');
    return (
        front.includes(PRODUCTION_TEMPLATE_MARKER)
        && back.includes(PRODUCTION_TEMPLATE_MARKER)
        && front.includes(`{{#${PRODUCTION_FRONT_FIELD}}}`)
        && front.includes(`{{${PRODUCTION_FRONT_FIELD}}}`)
        && front.includes(`{{/${PRODUCTION_FRONT_FIELD}}}`)
        && back.includes('{{FrontSide}}')
        && back.includes(`{{${PRODUCTION_BACK_FIELD}}}`)
        && back.includes('{{WordAudio}}')
    );
}

function isCanonicalProductionTemplate(template) {
    return Boolean(
        template
        && String(template.Front || '') === PRODUCTION_TEMPLATE_FRONT
        && String(template.Back || '') === PRODUCTION_TEMPLATE_BACK
    );
}

async function ensureProductionCardModel(modelName) {
    const initialFields = await invokeAnki('modelFieldNames', { modelName });
    const missingRequired = REQUIRED_ANKI_FIELDS.filter(
        field => !initialFields.includes(field)
    );
    if (missingRequired.length) {
        throw new Error(
            `The "${modelName}" note type is missing: ${missingRequired.join(', ')}.`
        );
    }

    const initialTemplates = await invokeAnki('modelTemplates', { modelName });
    const existingProductionTemplate =
        initialTemplates && initialTemplates[PRODUCTION_TEMPLATE_NAME];
    if (
        existingProductionTemplate
        && !isOwnedProductionTemplate(existingProductionTemplate)
    ) {
        throw new Error(
            `The "${modelName}" note type already has a card type named `
            + `"${PRODUCTION_TEMPLATE_NAME}" that was not created by this app.`
        );
    }
    if (
        existingProductionTemplate
        && !isCanonicalProductionTemplate(existingProductionTemplate)
    ) {
        throw new Error(
            `The app-owned "${PRODUCTION_TEMPLATE_NAME}" card type was edited `
            + 'or is outdated. Remove it in Settings, then try again.'
        );
    }

    const hasProductionField = [PRODUCTION_FRONT_FIELD, PRODUCTION_BACK_FIELD]
        .some(field => initialFields.includes(field));
    if (
        !existingProductionTemplate
        && hasProductionField
    ) {
        throw new Error(
            `The "${modelName}" note type already contains a production field `
            + 'with the same name. Nothing was changed.'
        );
    }

    const addedFields = [];
    let templateAdded = false;
    const rollbackNewModelParts = async () => {
        if (templateAdded) {
            try {
                await invokeAnki('modelTemplateRemove', {
                    modelName,
                    templateName: PRODUCTION_TEMPLATE_NAME
                });
            } catch (error) {
                console.warn('Could not roll back the new production template:', error);
            }
        }
        for (const fieldName of [...addedFields].reverse()) {
            try {
                await invokeAnki('modelFieldRemove', { modelName, fieldName });
            } catch (error) {
                console.warn(`Could not roll back ${fieldName}:`, error);
            }
        }
    };

    try {
        for (const fieldName of [PRODUCTION_FRONT_FIELD, PRODUCTION_BACK_FIELD]) {
            if (!initialFields.includes(fieldName)) {
                await invokeAnki('modelFieldAdd', { modelName, fieldName });
                addedFields.push(fieldName);
            }
        }

        if (!existingProductionTemplate) {
            await invokeAnki('modelTemplateAdd', {
                modelName,
                template: {
                    Name: PRODUCTION_TEMPLATE_NAME,
                    Front: PRODUCTION_TEMPLATE_FRONT,
                    Back: PRODUCTION_TEMPLATE_BACK
                }
            });
            templateAdded = true;
        }
    } catch (error) {
        await rollbackNewModelParts();
        throw error;
    }

    let verifiedFields;
    let verifiedTemplates;
    try {
        [verifiedFields, verifiedTemplates] = await Promise.all([
            invokeAnki('modelFieldNames', { modelName }),
            invokeAnki('modelTemplates', { modelName })
        ]);
    } catch (error) {
        await rollbackNewModelParts();
        throw error;
    }
    const fieldsReady = [PRODUCTION_FRONT_FIELD, PRODUCTION_BACK_FIELD].every(
        field => verifiedFields.includes(field)
    );
    const templateReady = isCanonicalProductionTemplate(
        verifiedTemplates && verifiedTemplates[PRODUCTION_TEMPLATE_NAME]
    );

    if (!fieldsReady || !templateReady) {
        await rollbackNewModelParts();
        throw new Error(
            'Anki did not finish creating the production card type. '
            + 'Update AnkiConnect or turn off Production recall in Settings.'
        );
    }
}

function ankiSearchLiteral(value) {
    return String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function normalizeDuplicateValue(value) {
    return String(value || '').trim().toLocaleLowerCase();
}

async function findExistingWordNote(word, deckName, fieldName = 'Word') {
    const fieldQuery = `deck:"${ankiSearchLiteral(deckName)}" ${fieldName}:"${ankiSearchLiteral(word)}"`;
    let notes = await invokeAnki('findNotes', { query: fieldQuery });

    // If Anki's field search misses because of search syntax/version quirks,
    // scan the deck and still compare only the configured main word field.
    if (!notes || notes.length === 0) {
        const deckQuery = `deck:"${ankiSearchLiteral(deckName)}"`;
        notes = await invokeAnki('findNotes', { query: deckQuery });
    }

    if (!notes || notes.length === 0) return false;

    const notesInfo = await invokeAnki('notesInfo', { notes });
    const target = normalizeDuplicateValue(word);
    return notesInfo.some(note => {
        const field = note.fields && note.fields[fieldName];
        return normalizeDuplicateValue(field && field.value) === target;
    });
}

function promptFingerprint(value) {
    let hash = 0x811c9dc5;
    const normalized = String(value || '').replace(/\r\n/g, '\n');
    for (let index = 0; index < normalized.length; index += 1) {
        hash ^= normalized.charCodeAt(index);
        hash = Math.imul(hash, 0x01000193);
    }
    return (hash >>> 0).toString(16).padStart(8, '0');
}

function hasManualCustomPrompt() {
    const state = localStorage.getItem('customPromptIsManual');
    const storedPrompt = localStorage.getItem('customPrompt');

    // Before this flag existed, every prompt edit was stored under customPrompt.
    // Refresh the known old default, but preserve every unknown/custom value.
    if (state === null && storedPrompt) {
        if (
            LEGACY_DEFAULT_PROMPT_FINGERPRINTS.has(
                promptFingerprint(storedPrompt)
            )
        ) {
            localStorage.setItem('customPromptIsManual', 'false');
            return false;
        }
        localStorage.setItem('customPromptIsManual', 'true');
        return true;
    }
    return state === 'true';
}

async function getPromptForGeneration() {
    if (hasManualCustomPrompt()) {
        return localStorage.getItem('customPrompt') || '';
    }

    try {
        const response = await fetch('/api/prompt');
        const data = await response.json();
        localStorage.setItem('customPrompt', data.prompt);
        if (data.version) {
            localStorage.setItem('customPromptVersion', data.version);
        }
        localStorage.setItem('customPromptIsManual', 'false');
        return data.prompt;
    } catch (err) {
        console.error("Failed to refresh default prompt:", err);
        return localStorage.getItem('customPrompt') || '';
    }
}

async function createAnkiNote(data, audios, deckName, modelName, language) {
    const word = data.data.word;
    const productionCard = data.data.production_card_html;

    // Auto-create deck if it doesn't exist
    const existingDecks = await invokeAnki('deckNames');
    if (!existingDecks.includes(deckName)) {
        await invokeAnki('createDeck', { deck: deckName });
    }

    if (await findExistingWordNote(word, deckName)) {
        throw new Error(`This word is already in your Anki deck: ${deckName}!`);
    }

    if (data.data.back_html.includes('AnkiVazirmatn')) {
        try {
            await ensureAnkiFontAssets();
        } catch (error) {
            // The installed/local font fallback still lets the card save.
            console.warn('Could not install Vazirmatn in Anki media:', error);
        }
    }

    // store every audio file
    const audioFilenames = data.data.audio_filenames || {};
    for (const [suffix, base64Data] of Object.entries(audios)) {
        const filename = audioFilenames[suffix] || `${word}${suffix}.mp3`;
        await invokeAnki('storeMediaFile', { filename: filename, data: base64Data });
    }
    const wordAudioFilename = audioFilenames[''] || `${word}.mp3`;

    const fields = {
        "Word": word,
        "Front": data.data.front_html,
        "Back": data.data.back_html,
        "WordAudio": `[sound:${wordAudioFilename}]`,
        // The example is rendered as a manual HTML5 control in Back.
        "Audio": "",
        "Conjugation": data.data.conjugation_field
    };
    if (
        productionCard
        && productionCard.front_html
        && productionCard.back_html
    ) {
        fields[PRODUCTION_FRONT_FIELD] = productionCard.front_html;
        fields[PRODUCTION_BACK_FIELD] = productionCard.back_html;
    }

    // One note creates the original recognition card and, when populated,
    // the optional production-recall sibling card.
    const noteId = await invokeAnki('addNote', {
        note: {
            deckName: deckName,
            modelName: modelName,
            fields,
            tags: ["auto", language.toLowerCase()],
            options: { allowDuplicate: true }
        }
    });

    return {
        noteId,
        productionIncluded: Boolean(
            fields[PRODUCTION_FRONT_FIELD]
            && fields[PRODUCTION_BACK_FIELD]
        )
    };
}

document.addEventListener('DOMContentLoaded', () => {


    const form = document.getElementById('wordForm');
    const wordInput = document.getElementById('wordInput');
    const generateBtn = document.getElementById('generateBtn');
    const statusMessage = document.getElementById('statusMessage');
    const progressContainer = document.getElementById('progressContainer');
    const mainTitle = document.getElementById('mainTitle');
    const meaningChoicePanel = document.getElementById('meaningChoicePanel');
    const meaningChoiceTitle = document.getElementById('meaningChoiceTitle');
    const meaningChoiceOptions = document.getElementById('meaningChoiceOptions');
    const meaningChoiceCancel = document.getElementById('meaningChoiceCancel');

    const previewSection = document.getElementById('previewSection');
    const frontHtml = document.getElementById('frontHtml');
    const backHtml = document.getElementById('backHtml');
    const frontAudioControls = document.getElementById('frontAudioControls');
    const backAudioControls = document.getElementById('backAudioControls');
    const productionPreview = document.getElementById('productionPreview');
    const productionFrontHtml = document.getElementById('productionFrontHtml');
    const productionBackHtml = document.getElementById('productionBackHtml');

    let selectedInterpretation = null;
    let selectedInterpretationInput = '';

    function hideMeaningChoices() {
        meaningChoicePanel.classList.add('hidden');
        meaningChoiceOptions.innerHTML = '';
    }

    function showMeaningChoices(disambiguation) {
        const input = String(disambiguation.input || wordInput.value).trim();
        const options = Array.isArray(disambiguation.options)
            ? disambiguation.options
            : [];

        meaningChoiceTitle.textContent = `What does “${input}” mean here?`;
        meaningChoiceOptions.innerHTML = '';
        options.forEach(option => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'meaning-choice-option';

            const top = document.createElement('div');
            top.className = 'meaning-choice-option-top';
            const headword = document.createElement('span');
            headword.className = 'meaning-choice-headword';
            headword.textContent = option.headword;
            const part = document.createElement('span');
            part.className = 'meaning-choice-part';
            part.textContent = String(option.part_of_speech || 'other').replace('_', ' ');
            top.append(headword, part);

            const meaning = document.createElement('div');
            meaning.className = 'meaning-choice-meaning';
            meaning.textContent = option.meaning_en;
            button.append(top, meaning);

            if (option.meaning_fa) {
                const persian = document.createElement('div');
                persian.className = 'meaning-choice-persian';
                persian.lang = 'fa';
                persian.textContent = option.meaning_fa;
                button.appendChild(persian);
            }
            if (option.explanation) {
                const explanation = document.createElement('div');
                explanation.className = 'meaning-choice-explanation';
                explanation.textContent = option.explanation;
                button.appendChild(explanation);
            }

            button.addEventListener('click', () => {
                selectedInterpretation = option;
                selectedInterpretationInput = input;
                hideMeaningChoices();
                form.requestSubmit();
            });
            meaningChoiceOptions.appendChild(button);
        });

        meaningChoicePanel.classList.remove('hidden');
        meaningChoicePanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    meaningChoiceCancel.addEventListener('click', () => {
        selectedInterpretation = null;
        selectedInterpretationInput = '';
        hideMeaningChoices();
        wordInput.focus();
    });

    wordInput.addEventListener('input', () => {
        if (wordInput.value.trim() !== selectedInterpretationInput) {
            selectedInterpretation = null;
            selectedInterpretationInput = '';
            hideMeaningChoices();
        }
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const word = wordInput.value.trim();
        if (!word) return;
        const interpretationForRequest =
            selectedInterpretationInput === word
                ? selectedInterpretation
                : null;

        // Reset UI
        previewSection.classList.add('hidden');
        statusMessage.classList.add('hidden');
        statusMessage.className = '';
        frontAudioControls.innerHTML = '';
        backAudioControls.innerHTML = '';
        if (productionPreview) {
            productionPreview.classList.add('hidden');
            productionPreview.open = false;
        }
        if (productionFrontHtml) productionFrontHtml.innerHTML = '';
        if (productionBackHtml) productionBackHtml.innerHTML = '';
        hideMeaningChoices();

        let deckName = localStorage.getItem('isCreatingNewDeck') === 'true' 
            ? (localStorage.getItem('newDeckName') || 'Default') 
            : (localStorage.getItem('deckName') || 'Italian');
        let modelName = localStorage.getItem('modelName') || 'Italian Vocab';
        let language = localStorage.getItem('language') || 'Italian';
        let translationLang = localStorage.getItem('translationLang') || 'Both (English + Persian)';
        const features = getLearningFeatures(language);

        // 3-dot loading removed
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

            const promptValue = await getPromptForGeneration();
            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    word,
                    deckName,
                    modelName,
                    language,
                    prompt: promptValue,
                    translationLang,
                    features,
                    apiKeys,
                    selectedInterpretation: interpretationForRequest
                })
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
                if (data.disambiguation) {
                    setLoading(false, false);
                    showMeaningChoices(data.disambiguation);
                    return;
                }

                selectedInterpretation = null;
                selectedInterpretationInput = '';

                if (features.production_card) {
                    try {
                        await ensureProductionCardModel(modelName);
                    } catch (error) {
                        setLoading(false, false);
                        showError(
                            `Production card setup failed: ${error.message} `
                            + 'You can turn off Production recall in Settings and continue with the original card.'
                        );
                        return;
                    }
                }

                const generatedProductionCard =
                    data.data && data.data.production_card_html;
                if (
                    features.production_card
                    && !(
                        generatedProductionCard
                        && generatedProductionCard.front_html
                        && generatedProductionCard.back_html
                    )
                ) {
                    throw new Error(
                        'Production recall was enabled, but its sentence could '
                        + 'not be verified. Nothing was added; please try again.'
                    );
                }
                try {
                    // Now save it to Anki locally!
                    const noteResult = await createAnkiNote(
                        data,
                        data.audios,
                        deckName,
                        modelName,
                        language
                    );

                    setLoading(false, true);
                    const cardSummary = noteResult.productionIncluded
                        ? 'Recognition and production cards added'
                        : 'Recognition card added';
                    showSuccess(
                        `${cardSummary}. Note ID: ${noteResult.noteId}`
                    );

                    // Strip [sound:...] tags from the front entirely
                    const cleanFront = data.data.front_html.replace(/\[sound:.*?\.mp3\]/g, '');

                    let cleanBack = data.data.back_html;
                    const word = data.data.word;
                    const audioFilenames = data.data.audio_filenames || {};

                    // Replace conjugation audio tags [sound:word_1.mp3] with inline play buttons!
                    const playIconSvg = `<svg viewBox="0 0 24 24" width="20" height="20" style="vertical-align: text-bottom; cursor: pointer; fill: var(--accent-color); margin-left: 6px; transition: transform 0.2s;"><path d="M8 5v14l11-7z"/></svg>`;
                    for (let i = 1; i <= 6; i++) {
                        const filename = audioFilenames[`_${i}`] || `${word}_${i}.mp3`;
                        const soundTag = `[sound:${filename}]`;
                        if (data.audios[`_${i}`]) {
                            const btnHtml = `<span class="inline-audio" data-suffix="_${i}" title="Play">${playIconSvg}</span>`;
                            cleanBack = cleanBack.replace(soundTag, btnHtml);
                        }
                    }

                    // Compatibility for older responses that used native family tags.
                    for (const part of ['noun', 'verb', 'adjective', 'adverb']) {
                        for (const tail of ['', '_example']) {
                            const suffix = `_family_${part}${tail}`;
                            const filename = audioFilenames[suffix] || `${word}${suffix}.mp3`;
                            const soundTag = `[sound:${filename}]`;
                            if (data.audios[suffix]) {
                                const title = tail ? 'Play example' : 'Play word';
                                const btnHtml = `<span class="inline-audio" data-suffix="${suffix}" title="${title}">${playIconSvg}</span>`;
                                cleanBack = cleanBack.replace(soundTag, btnHtml);
                            }
                        }
                    }

                    // Strip any remaining sound tags from the back
                    cleanBack = cleanBack.replace(/\[sound:.*?\.mp3\]/g, '');

                    frontHtml.innerHTML = cleanFront;
                    backHtml.innerHTML = cleanBack;

                    const productionCard = data.data.production_card_html;
                    if (
                        productionCard
                        && productionFrontHtml
                        && productionBackHtml
                        && productionPreview
                    ) {
                        productionFrontHtml.innerHTML =
                            productionCard.front_html.replace(/\[sound:.*?\.mp3\]/g, '');
                        productionBackHtml.innerHTML =
                            productionCard.back_html.replace(/\[sound:.*?\.mp3\]/g, '');
                        productionPreview.classList.remove('hidden');
                    }

                    // Manual-only HTML5 controls use the generated base64 audio
                    // in the web preview and never join Anki's autoplay queue.
                    const manualAudios = [];
                    const manualAudioContainers = [backHtml];
                    if (
                        productionCard
                        && productionBackHtml
                    ) {
                        manualAudioContainers.push(productionBackHtml);
                    }
                    manualAudioContainers.forEach(container => {
                        container.querySelectorAll('.anki-generator-manual-audio').forEach(control => {
                            const suffix = control.dataset.audioSuffix;
                            const audio = control.querySelector('audio');
                            const base64Audio = data.audios[suffix];
                            if (!audio || !base64Audio) {
                                control.remove();
                                return;
                            }
                            audio.src = `data:audio/mp3;base64,${base64Audio}`;
                            manualAudios.push(audio);
                        });
                    });
                    manualAudios.forEach(audio => {
                        audio.addEventListener('play', () => {
                            manualAudios.forEach(other => {
                                if (other !== audio) {
                                    other.pause();
                                    other.currentTime = 0;
                                }
                            });
                        });
                    });

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
                    if (ankiErr.message.includes("already in your Anki deck")) {
                        showError(ankiErr.message);
                    } else {
                        showError("Failed to add to Anki: " + ankiErr.message);
                    }
                }
            } else {
                setLoading(false, false);
                if (data.error && data.error.includes("duplicate")) {
                    showError(`This word is already in your Anki deck: ${deckName}!`);
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

        // Back-side clips are now placed directly beside the text they play.
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
            
            const cloudNotice = document.getElementById('ankiCloudNotice');
            if (cloudNotice && !cloudNotice.classList.contains('hidden') && !cloudNotice.dataset.hiding) {
                cloudNotice.dataset.hiding = "true";
                setTimeout(() => {
                    cloudNotice.classList.add('hidden');
                    cloudNotice.dataset.hiding = "";
                }, 3000);
            }

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

            const cloudNotice = document.getElementById('ankiCloudNotice');
            if (cloudNotice) cloudNotice.classList.remove('hidden');

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
