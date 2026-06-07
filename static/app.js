document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('wordForm');
    const wordInput = document.getElementById('wordInput');
    const generateBtn = document.getElementById('generateBtn');
    const btnText = document.querySelector('.btn-text');
    const spinner = document.querySelector('.spinner');
    const statusMessage = document.getElementById('statusMessage');
    
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
        setLoading(true);
        previewSection.classList.add('hidden');
        statusMessage.classList.add('hidden');
        statusMessage.className = '';
        frontAudioControls.innerHTML = '';
        backAudioControls.innerHTML = '';
        
        try {
            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ word })
            });

            const data = await response.json();

            if (data.success) {
                showSuccess(`Successfully generated and added note ID: ${data.note_id}`);
                
                // Strip [sound:...] tags from the preview since the browser doesn't natively render them,
                // and we already have the interactive pill buttons at the bottom!
                const cleanFront = data.data.front_html.replace(/\[sound:.*?\.mp3\]/g, '');
                const cleanBack = data.data.back_html.replace(/\[sound:.*?\.mp3\]/g, '');
                
                frontHtml.innerHTML = cleanFront;
                backHtml.innerHTML = cleanBack;
                
                renderAudioControls(data.audios);

                previewSection.classList.remove('hidden');
                wordInput.classList.remove('error-shake');
            } else {
                if (data.error && data.error.includes("duplicate")) {
                    showError("This word is already in your Anki deck!");
                    wordInput.classList.add('error-shake');
                    setTimeout(() => wordInput.classList.remove('error-shake'), 600);
                } else {
                    showError(data.error || "An unknown error occurred");
                    wordInput.classList.remove('error-shake');
                }
            }
        } catch (err) {
            showError("Failed to connect to the server. Is the Flask app running?");
        } finally {
            setLoading(false);
        }
    });

    function setLoading(isLoading) {
        wordInput.disabled = isLoading;
        generateBtn.disabled = isLoading;
        if (isLoading) {
            btnText.classList.add('hidden');
            spinner.classList.remove('hidden');
        } else {
            btnText.classList.remove('hidden');
            spinner.classList.add('hidden');
        }
    }

    function showSuccess(msg) {
        statusMessage.textContent = msg;
        statusMessage.className = 'success';
        statusMessage.classList.remove('hidden');
    }

    function showError(msg) {
        statusMessage.textContent = msg;
        statusMessage.className = 'error';
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

        const pronouns = ["_io", "_tu", "_lui", "_noi", "_voi", "_loro"];
        pronouns.forEach(p => {
            if (audios[p]) {
                const btn = document.createElement('button');
                btn.className = 'play-audio-btn';
                btn.innerHTML = `${playIcon} ${p.replace('_', '')}`;
                btn.onclick = () => playBase64Audio(audios[p]);
                backAudioControls.appendChild(btn);
            }
        });
    }

    function playBase64Audio(base64Str) {
        const audio = new Audio("data:audio/mp3;base64," + base64Str);
        audio.play().catch(e => console.error("Error playing audio:", e));
    }

    // Anki Status Polling
    const ankiStatusIndicator = document.getElementById('ankiStatus');
    
    async function checkAnkiStatus() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            
            if (data.status === 'online') {
                ankiStatusIndicator.className = 'status-indicator status-online';
                ankiStatusIndicator.title = 'Anki is connected and running';
            } else {
                ankiStatusIndicator.className = 'status-indicator status-offline';
                ankiStatusIndicator.title = 'Anki is not running. Please open Anki.';
            }
        } catch (error) {
            ankiStatusIndicator.className = 'status-indicator status-offline';
            ankiStatusIndicator.title = 'Cannot connect to the local server.';
        }
    }

    // Check immediately on load, then every 5 seconds
    checkAnkiStatus();
    setInterval(checkAnkiStatus, 5000);
});
