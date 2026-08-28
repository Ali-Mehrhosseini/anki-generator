const ANKICONNECT_URL = 'http://127.0.0.1:8765';
const PRODUCTION_FRONT_FIELD = 'AG_ProductionFront_v1';
const PRODUCTION_BACK_FIELD = 'AG_ProductionBack_v1';
const PRODUCTION_TEMPLATE_NAME = 'AG Production Recall';
const PRODUCTION_TEMPLATE_MARKER = 'anki-generator-production-v1';
const LEARNING_ESSENTIALS_START =
    '<!-- anki-generator-learning-essentials-start -->';
const LEARNING_ESSENTIALS_END =
    '<!-- anki-generator-learning-essentials-end -->';
const LEGACY_DEFAULT_PROMPT_FINGERPRINTS = new Set(['b8580232']);
const REVERT_PROGRESS_KEY = 'ankiGeneratorRevertProgressV1';
const REVERT_PROGRESS_MAX_AGE_MS = 24 * 60 * 60 * 1000;
const LEARNING_FEATURE_KEYS = {
    production: 'featureProductionCard',
    phrases: 'featureCommonPhrases',
    grammar: 'featureSmartGrammar',
    listening: 'featureListeningCard',
    cloze: 'featureSentenceCloze'
};

const REQUIRED_ANKI_FIELDS = [
    'Word',
    'Front',
    'Back',
    'WordAudio',
    'Audio',
    'Conjugation'
];

async function ensureNoteType(modelName) {
    try {
        const existingModels = await invokeAnki('modelNames');
        if (existingModels && existingModels.includes(modelName)) return;

        console.log(`Note type "${modelName}" not found — creating it now…`);
        await invokeAnki('createModel', {
            modelName,
            inOrderFields: [...REQUIRED_ANKI_FIELDS],
            css: `.card {
    font-family: arial;
    font-size: 20px;
    line-height: 1.5;
    text-align: center;
    color: black;
    background-color: white;
}`,
            cardTemplates: [
                {
                    Name: 'Card 1',
                    Front: `<div style='font-family: "Arial"; font-size: 20px;'>{{Front}}</div>\n<div style='font-family: "Arial"; font-size: 20px;'>{{WordAudio}}</div>`,
                    Back: `{{FrontSide}}\n\n<hr id=answer>\n\n<div style='font-family: "Arial"; font-size: 20px;'>{{Back}}</div>`
                }
            ]
        });
        console.log(`Note type "${modelName}" created.`);
    } catch (e) {
        console.warn('Could not auto-create note type:', e);
    }
}

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

function getRevertProgress() {
    try {
        const value = JSON.parse(
            localStorage.getItem(REVERT_PROGRESS_KEY) || '{}'
        );
        return value && typeof value === 'object' && !Array.isArray(value)
            ? value
            : {};
    } catch (error) {
        return {};
    }
}

function rememberRevertProgress(modelName, modelId) {
    const progress = getRevertProgress();
    progress[String(modelId)] = {
        modelName,
        startedAt: Date.now()
    };
    localStorage.setItem(REVERT_PROGRESS_KEY, JSON.stringify(progress));
}

function hasRevertProgress(modelName, modelId) {
    const value = getRevertProgress()[String(modelId)];
    const age = value ? Date.now() - value.startedAt : NaN;
    return Boolean(
        value
        && value.modelName === modelName
        && Number.isFinite(value.startedAt)
        && age >= 0
        && age <= REVERT_PROGRESS_MAX_AGE_MS
    );
}

function clearRevertProgress(modelId) {
    const progress = getRevertProgress();
    delete progress[String(modelId)];
    localStorage.setItem(REVERT_PROGRESS_KEY, JSON.stringify(progress));
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

function ankiSearchLiteral(value) {
    return String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function removeOwnedLearningEssentials(backHtml) {
    let result = String(backHtml || '');
    while (true) {
        const start = result.indexOf(LEARNING_ESSENTIALS_START);
        if (start < 0) return result;
        const endMarker = result.indexOf(
            LEARNING_ESSENTIALS_END,
            start + LEARNING_ESSENTIALS_START.length
        );
        if (endMarker < 0) return result;
        const end = endMarker + LEARNING_ESSENTIALS_END.length;
        result = result.slice(0, start) + result.slice(end);
    }
}

async function revertLearningFeaturesInAnki(modelName) {
    const [templates, fields, noteIds, modelIds] = await Promise.all([
        invokeAnki('modelTemplates', { modelName }),
        invokeAnki('modelFieldNames', { modelName }),
        invokeAnki('findNotes', {
            query: `note:"${ankiSearchLiteral(modelName)}"`
        }),
        invokeAnki('modelNamesAndIds')
    ]);
    const modelId = modelIds && modelIds[modelName];
    if (!modelId) {
        throw new Error(`The "${modelName}" note type no longer exists.`);
    }

    const template = templates && templates[PRODUCTION_TEMPLATE_NAME];
    if (template && !isOwnedProductionTemplate(template)) {
        throw new Error(
            'A card type with the same name exists, but it is not owned by this generator. Nothing was removed.'
        );
    }

    const productionFields = [
        PRODUCTION_FRONT_FIELD,
        PRODUCTION_BACK_FIELD
    ].filter(fieldName => fields.includes(fieldName));
    const canResumeVerifiedRevert = hasRevertProgress(
        modelName,
        modelId
    );
    if (
        !template
        && productionFields.length
        && !canResumeVerifiedRevert
    ) {
        throw new Error(
            'Production-named fields exist without the app-owned card type, so their ownership cannot be verified. Nothing was removed.'
        );
    }

    const foreignTemplateUsesProductionFields = Object.entries(
        templates || {}
    ).some(([name, value]) => {
        if (name === PRODUCTION_TEMPLATE_NAME) return false;
        const html = `${value.Front || ''}${value.Back || ''}`;
        return productionFields.some(
            fieldName => html.includes(fieldName)
        );
    });
    if (foreignTemplateUsesProductionFields) {
        throw new Error(
            'Another card type uses the production fields, so the safe revert stopped without changing anything.'
        );
    }

    const notes = noteIds && noteIds.length
        ? await invokeAnki('notesInfo', { notes: noteIds })
        : [];
    const backUpdates = (notes || []).flatMap(note => {
        if (note.modelName !== modelName) return [];
        const back = note.fields && note.fields.Back;
        const currentBack = String(back && back.value || '');
        const cleanedBack = removeOwnedLearningEssentials(currentBack);
        const noteId = note.noteId || note.id;
        if (!noteId || cleanedBack === currentBack) return [];
        return [{
            id: noteId,
            originalBack: currentBack,
            cleanedBack
        }];
    });

    const hasProductionParts = Boolean(
        template || productionFields.length
    );
    if (hasProductionParts) {
        rememberRevertProgress(modelName, modelId);
    }

    const appliedBackUpdates = [];
    try {
        for (const update of backUpdates) {
            await invokeAnki('updateNoteFields', {
                note: {
                    id: update.id,
                    fields: { Back: update.cleanedBack }
                }
            });
            appliedBackUpdates.push(update);
        }
    } catch (error) {
        let restored = 0;
        for (const update of [...appliedBackUpdates].reverse()) {
            try {
                await invokeAnki('updateNoteFields', {
                    note: {
                        id: update.id,
                        fields: { Back: update.originalBack }
                    }
                });
                restored += 1;
            } catch (restoreError) {
                console.warn('Could not restore a partially reverted Back:', restoreError);
            }
        }
        if (restored === appliedBackUpdates.length) {
            if (hasProductionParts) clearRevertProgress(modelId);
            throw new Error(
                'Anki could not update every note, so no production card parts were removed and completed Back changes were restored. Please try again.'
            );
        }
        throw new Error(
            'Anki stopped during the note cleanup and could not restore every changed Back. Click Revert again to finish safely.'
        );
    }

    try {
        if (template) {
            await invokeAnki('modelTemplateRemove', {
                modelName,
                templateName: PRODUCTION_TEMPLATE_NAME
            });
        }
        for (const fieldName of [...productionFields].reverse()) {
            await invokeAnki('modelFieldRemove', {
                modelName,
                fieldName
            });
        }
    } catch (error) {
        throw new Error(
            'The note text was reverted, but Anki could not finish removing '
            + 'the production card parts. Click Revert again to continue. '
            + (error.message || '')
        );
    }
    clearRevertProgress(modelId);

    return {
        updatedNotes: backUpdates.length,
        productionRemoved: Boolean(template)
    };
}

document.addEventListener('DOMContentLoaded', async () => {
    // Hide cors notice if previously acknowledged
    if (localStorage.getItem('hideCorsNotice') === 'true') {
        const corsNotice = document.getElementById('corsNotice');
        if (corsNotice) corsNotice.style.display = 'none';
    }

    const autoConnectionStatus = document.getElementById('autoConnectionStatus');
    const verifyConnection = async () => {
        const gemini = localStorage.getItem('geminiKey') || '';
        const aws_access = localStorage.getItem('awsAccessKey') || '';
        const aws_secret = localStorage.getItem('awsSecretKey') || '';

        if (gemini && aws_access && aws_secret) {
            try {
                const response = await fetch('/api/verify-keys', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ apiKeys: { gemini, aws_access, aws_secret } })
                });
                const data = await response.json();
                if (autoConnectionStatus) {
                    autoConnectionStatus.classList.remove('hidden');
                    if (!data.error && data.gemini && data.aws) {
                        autoConnectionStatus.classList.remove('cloud-error');
                        autoConnectionStatus.classList.add('cloud-success');
                        autoConnectionStatus.querySelector('.cloud-icon').textContent = '☁️';
                        autoConnectionStatus.querySelector('.cloud-text').textContent = 'Cloud APIs Connected & Ready!';
                        autoConnectionStatus.querySelector('.sparkle-icon').textContent = '✨';
                    } else {
                        autoConnectionStatus.classList.remove('cloud-success');
                        autoConnectionStatus.classList.add('cloud-error');
                        autoConnectionStatus.querySelector('.cloud-icon').textContent = '⚠️';
                        autoConnectionStatus.querySelector('.cloud-text').textContent = 'Cloud APIs Disconnected';
                        autoConnectionStatus.querySelector('.sparkle-icon').textContent = '';
                    }
                }
            } catch (e) {
                console.error("Auto-verify failed", e);
                if (autoConnectionStatus) {
                    autoConnectionStatus.classList.remove('hidden', 'cloud-success');
                    autoConnectionStatus.classList.add('cloud-error');
                    autoConnectionStatus.querySelector('.cloud-icon').textContent = '⚠️';
                    autoConnectionStatus.querySelector('.cloud-text').textContent = 'Cloud APIs Disconnected';
                    autoConnectionStatus.querySelector('.sparkle-icon').textContent = '';
                }
            }
        } else {
            if (autoConnectionStatus) {
                autoConnectionStatus.classList.remove('hidden', 'cloud-success');
                autoConnectionStatus.classList.add('cloud-error');
                autoConnectionStatus.querySelector('.cloud-icon').textContent = '⚠️';
                autoConnectionStatus.querySelector('.cloud-text').textContent = 'API Keys Missing';
                autoConnectionStatus.querySelector('.sparkle-icon').textContent = '';
            }
        }
    };
    verifyConnection();

    // Elements
    const languageSelect = document.getElementById('languageSelect');
    const deckSelect = document.getElementById('deckSelect');
    const newDeckInput = document.getElementById('newDeckInput');
    const toggleNewDeckBtn = document.getElementById('toggleNewDeckBtn');
    const modelSelect = document.getElementById('modelSelect');
    const translationSelect = document.getElementById('translationSelect');
    const promptInput = document.getElementById('promptInput');
    const resetPromptBtn = document.getElementById('resetPromptBtn');
    const geminiKeyInput = document.getElementById('geminiKey');
    const awsAccessKeyInput = document.getElementById('awsAccessKey');
    const awsSecretKeyInput = document.getElementById('awsSecretKey');
    const verifyKeysBtn = document.getElementById('verifyKeysBtn');
    const verifyKeysStatus = document.getElementById('verifyKeysStatus');
    const productionCardToggle = document.getElementById('productionCardToggle');
    const commonPhrasesToggle = document.getElementById('commonPhrasesToggle');
    const smartGrammarToggle = document.getElementById('smartGrammarToggle');
    const listeningCardToggle = document.getElementById('listeningCardToggle');
    const sentenceClozeToggle = document.getElementById('sentenceClozeToggle');
    const useOriginalCardBtn = document.getElementById('useOriginalCardBtn');
    const revertLearningFeaturesBtn = document.getElementById('revertLearningFeaturesBtn');
    const learningFeatureStatus = document.getElementById('learningFeatureStatus');

    let isCreatingNewDeck = false;
    let promptWasEdited = false;

    // Load saved settings
    if (languageSelect) languageSelect.value = localStorage.getItem('language') || 'Italian';
    if (translationSelect) translationSelect.value = localStorage.getItem('translationLang') || 'Both (English + Persian)';
    if (geminiKeyInput) geminiKeyInput.value = localStorage.getItem('geminiKey') || '';
    if (awsAccessKeyInput) awsAccessKeyInput.value = localStorage.getItem('awsAccessKey') || '';
    if (awsSecretKeyInput) awsSecretKeyInput.value = localStorage.getItem('awsSecretKey') || '';
    if (promptInput) promptInput.value = localStorage.getItem('customPrompt') || '';
    if (productionCardToggle) {
        productionCardToggle.checked = localStorage.getItem(LEARNING_FEATURE_KEYS.production) !== 'false';
    }
    if (commonPhrasesToggle) {
        commonPhrasesToggle.checked = localStorage.getItem(LEARNING_FEATURE_KEYS.phrases) !== 'false';
    }
    if (smartGrammarToggle) {
        smartGrammarToggle.checked = localStorage.getItem(LEARNING_FEATURE_KEYS.grammar) !== 'false';
    }
    if (listeningCardToggle) {
        listeningCardToggle.checked = localStorage.getItem(LEARNING_FEATURE_KEYS.listening) === 'true';
    }
    if (sentenceClozeToggle) {
        sentenceClozeToggle.checked = localStorage.getItem(LEARNING_FEATURE_KEYS.cloze) === 'true';
    }

    const saveKeys = () => {
        if (geminiKeyInput) localStorage.setItem('geminiKey', geminiKeyInput.value.trim());
        if (awsAccessKeyInput) localStorage.setItem('awsAccessKey', awsAccessKeyInput.value.trim());
        if (awsSecretKeyInput) localStorage.setItem('awsSecretKey', awsSecretKeyInput.value.trim());
    };
    
    // Save on blur/change
    if (geminiKeyInput) geminiKeyInput.addEventListener('blur', saveKeys);
    if (awsAccessKeyInput) awsAccessKeyInput.addEventListener('blur', saveKeys);
    if (awsSecretKeyInput) awsSecretKeyInput.addEventListener('blur', saveKeys);
    if (languageSelect) languageSelect.addEventListener('change', (e) => localStorage.setItem('language', e.target.value));
    if (translationSelect) translationSelect.addEventListener('change', (e) => localStorage.setItem('translationLang', e.target.value));
    if (promptInput) {
        promptInput.addEventListener('input', () => {
            promptWasEdited = true;
        });
        promptInput.addEventListener('blur', () => {
            if (!promptWasEdited) return;
            localStorage.setItem('customPrompt', promptInput.value);
            localStorage.setItem('customPromptIsManual', 'true');
            promptWasEdited = false;
        });
    }
    
    if (deckSelect) deckSelect.addEventListener('change', (e) => localStorage.setItem('deckName', e.target.value));
    if (modelSelect) modelSelect.addEventListener('change', (e) => localStorage.setItem('modelName', e.target.value));
    if (newDeckInput) newDeckInput.addEventListener('blur', (e) => localStorage.setItem('newDeckName', e.target.value));
    if (productionCardToggle) {
        productionCardToggle.addEventListener('change', () => {
            localStorage.setItem(LEARNING_FEATURE_KEYS.production, String(productionCardToggle.checked));
        });
    }
    if (commonPhrasesToggle) {
        commonPhrasesToggle.addEventListener('change', () => {
            localStorage.setItem(LEARNING_FEATURE_KEYS.phrases, String(commonPhrasesToggle.checked));
        });
    }
    if (smartGrammarToggle) {
        smartGrammarToggle.addEventListener('change', () => {
            localStorage.setItem(LEARNING_FEATURE_KEYS.grammar, String(smartGrammarToggle.checked));
        });
    }
    if (listeningCardToggle) {
        listeningCardToggle.addEventListener('change', () => {
            localStorage.setItem(LEARNING_FEATURE_KEYS.listening, String(listeningCardToggle.checked));
        });
    }
    if (sentenceClozeToggle) {
        sentenceClozeToggle.addEventListener('change', () => {
            localStorage.setItem(LEARNING_FEATURE_KEYS.cloze, String(sentenceClozeToggle.checked));
        });
    }

    if (useOriginalCardBtn) {
        useOriginalCardBtn.addEventListener('click', () => {
            for (const [toggle, key] of [
                [productionCardToggle, LEARNING_FEATURE_KEYS.production],
                [commonPhrasesToggle, LEARNING_FEATURE_KEYS.phrases],
                [smartGrammarToggle, LEARNING_FEATURE_KEYS.grammar],
                [listeningCardToggle, LEARNING_FEATURE_KEYS.listening],
                [sentenceClozeToggle, LEARNING_FEATURE_KEYS.cloze]
            ]) {
                if (toggle) toggle.checked = false;
                localStorage.setItem(key, 'false');
            }
            if (learningFeatureStatus) {
                learningFeatureStatus.textContent = 'Original layout selected for all newly generated words.';
                learningFeatureStatus.style.color = 'var(--text-secondary)';
            }
        });
    }

    if (revertLearningFeaturesBtn) {
        revertLearningFeaturesBtn.addEventListener('click', async () => {
            const modelName = (modelSelect && modelSelect.value)
                || localStorage.getItem('modelName')
                || 'Italian Vocab';
            const confirmed = window.confirm(
                `Revert the three learning additions in "${modelName}"?\n\n`
                + 'This deletes Production recall cards and their review history, '
                + 'removes their two app-owned fields, and removes the app-owned '
                + 'Common phrases / Smart grammar block from existing notes.\n\n'
                + 'Original recognition cards, Word Family, and audio stay unchanged.'
            );
            if (!confirmed) return;

            revertLearningFeaturesBtn.disabled = true;
            if (learningFeatureStatus) {
                learningFeatureStatus.textContent = 'Checking app-owned additions in Anki…';
                learningFeatureStatus.style.color = 'var(--text-secondary)';
            }

            try {
                const revertResult = await revertLearningFeaturesInAnki(
                    modelName
                );

                for (const [toggle, key] of [
                    [productionCardToggle, LEARNING_FEATURE_KEYS.production],
                    [commonPhrasesToggle, LEARNING_FEATURE_KEYS.phrases],
                    [smartGrammarToggle, LEARNING_FEATURE_KEYS.grammar]
                ]) {
                    if (toggle) toggle.checked = false;
                    localStorage.setItem(key, 'false');
                }
                if (learningFeatureStatus) {
                    learningFeatureStatus.textContent =
                        'Revert complete. '
                        + (
                            revertResult.productionRemoved
                                ? 'Production cards and fields were removed. '
                                : ''
                        )
                        + 'Removed optional blocks from '
                        + `${revertResult.updatedNotes} existing note`
                        + `${revertResult.updatedNotes === 1 ? '' : 's'}. `
                        + 'Original recognition cards, Word Family, and audio were kept.';
                    learningFeatureStatus.style.color = '#34a853';
                }
            } catch (error) {
                if (learningFeatureStatus) {
                    learningFeatureStatus.textContent =
                        error.message || 'Could not safely revert the added features.';
                    learningFeatureStatus.style.color = 'var(--error-color)';
                }
            } finally {
                revertLearningFeaturesBtn.disabled = false;
            }
        });
    }

    // Verify Keys Logic
    if (verifyKeysBtn) {
        verifyKeysBtn.addEventListener('click', async () => {
            saveKeys();
            const gemini = geminiKeyInput.value.trim();
            const aws_access = awsAccessKeyInput.value.trim();
            const aws_secret = awsSecretKeyInput.value.trim();
            
            if (!gemini || !aws_access || !aws_secret) {
                verifyKeysStatus.innerHTML = '<span style="color:var(--error-color)">Missing keys</span>';
                return;
            }
            
            verifyKeysBtn.disabled = true;
            verifyKeysBtn.textContent = 'Verifying...';
            verifyKeysStatus.innerHTML = '';
            
            try {
                const response = await fetch('/api/verify-keys', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ apiKeys: { gemini, aws_access, aws_secret } })
                });
                const data = await response.json();
                
                if (data.error) {
                    verifyKeysStatus.innerHTML = `<span style="color:var(--error-color); display:inline-block; max-width:200px; font-size:11px; line-height:1.2;">❌ ${data.error}</span>`;
                } else if (data.gemini && data.aws) {
                    verifyKeysStatus.innerHTML = '<span style="color:#34a853">✅ Connected & Verified!</span>';
                } else {
                    verifyKeysStatus.innerHTML = '<span style="color:var(--error-color)">❌ Verification failed</span>';
                }
            } catch (err) {
                verifyKeysStatus.innerHTML = '<span style="color:var(--error-color)">❌ Connection error</span>';
            } finally {
                verifyKeysBtn.disabled = false;
                verifyKeysBtn.textContent = 'Verify Connection';
            }
        });
    }

    // Toggle new deck logic
    if (toggleNewDeckBtn) {
        toggleNewDeckBtn.addEventListener('click', () => {
            isCreatingNewDeck = !isCreatingNewDeck;
            localStorage.setItem('isCreatingNewDeck', isCreatingNewDeck ? 'true' : 'false');
            if (isCreatingNewDeck) {
                deckSelect.classList.add('hidden');
                newDeckInput.classList.remove('hidden');
                newDeckInput.focus();
                toggleNewDeckBtn.textContent = '📋';
                toggleNewDeckBtn.title = 'Select existing deck';
            } else {
                newDeckInput.classList.add('hidden');
                deckSelect.classList.remove('hidden');
                toggleNewDeckBtn.textContent = '➕';
                toggleNewDeckBtn.title = 'Create new deck';
            }
        });
        
        // Restore state
        if (localStorage.getItem('isCreatingNewDeck') === 'true') {
            toggleNewDeckBtn.click();
            if (newDeckInput) newDeckInput.value = localStorage.getItem('newDeckName') || '';
        }
    }

    // Keep the default prompt current unless the user intentionally edits it.
    if (promptInput && !hasManualCustomPrompt()) {
        try {
            const resp = await fetch('/api/prompt');
            const data = await resp.json();
            promptInput.value = data.prompt;
            localStorage.setItem('customPrompt', data.prompt);
            if (data.version) {
                localStorage.setItem('customPromptVersion', data.version);
            }
            localStorage.setItem('customPromptIsManual', 'false');
            promptWasEdited = false;
        } catch (e) {
            console.error("Failed to load prompt:", e);
        }
    }

    // Reset prompt logic
    if (resetPromptBtn) {
        resetPromptBtn.addEventListener('click', async () => {
            try {
                const resp = await fetch('/api/prompt');
                const data = await resp.json();
                promptInput.value = data.prompt;
                localStorage.setItem('customPrompt', data.prompt);
                if (data.version) {
                    localStorage.setItem('customPromptVersion', data.version);
                }
                localStorage.setItem('customPromptIsManual', 'false');
                promptWasEdited = false;
            } catch (e) {
                console.error("Failed to load prompt:", e);
            }
        });
    }

    // Load Anki Data
    try {
        const decks = await invokeAnki('deckNames');
        if (deckSelect) {
            deckSelect.innerHTML = decks.map(d => `<option value="${d}">${d}</option>`).join('');
            const preferredDeck = localStorage.getItem('deckName') || 'Italian';
            if (decks.includes(preferredDeck)) {
                deckSelect.value = preferredDeck;
            }
            if (deckSelect.value) {
                localStorage.setItem('deckName', deckSelect.value);
            }
        }
        
        const APP_DEFAULT_MODEL = 'Italian Vocab';
        await ensureNoteType(APP_DEFAULT_MODEL);
        const models = (await invokeAnki('modelNames')) || [];
        if (modelSelect) {
            const BUILTIN_MODELS = new Set([
                'Basic', 'Basic (and reversed card)',
                'Basic (optional reversed card)', 'Basic (type in the answer)',
                'Cloze', 'Image Occlusion'
            ]);

            const modelList = models.includes(APP_DEFAULT_MODEL)
                ? models
                : [APP_DEFAULT_MODEL, ...models];

            modelSelect.innerHTML = modelList.map(m => `<option value="${m}">${m}</option>`).join('');

            const savedModel = localStorage.getItem('modelName');
            const preferredModel = (savedModel && modelList.includes(savedModel) && !BUILTIN_MODELS.has(savedModel))
                ? savedModel
                : APP_DEFAULT_MODEL;

            modelSelect.value = preferredModel;
            localStorage.setItem('modelName', preferredModel);
        }
    } catch (e) {
        console.error("AnkiConnect not available yet.", e);
    }
});
