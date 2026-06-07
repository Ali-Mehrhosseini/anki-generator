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
                if (!data.error && data.gemini && data.aws) {
                    if (autoConnectionStatus) {
                        autoConnectionStatus.classList.remove('hidden');
                    }
                }
            } catch (e) {
                console.error("Auto-verify failed", e);
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

    let isCreatingNewDeck = false;

    // Load saved settings
    if (languageSelect) languageSelect.value = localStorage.getItem('language') || 'Italian';
    if (translationSelect) translationSelect.value = localStorage.getItem('translationLang') || 'Both (English + Persian)';
    if (geminiKeyInput) geminiKeyInput.value = localStorage.getItem('geminiKey') || '';
    if (awsAccessKeyInput) awsAccessKeyInput.value = localStorage.getItem('awsAccessKey') || '';
    if (awsSecretKeyInput) awsSecretKeyInput.value = localStorage.getItem('awsSecretKey') || '';
    if (promptInput) promptInput.value = localStorage.getItem('customPrompt') || '';

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
    if (promptInput) promptInput.addEventListener('blur', () => localStorage.setItem('customPrompt', promptInput.value));
    
    if (deckSelect) deckSelect.addEventListener('change', (e) => localStorage.setItem('deckName', e.target.value));
    if (modelSelect) modelSelect.addEventListener('change', (e) => localStorage.setItem('modelName', e.target.value));
    if (newDeckInput) newDeckInput.addEventListener('blur', (e) => localStorage.setItem('newDeckName', e.target.value));

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

    // Fetch initial prompt if empty
    if (promptInput && !promptInput.value) {
        try {
            const resp = await fetch('/api/prompt');
            const data = await resp.json();
            promptInput.value = data.prompt;
            localStorage.setItem('customPrompt', data.prompt);
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
            const savedDeck = localStorage.getItem('deckName');
            if (savedDeck && decks.includes(savedDeck)) {
                deckSelect.value = savedDeck;
            }
        }
        
        const models = await invokeAnki('modelNames');
        if (modelSelect) {
            modelSelect.innerHTML = models.map(m => `<option value="${m}">${m}</option>`).join('');
            const savedModel = localStorage.getItem('modelName');
            if (savedModel && models.includes(savedModel)) {
                modelSelect.value = savedModel;
            }
        }
    } catch (e) {
        console.error("AnkiConnect not available yet.", e);
    }
});
