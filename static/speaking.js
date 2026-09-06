(() => {
    'use strict';

    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const defaults = {
        rounds: 3,
        minimum_seconds: 0,
        minimum_words: 1,
        max_feedback_attempts: 2,
        preparation_seconds: 5,
    };
    const elements = Object.fromEntries([
        'intro', 'startSprint', 'status', 'sprint', 'roundLabel', 'attemptLabel',
        'dailyProgress', 'dailyRing', 'progressFill', 'roundTitle', 'promptEn', 'promptFa', 'targets',
        'coachStrip', 'phaseLabel', 'hintPanel', 'hintText', 'hintButton', 'changeSentence',
        'promptCard', 'recordClock', 'recordButton', 'recordButtonText', 'recordHint',
        'liveCaptions', 'captionFinal', 'captionInterim',
        'wordHelpPanel', 'wordHelpWord', 'wordHelpClose', 'wordHelpShape',
        'wordHelpGuess', 'wordHelpGuessBtn', 'wordHelpGuessFeedback',
        'wordHelpHintBlock', 'wordHelpHint', 'wordHelpHintFa',
        'wordHelpMeaning', 'wordHelpLemma', 'wordHelpPos',
        'wordHelpMeaningEn', 'wordHelpMeaningFa',
        'wordHelpExample', 'wordHelpExampleEn',
        'wordHelpDeep', 'wordHelpUsage', 'wordHelpUsageFa',
        'wordHelpFormIt', 'wordHelpFormEn', 'wordHelpFormFa',
        'wordHelpNote', 'wordHelpNoteFa', 'wordHelpDeepStatus',
        'wordHelpShow', 'wordHelpPlay', 'wordHelpAdd', 'wordHelpStatus',
        'wordHelpMnemonic', 'wordHelpMnemonicBlock', 'wordHelpKeyword',
        'wordHelpImage', 'wordHelpImageFa',
        'transcriptPanel', 'transcriptText', 'durationLabel', 'transcriptWrong',
        'transcriptUncertain', 'transcriptSource',
        'ownRecording', 'fluencyMetrics', 'checkButton',
        'feedback', 'modelPanel', 'modelAnswer', 'playModel', 'shadowHint',
        'correctPanel', 'correctSentence', 'pollyVoice', 'playCorrect', 'correctAudioStatus',
        'pronunciationPanel', 'pronunciationTitle', 'pronunciationTip', 'pronunciationTipFa',
        'patternPanel', 'patternTitle', 'patternExplanation', 'patternExplanationFa',
        'patternAlternativeWrap', 'patternAlternative', 'patternRegister',
        'patternRegisterFa',
        'nextRound', 'summary', 'summaryRounds', 'summarySeconds',
        'lapBtn',
        'summaryRetries', 'summaryHints', 'summaryCoach', 'newSprint',
    ].map(id => [id, document.getElementById(id)]));

    let settings = { ...defaults };
    let session = null;
    let roundNumber = 1;
    let attempt = 1;
    let recognition = null;
    let captureStream = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let audioContext = null;
    let audioAnalyser = null;
    let voiceMonitorTimer = null;
    let voicedFrames = 0;
    let peakVoiceLevel = 0;
    let voiceActivitySupported = false;
    let firstVoiceDelay = null;
    let currentSilentFrames = 0;
    let longestSilentFrames = 0;
    let lastAudioBlob = null;
    let stopRequested = false;
    let recording = false;
    let preparing = false;
    let shadowMode = false;
    let shadowListened = false;
    let transcript = '';
    // The browser's caption preview, kept so the final Gemini transcription
    // can be compared against what the live preview showed.
    let lastCaptionPreview = '';
    let recordingStartedAt = 0;
    let lastDuration = 0;
    let clockTimer = null;
    let preparationTimer = null;
    // Caption-only recognizer: shows the words while you speak. It never
    // feeds the graded transcript — Gemini still judges the audio itself.
    let captionRecognition = null;
    let captionWanted = false;
    let captionServiceFailed = false;
    let totalSeconds = 0;
    let retries = 0;
    let hintsUsed = 0;
    let correctAudio = null;
    let correctAudioUrl = '';
    let correctAudioSentence = '';
    let correctAudioVoice = '';
    let ownRecordingUrl = '';
    // Direct audio evaluation is the reliable default. The Web Speech service
    // is network-dependent and repeatedly fails in embedded browsers.
    let speechServiceDisabled = true;
    let patternShadowMode = false;
    let seenWords = new Set();
    let transferMode = false;
    let pendingTransferTask = null;
    let nextAction = 'round';
    let completedProductions = 0;
    let dailyCorrect = 0;
    let dailyGoal = 0;
    // 4/3/2 fluency drill: the same sentence delivered three times, each
    // lap with 75% of the previous one's time. Pure pace work — no grading.
    let lapMode = false;
    let lapsCompleted = 0;
    let lapTargetSeconds = 0;
    let lastSuccessSeconds = 0;
    // Word help state: one cached fetch per English word per sprint, plus
    // which words have already been revealed or added to Anki.
    let wordHelpCache = new Map();
    let wordHelpDeepLoading = new Set();
    let activeWordHelp = null;
    let wordHelpGuesses = 0;
    let wordHelpAudio = null;
    let wordHelpAudioUrl = '';
    let wordHelpAudioSentence = '';

    const escapeHtml = value => String(value || '').replace(/[&<>"']/g, character => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[character]));

    function setStatus(message, type = '') {
        elements.status.textContent = message;
        elements.status.className = `speaking-status${type ? ` ${type}` : ''}`;
    }

    function hideStatus() {
        elements.status.classList.add('hidden');
    }

    function stopCorrectAudio() {
        correctAudio?.pause();
        correctAudio = null;
        if (correctAudioUrl) URL.revokeObjectURL(correctAudioUrl);
        correctAudioUrl = '';
        correctAudioSentence = '';
        correctAudioVoice = '';
    }

    function stopOwnRecording() {
        elements.ownRecording.pause();
        elements.ownRecording.removeAttribute('src');
        elements.ownRecording.load();
        elements.ownRecording.classList.add('hidden');
        if (ownRecordingUrl) URL.revokeObjectURL(ownRecordingUrl);
        ownRecordingUrl = '';
    }

    function showOwnRecording(blob) {
        stopOwnRecording();
        if (!blob?.size) return;
        ownRecordingUrl = URL.createObjectURL(blob);
        elements.ownRecording.src = ownRecordingUrl;
        elements.ownRecording.classList.remove('hidden');
    }

    function apiKey() {
        return localStorage.getItem('geminiKey') || '';
    }

    function formatClock(seconds) {
        const safe = Math.max(0, Math.floor(seconds));
        return `${String(Math.floor(safe / 60)).padStart(2, '0')}:${String(safe % 60).padStart(2, '0')}`;
    }

    function elapsedSeconds() {
        return recordingStartedAt ? (Date.now() - recordingStartedAt) / 1000 : 0;
    }

    function minimumDuration() {
        return settings.minimum_seconds;
    }

    function updateClock() {
        const elapsed = elapsedSeconds();
        elements.recordClock.textContent = formatClock(elapsed);
        setRecordHint(shadowMode
            ? 'Repeat the complete model answer, then stop.'
            : 'Say the complete Italian sentence, then stop.');
        elements.recordButton.classList.remove('minimum-pending');
    }

    function stopTimers() {
        window.clearInterval(clockTimer);
        window.clearInterval(preparationTimer);
        clockTimer = null;
        preparationTimer = null;
    }

    function stopVoiceMonitor() {
        window.clearInterval(voiceMonitorTimer);
        voiceMonitorTimer = null;
        if (audioContext) audioContext.close().catch(() => {});
        audioContext = null;
        audioAnalyser = null;
    }

    function speechWasDetected() {
        // A breath can produce two or three weak frames; real speech holds
        // half a second of clearly voiced audio.
        return voiceActivitySupported && voicedFrames >= 5 && peakVoiceLevel >= 0.03;
    }

    function currentFluency(wordCount = 0) {
        const duration = Math.max(lastDuration, 0.1);
        return {
            words_per_minute: Math.min(400, Math.round((wordCount / duration) * 600) / 10),
            voice_ratio: Math.min(1, Math.round(((voicedFrames * 0.1) / duration) * 100) / 100),
            start_delay_seconds: Math.round((firstVoiceDelay || 0) * 10) / 10,
            longest_pause_seconds: Math.round(longestSilentFrames) / 10,
        };
    }

    function showFluency(wordCount) {
        const value = currentFluency(wordCount);
        elements.fluencyMetrics.innerHTML = `
            <span><small>Pace</small><strong>${value.words_per_minute} wpm</strong></span>
            <span><small>Voice time</small><strong>${Math.round(value.voice_ratio * 100)}%</strong></span>
            <span><small>Start</small><strong>${value.start_delay_seconds}s</strong></span>
            <span><small>Longest pause</small><strong>${value.longest_pause_seconds}s</strong></span>`;
        elements.fluencyMetrics.classList.remove('hidden');
    }

    function resetCapture({ preserveTranscript = false } = {}) {
        stopTimers();
        transcript = '';
        lastDuration = 0;
        recordingStartedAt = 0;
        recording = false;
        preparing = false;
        recognition = null;
        stopRequested = false;
        if (mediaRecorder?.state === 'recording') mediaRecorder.stop();
        stopVoiceMonitor();
        captureStream?.getTracks().forEach(track => track.stop());
        captureStream = null;
        mediaRecorder = null;
        audioChunks = [];
        voicedFrames = 0;
        peakVoiceLevel = 0;
        voiceActivitySupported = false;
        lastAudioBlob = null;
        firstVoiceDelay = null;
        currentSilentFrames = 0;
        longestSilentFrames = 0;
        elements.recordClock.textContent = '00:00';
        elements.recordButton.disabled = shadowMode && !shadowListened;
        elements.recordButton.classList.remove('recording', 'minimum-pending');
        elements.recordButton.setAttribute('aria-pressed', 'false');
        elements.recordButtonText.textContent = shadowMode ? 'Repeat the model aloud' : 'Prepare, then speak';
        setRecordHint(shadowMode
            ? 'Play the model answer first. Then repeat it aloud.'
            : 'You will get five seconds to prepare. Then say the complete Italian sentence.');
        elements.transcriptPanel.classList.toggle('hidden', !preserveTranscript);
        stopCaptionRecognition();
        hideLiveCaptions();
        if (!preserveTranscript) {
            stopOwnRecording();
            elements.fluencyMetrics.classList.add('hidden');
        }
        elements.transcriptWrong.classList.add('hidden');
        elements.checkButton.classList.add('hidden');
        elements.checkButton.disabled = true;
    }

    async function requestMicrophone() {
        if (!navigator.mediaDevices?.getUserMedia) {
            throw new Error('Microphone recording is unavailable in this browser.');
        }
        captureStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {
            throw new Error('This browser cannot verify that speech was recorded.');
        }
        audioContext = new AudioContextClass();
        audioAnalyser = audioContext.createAnalyser();
        audioAnalyser.fftSize = 2048;
        audioContext.createMediaStreamSource(captureStream).connect(audioAnalyser);
        await audioContext.resume();
        voiceActivitySupported = true;
    }

    function startAudioCapture() {
        if (!captureStream || !window.MediaRecorder) return;
        audioChunks = [];
        mediaRecorder = new MediaRecorder(captureStream);
        mediaRecorder.ondataavailable = event => {
            if (event.data?.size) audioChunks.push(event.data);
        };
        mediaRecorder.start();
        voicedFrames = 0;
        peakVoiceLevel = 0;
        firstVoiceDelay = null;
        currentSilentFrames = 0;
        longestSilentFrames = 0;
        if (audioAnalyser) {
            const samples = new Float32Array(audioAnalyser.fftSize);
            voiceMonitorTimer = window.setInterval(() => {
                audioAnalyser.getFloatTimeDomainData(samples);
                let energy = 0;
                for (const sample of samples) energy += sample * sample;
                const rms = Math.sqrt(energy / samples.length);
                peakVoiceLevel = Math.max(peakVoiceLevel, rms);
                if (rms >= 0.018) {
                    voicedFrames += 1;
                    if (firstVoiceDelay === null && recordingStartedAt) {
                        firstVoiceDelay = (Date.now() - recordingStartedAt) / 1000;
                    }
                    currentSilentFrames = 0;
                } else if (firstVoiceDelay !== null) {
                    currentSilentFrames += 1;
                    longestSilentFrames = Math.max(longestSilentFrames, currentSilentFrames);
                }
            }, 100);
        }
    }

    function stopAudioCapture() {
        return new Promise(resolve => {
            const recorder = mediaRecorder;
            const finish = () => {
                const type = recorder?.mimeType || 'audio/webm';
                const blob = new Blob(audioChunks, { type });
                stopVoiceMonitor();
                captureStream?.getTracks().forEach(track => track.stop());
                captureStream = null;
                mediaRecorder = null;
                audioChunks = [];
                resolve(blob);
            };
            if (!recorder || recorder.state === 'inactive') finish();
            else {
                recorder.addEventListener('stop', finish, { once: true });
                recorder.stop();
            }
        });
    }

    async function evaluateAudio(blob) {
        if (!blob?.size) throw new Error('The temporary recording was empty. Please record again.');
        const form = new FormData();
        form.append('audio', blob, 'practice.webm');
        form.append('geminiKey', apiKey());
        form.append('context', JSON.stringify({
            targets: session.targets,
            task: session.task,
            durationSeconds: lastDuration,
            attempt,
            round: roundNumber,
            phase: transferMode ? 'transfer' : 'translation',
            fluency: currentFluency(),
        }));
        const controller = new AbortController();
        let waitingSeconds = 0;
        const progressTimer = window.setInterval(() => {
            waitingSeconds += 1;
            // Progress belongs next to the recorder, where the learner is
            // already looking — not in the detached status box up top.
            elements.recordHint.textContent =
                `Gemini is listening and checking the recording… ${waitingSeconds}s`;
        }, 1000);
        const timeoutTimer = window.setTimeout(() => controller.abort(), 75_000);
        try {
            elements.recordButton.disabled = true;
            const response = await fetch('/api/learning-lab/audio-feedback', {
                method: 'POST',
                body: form,
                signal: controller.signal,
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not evaluate the recording.');
            return data;
        } catch (error) {
            if (error.name === 'AbortError') {
                throw new Error('Transcription took too long. Please record the sentence again.');
            }
            throw error;
        } finally {
            window.clearInterval(progressTimer);
            window.clearTimeout(timeoutTimer);
        }
    }

    function updateLiveCaptions(finalText, interimText) {
        elements.captionFinal.textContent = String(finalText || '').trim();
        elements.captionInterim.textContent = String(interimText || '').trim()
            ? ` ${String(interimText).trim()}`
            : '';
        lastCaptionPreview =
            `${String(finalText || '').trim()} ${String(interimText || '').trim()}`.trim();
        elements.liveCaptions.classList.remove('hidden');
        elements.liveCaptions.classList.add('speaking-recorder-pulse');
    }

    function hideLiveCaptions() {
        elements.captionFinal.textContent = '';
        elements.captionInterim.textContent = '';
        elements.liveCaptions.classList.add('hidden');
        elements.liveCaptions.classList.remove('speaking-recorder-pulse');
    }

    function stopCaptionRecognition() {
        captionWanted = false;
        const instance = captionRecognition;
        captionRecognition = null;
        if (!instance) return;
        instance.onresult = null;
        instance.onend = null;
        instance.onerror = null;
        try {
            instance.abort();
        } catch { /* already stopped */ }
    }

    function startCaptionRecognition() {
        if (!Recognition || captionServiceFailed || captionRecognition) return;
        captionWanted = true;
        let finalText = '';
        let interimText = '';
        const instance = new Recognition();
        instance.lang = 'it-IT';
        instance.interimResults = true;
        instance.continuous = true;
        instance.onresult = event => {
            interimText = '';
            for (let index = event.resultIndex; index < event.results.length; index += 1) {
                const text = event.results[index][0].transcript;
                if (event.results[index].isFinal) finalText += `${text} `;
                else interimText += `${text} `;
            }
            updateLiveCaptions(finalText, interimText);
        };
        instance.onerror = event => {
            if (event.error === 'no-speech' || event.error === 'aborted') return;
            // Captions are cosmetic: any service failure silently falls back
            // to the hidden-until-stop behaviour without touching recording.
            captionServiceFailed = true;
            stopCaptionRecognition();
            hideLiveCaptions();
        };
        instance.onend = () => {
            captionRecognition = null;
            // Chrome ends the service after silence; restart to stay live.
            if (captionWanted && recording && !captionServiceFailed) {
                startCaptionRecognition();
            }
        };
        try {
            instance.start();
            captionRecognition = instance;
            // A new attempt starts with a clean caption preview.
            elements.captionFinal.textContent = '';
            elements.captionInterim.textContent = '';
            lastCaptionPreview = '';
        } catch {
            captionWanted = false;
            captionRecognition = null;
        }
    }

    function buildRecognition() {
        const instance = new Recognition();
        instance.lang = 'it-IT';
        instance.interimResults = true;
        instance.continuous = true;
        let finalText = '';
        let latestInterim = '';

        instance.onstart = () => {
            preparing = false;
            recording = true;
            recordingStartedAt = Date.now();
            stopRequested = false;
            startAudioCapture();
            elements.recordButton.disabled = false;
            elements.recordButton.classList.add('recording');
            elements.recordButton.setAttribute('aria-pressed', 'true');
            elements.recordButtonText.textContent = '■ Stop recording';
            updateClock();
            clockTimer = window.setInterval(updateClock, 200);
        };
        instance.onresult = event => {
            latestInterim = '';
            for (let index = event.resultIndex; index < event.results.length; index += 1) {
                const text = event.results[index][0].transcript;
                if (event.results[index].isFinal) finalText += `${text} `;
                else latestInterim += `${text} `;
            }
            transcript = `${finalText}${latestInterim}`.trim();
            updateLiveCaptions(finalText, latestInterim);
        };
        instance.onerror = event => {
            if (event.error === 'no-speech') return;
            if (event.error === 'network' || event.error === 'service-not-allowed') {
                speechServiceDisabled = true;
                sessionStorage.setItem('ankiSpeechServiceDisabled', '1');
                setStatus('Switched to direct audio mode. Keep speaking, then press Stop.', 'warning');
                return;
            }
            const friendly = {
                'not-allowed': 'Microphone permission was denied. Allow microphone access and try again.',
                'no-speech': 'No Italian speech was detected. Try again and speak clearly.',
                'audio-capture': 'No working microphone was found.',
                'network': 'The browser speech service could not be reached.',
            }[event.error] || `Speech recognition stopped: ${event.error}.`;
            setStatus(friendly, 'error');
        };
        instance.onend = () => {
            recognition = null;
            if (recording && !stopRequested) {
                elements.recordButtonText.textContent = '■ Stop and transcribe';
                elements.recordHint.textContent = 'Keep speaking, then press Stop. The audio fallback is listening.';
                return;
            }
            finishRecording().catch(error => setStatus(error.message, 'error'));
        };
        return instance;
    }

    function captionTranscriptsDiffer(preview, finalText) {
        const words = text => String(text || '').toLocaleLowerCase('it').match(/[\p{L}\p{N}']+/gu) || [];
        const previewWords = new Set(words(preview));
        const finalWords = new Set(words(finalText));
        if (!previewWords.size || !finalWords.size) return false;
        let shared = 0;
        previewWords.forEach(word => { if (finalWords.has(word)) shared += 1; });
        return shared / Math.max(previewWords.size, finalWords.size) < 0.6;
    }

    function renderTranscriptNotes(audioFeedback) {
        elements.transcriptUncertain.classList.toggle(
            'hidden',
            !audioFeedback?.transcription_uncertain,
        );
        const source = elements.transcriptSource;
        if (audioFeedback) {
            source.textContent = captionTranscriptsDiffer(lastCaptionPreview, transcript)
                ? "The live caption preview and this transcription differ — Gemini listened to your recording directly, and this version was graded."
                : "Transcribed by Gemini directly from your recording. The live captions were only a browser preview.";
        } else {
            source.textContent = "Recognized live by the browser; this text is what Gemini will grade.";
        }
        source.classList.remove('hidden');
    }

    function setRecordHint(message, type = '') {
        elements.recordHint.textContent = message;
        elements.recordHint.className = `speaking-record-hint${type ? ` ${type}` : ''}`.trim();
    }

    async function finishRecording() {
        if (!recordingStartedAt) return;
        elements.recordButton.disabled = true;
        lastDuration = Math.max(0, elapsedSeconds());
        recordingStartedAt = 0;
        recording = false;
        stopTimers();
        stopCaptionRecognition();
        const audioBlob = await stopAudioCapture();
        lastAudioBlob = audioBlob;
        if (lapMode) {
            // Fluency laps never touch grading — the clock is the only judge.
            completeLap();
            return;
        }
        elements.recordButton.classList.remove('recording', 'minimum-pending');
        elements.recordButton.setAttribute('aria-pressed', 'false');
        elements.recordButtonText.textContent = shadowMode ? 'Repeat again' : 'Record again';
        elements.recordClock.textContent = formatClock(lastDuration);

        if (!speechWasDetected()) {
            lastAudioBlob = null;
            transcript = '';
            elements.recordButton.disabled = false;
            elements.changeSentence.disabled = false;
            elements.recordHint.textContent = 'Say the sentence aloud, then press Stop.';
            setStatus('No voice was detected. This attempt was not sent to Gemini and was not counted.', 'warning');
            return;
        }
        totalSeconds += lastDuration;
        showOwnRecording(audioBlob);

        if (shadowMode && audioBlob.size) {
            hideStatus();
            elements.transcriptText.textContent = 'Model repetition recorded — play it back below.';
            elements.durationLabel.textContent = `${lastDuration.toFixed(1)} seconds`;
            elements.fluencyMetrics.classList.add('hidden');
            elements.transcriptPanel.classList.remove('hidden');
            elements.feedback.innerHTML = patternShadowMode
                ? '<div class="speaking-feedback-title">✓ New pattern repeated</div><p>You noticed, listened, and produced the authentic Italian pattern. It can be tested after another exposure.</p>'
                : '<div class="speaking-feedback-title">✓ Spoken repetition captured</div><p>You listened and produced the Italian model aloud. The next translation is unlocked.</p>';
            elements.feedback.className = 'speaking-feedback success';
            setNextAction(patternShadowMode && pendingTransferTask ? 'transfer' : 'round');
            elements.recordButton.disabled = true;
            patternShadowMode = false;
            return;
        }

        let audioFeedback = null;
        if (!transcript && !shadowMode) {
            setRecordHint('The browser heard no text — Gemini is checking the audio directly…');
            try {
                audioFeedback = await evaluateAudio(audioBlob);
                transcript = String(audioFeedback.transcript_it || '').trim();
            } catch (error) {
                // Recording-flow errors belong beside the recorder, not in
                // the detached status box at the top of the page.
                setRecordHint(`❌ ${error.message} — press Record again to try.`, 'error');
                elements.recordButton.disabled = false;
                return;
            }
        }
        const wordCount = transcript ? transcript.split(/\s+/u).filter(Boolean).length : 0;
        if (wordCount < settings.minimum_words) {
            setStatus('I could not hear any Italian words. Try again and speak a little closer to the microphone.', 'warning');
            transcript = '';
            elements.recordHint.textContent = 'Take a breath, then record the complete response again.';
            elements.recordButton.disabled = false;
            return;
        }
        // Hallucination guard: a transcript longer than the measured voice
        // time cannot be what was said (Gemini and browser recognizers both
        // tend to "complete" a half-silent clip toward the model answer).
        const plausibleWords = Math.floor(voicedFrames * 0.1 * 3) + 2;
        if (wordCount > plausibleWords) {
            transcript = '';
            lastAudioBlob = null;
            setStatus('The transcript was longer than the speech I measured, so this attempt was not graded or counted. Please record again.', 'warning');
            elements.recordHint.textContent = 'Say the complete sentence aloud, then press Stop.';
            elements.recordButton.disabled = false;
            return;
        }

        hideStatus();
        elements.recordButton.disabled = false;
        elements.transcriptText.textContent = transcript;
        elements.durationLabel.textContent = `${lastDuration.toFixed(1)} seconds`;
        showFluency(wordCount);
        elements.transcriptPanel.classList.remove('hidden');
        // The rough browser preview is replaced by the authoritative panel;
        // keeping both visible made it look like two conflicting answers.
        hideLiveCaptions();
        renderTranscriptNotes(audioFeedback);
        elements.transcriptWrong.classList.toggle('hidden', !lastAudioBlob?.size || shadowMode || Boolean(audioFeedback));
        if (!shadowMode) {
            if (audioFeedback) {
                elements.recordHint.textContent = audioFeedback.transcription_uncertain
                    ? 'Gemini was uncertain about part of the audio. Re-record if the transcript changed your meaning.'
                    : 'The temporary audio was transcribed and evaluated in one step.';
                handleFeedback(audioFeedback);
            } else {
                elements.checkButton.classList.remove('hidden');
                elements.checkButton.disabled = false;
                elements.recordHint.textContent = 'Review what the browser heard, then check your translation or record again.';
            }
        }
    }

    function beginRecognition() {
        try {
            if (!Recognition || speechServiceDisabled) {
                preparing = false;
                recording = true;
                recordingStartedAt = Date.now();
                stopRequested = false;
                startAudioCapture();
                startCaptionRecognition();
                elements.recordButton.disabled = false;
                elements.recordButton.classList.add('recording');
                elements.recordButton.setAttribute('aria-pressed', 'true');
                elements.recordButtonText.textContent = lapMode
                    ? '■ Stop the lap'
                    : '■ Stop and check audio';
                elements.recordHint.textContent = 'Direct audio mode is active. Say the complete sentence, then press Stop.';
                updateClock();
                clockTimer = window.setInterval(updateClock, 200);
                return;
            }
            recognition = buildRecognition();
            recognition.start();
        } catch (error) {
            preparing = false;
            elements.recordButton.disabled = false;
            elements.changeSentence.disabled = false;
            setStatus(`Could not start speech recognition: ${error.message}`, 'error');
        }
    }

    async function prepareAndRecord() {
        if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
            setStatus('Voice-only mode needs microphone recording support. Open this page in Chrome or Safari and try again.', 'error');
            return;
        }
        if (recording) {
            stopRequested = true;
            if (recognition) recognition.stop();
            else finishRecording().catch(error => setStatus(error.message, 'error'));
            return;
        }
        if (preparing) return;

        hideStatus();
        elements.changeSentence.disabled = true;
        elements.transcriptPanel.classList.add('hidden');
        elements.checkButton.classList.add('hidden');
        transcript = '';
        try {
            await requestMicrophone();
        } catch (error) {
            captureStream?.getTracks().forEach(track => track.stop());
            captureStream = null;
            stopVoiceMonitor();
            elements.changeSentence.disabled = false;
            setStatus(error.message || 'Microphone access is required for a voice-only sprint.', 'error');
            return;
        }

        preparing = true;
        elements.recordButton.disabled = true;
        let remaining = (shadowMode || lapMode) ? 1 : settings.preparation_seconds;
        elements.recordClock.textContent = String(remaining);
        elements.recordButtonText.textContent = 'Get ready…';
        setRecordHint(lapMode
            ? 'Same sentence — faster this time. Go on "Speak!"'
            : 'Plan the message in your head—do not write it.');
        preparationTimer = window.setInterval(() => {
            remaining -= 1;
            elements.recordClock.textContent = remaining > 0 ? String(remaining) : 'Speak!';
            if (remaining <= 0) {
                window.clearInterval(preparationTimer);
                preparationTimer = null;
                beginRecognition();
            }
        }, 1000);
    }

    function updateDailyDisplay() {
        if (!dailyGoal) {
            elements.dailyRing.classList.add('hidden');
            return;
        }
        elements.dailyRing.classList.remove('hidden');
        const percent = Math.min(100, Math.round((dailyCorrect / dailyGoal) * 100));
        elements.dailyRing.style.background =
            `conic-gradient(#73d88a ${percent}%, rgba(127,127,127,.28) 0)`;
        elements.dailyProgress.textContent = `Today ${dailyCorrect}/${dailyGoal}`;
    }

    function collapsePrompt() {
        elements.promptCard.classList.add('speaking-prompt-collapsed');
    }

    function expandPrompt({ sceneChange = false } = {}) {
        elements.promptCard.classList.remove('speaking-prompt-collapsed');
        elements.promptCard.classList.remove('speaking-scene-change');
        if (sceneChange) {
            // Restart the entrance animation so the new situation reads as a
            // fresh scene rather than an edit of the old one.
            void elements.promptCard.offsetWidth;
            elements.promptCard.classList.add('speaking-scene-change');
        }
    }

    function resetLaps() {
        lapMode = false;
        lapsCompleted = 0;
        lapTargetSeconds = 0;
        elements.lapBtn.classList.add('hidden');
    }

    function startLap() {
        if (!lastSuccessSeconds) return;
        lapMode = true;
        lapsCompleted = 0;
        lapTargetSeconds = Math.max(1.5, Math.round(lastSuccessSeconds * 0.75 * 10) / 10);
        elements.lapBtn.classList.add('hidden');
        elements.nextRound.classList.add('hidden');
        elements.feedback.classList.add('hidden');
        elements.correctPanel.classList.add('hidden');
        elements.attemptLabel.textContent = '⚡ Fluency laps';
        elements.recordButton.disabled = false;
        elements.recordButtonText.textContent = `Record lap 1 — under ${lapTargetSeconds.toFixed(1)}s`;
        setRecordHint(
            `4/3/2 drill: say the same sentence three times, each lap faster. ` +
            `Lap 1 target: ${lapTargetSeconds.toFixed(1)}s. The clock is already running in your head — go.`
        );
        elements.recordClock.textContent = '00:00';
        elements.recordButton.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function completeLap() {
        const elapsed = lastDuration;
        if (!speechWasDetected()) {
            setRecordHint('No voice caught in that lap — record it again.', 'error');
            elements.recordButton.disabled = false;
            return;
        }
        if (elapsed > lapTargetSeconds + 0.05) {
            setRecordHint(
                `⏱ ${elapsed.toFixed(1)}s — the target was ${lapTargetSeconds.toFixed(1)}s. ` +
                'Try the lap again, or continue below.'
            );
            elements.recordButton.disabled = false;
            elements.nextRound.classList.remove('hidden');
            return;
        }
        lapsCompleted += 1;
        if (lapsCompleted >= 3) {
            lapMode = false;
            elements.attemptLabel.textContent = '⚡ 3 laps done';
            setRecordHint('Three laps — that sentence is yours at speed now. Continue when ready.');
            elements.recordButton.disabled = true;
            elements.nextRound.textContent = nextAction === 'transfer'
                ? 'Use it in a new situation →'
                : 'Next round →';
            elements.nextRound.classList.remove('hidden');
            return;
        }
        lapTargetSeconds = Math.max(1.0, Math.round(elapsed * 0.75 * 10) / 10);
        elements.recordButton.disabled = false;
        elements.recordButtonText.textContent =
            `Record lap ${lapsCompleted + 1} — under ${lapTargetSeconds.toFixed(1)}s`;
        setRecordHint(
            `⚡ Lap ${lapsCompleted} done in ${elapsed.toFixed(1)}s. ` +
            `Lap ${lapsCompleted + 1} target: ${lapTargetSeconds.toFixed(1)}s.`
        );
    }

    function renderTargets(results = []) {
        const resultByWord = Object.fromEntries(results.map(result => [String(result.word || '').toLocaleLowerCase('it'), result]));
        elements.targets.innerHTML = (session.targets || []).map(target => {
            const result = resultByWord[String(target.word || '').toLocaleLowerCase('it')];
            const state = result ? (result.correct ? 'correct' : 'incorrect') : '';
            const icon = result ? (result.correct ? '✓ ' : '↻ ') : '';
            return `<span class="speaking-target ${state}">${icon}${escapeHtml(target.word)}</span>`;
        }).join('');
    }

    function renderFeedback(data) {
        if (data.evaluation_reliable === false) {
            elements.feedback.innerHTML = `
                <div class="speaking-feedback-title">Audio check needed</div>
                <p>${escapeHtml(data.overall_en)}</p>
                <p lang="fa" dir="rtl">${escapeHtml(data.overall_fa)}</p>`;
            elements.feedback.className = 'speaking-feedback warning';
            return;
        }
        const results = data.target_results || [];
        const targetOkay = results.length > 0 && results.every(result => result.used && result.correct);
        const grammarErrors = new Set(['word_form', 'grammar', 'collocation', 'spelling']);
        const grammarOkay = !results.some(result => grammarErrors.has(result.error_type));
        const audioLabel = data.transcription_uncertain ? 'Check transcript' : 'Clear enough';
        const detail = results.map(result => `
            <div class="speaking-target-result ${result.correct ? 'correct' : 'incorrect'}">
                <strong>${result.correct ? '✓' : '↻'} ${escapeHtml(result.word)}</strong>
                <p>${escapeHtml(result.feedback_en)}</p>
                <p lang="fa" dir="rtl">${escapeHtml(result.feedback_fa)}</p>
            </div>`).join('');
        const focus = data.focus || {};
        const focusedRepair = focus.category && focus.category !== 'none' ? `
            <div class="speaking-focused-correction">
                <small>One focus · ${escapeHtml(focus.category)}</small>
                <div class="speaking-fragment-change">
                    <span>${escapeHtml(focus.learner_fragment)}</span><b>→</b><strong>${escapeHtml(focus.corrected_fragment)}</strong>
                </div>
                <p>${escapeHtml(focus.explanation_en)}</p>
                <p lang="fa" dir="rtl">${escapeHtml(focus.explanation_fa)}</p>
            </div>` : '';
        elements.feedback.innerHTML = `
            <div class="speaking-feedback-title">${data.retry_needed ? 'Repair this translation' : '✓ Meaning transferred into Italian'}</div>
            <div class="speaking-feedback-dimensions">
                <span><small>Meaning</small><strong>${data.retry_needed ? 'Review' : 'Preserved'}</strong></span>
                <span><small>Grammar</small><strong>${grammarOkay ? 'Good' : 'Repair'}</strong></span>
                <span><small>Target</small><strong>${targetOkay ? 'Natural' : 'Repair'}</strong></span>
                <span><small>Audio</small><strong>${audioLabel}</strong></span>
            </div>
            <p>${escapeHtml(data.overall_en)}</p>
            <p lang="fa" dir="rtl">${escapeHtml(data.overall_fa)}</p>
            ${focusedRepair}
            ${detail}`;
        elements.feedback.className = `speaking-feedback ${data.retry_needed ? 'error' : 'success'}`;
        renderTargets(results);
    }

    function showCorrectSentence(data) {
        const sentence = String(
            (transferMode
                ? (data.corrected_response_it || session?.task?.model_it)
                : session?.targets?.[0]?.example_it)
            || data.corrected_response_it
            || ''
        ).trim();
        if (!sentence) {
            elements.correctPanel.classList.add('hidden');
            return;
        }
        stopCorrectAudio();
        elements.correctSentence.textContent = sentence;
        elements.correctAudioStatus.textContent = '';
        elements.playCorrect.disabled = false;
        elements.playCorrect.textContent = '🔊 Play with AWS Polly';
        elements.correctPanel.classList.remove('hidden');
    }

    function showPronunciation(data) {
        const pronunciation = data.pronunciation || {};
        const useful = data.evaluation_reliable !== false
            && pronunciation.confidence !== 'low'
            && (pronunciation.coaching_tip_en || pronunciation.focus_word);
        if (!useful) {
            elements.pronunciationPanel.classList.add('hidden');
            return;
        }
        const label = pronunciation.intelligibility === 'clear'
            ? 'Clearly understandable'
            : 'One sound to polish';
        elements.pronunciationTitle.textContent = pronunciation.focus_word
            ? `${label}: ${pronunciation.focus_word}`
            : label;
        elements.pronunciationTip.textContent = pronunciation.coaching_tip_en || pronunciation.observed_issue || '';
        elements.pronunciationTipFa.textContent = pronunciation.coaching_tip_fa || '';
        elements.pronunciationPanel.classList.remove('hidden');
    }

    function setNextAction(action) {
        nextAction = action;
        elements.nextRound.textContent = action === 'transfer'
            ? 'Use it in a new situation →'
            : 'Next round →';
        elements.nextRound.classList.remove('hidden');
    }

    function beginTransfer() {
        const task = pendingTransferTask;
        if (!task?.available || !task.prompt_en) {
            nextRound().catch(error => setStatus(error.message, 'error'));
            return;
        }
        transferMode = true;
        pendingTransferTask = null;
        attempt = 1;
        session.task = {
            ...session.task,
            title: task.scenario || 'Everyday transfer',
            task_type: 'transfer',
            prompt_en: task.prompt_en,
            prompt_fa: task.prompt_fa,
            source_en: task.prompt_en,
            model_it: task.model_it,
            hint_it: task.hint_it,
            hint_visible: false,
        };
        elements.phaseLabel.textContent = 'Use it in a new situation';
        elements.roundTitle.textContent = session.task.title;
        elements.promptEn.textContent = '';
        renderClickablePrompt(session.task.prompt_en);
        elements.promptFa.textContent = session.task.prompt_fa;
        elements.attemptLabel.textContent = 'Transfer';
        elements.hintText.textContent = session.task.hint_it || '';
        elements.hintPanel.classList.add('hidden');
        elements.hintButton.classList.toggle('hidden', !session.task.hint_it);
        elements.changeSentence.classList.add('hidden');
        closeWordHelp();
        elements.feedback.classList.add('hidden');
        elements.correctPanel.classList.add('hidden');
        elements.patternPanel.classList.add('hidden');
        elements.pronunciationPanel.classList.add('hidden');
        elements.modelPanel.classList.add('hidden');
        elements.nextRound.classList.add('hidden');
        stopCorrectAudio();
        resetCapture();
        resetLaps();
        expandPrompt({ sceneChange: true });
        elements.recordHint.textContent = 'Express the new meaning naturally. Do not repeat the previous answer from memory.';
        elements.promptCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function showNewPattern(data) {
        const pattern = data.new_pattern || {};
        if (!pattern.detected) {
            elements.patternPanel.classList.add('hidden');
            return false;
        }
        const badge = elements.patternPanel.querySelector('.speaking-pattern-badge');
        badge.textContent = pattern.first_exposure
            ? 'New pattern · not graded yet'
            : 'Familiar pattern · review';
        elements.patternTitle.textContent = pattern.label_it || 'Italian pattern';
        elements.patternExplanation.textContent = pattern.explanation_en || '';
        elements.patternExplanationFa.textContent = pattern.explanation_fa || '';
        elements.patternAlternative.textContent = pattern.everyday_alternative_it || '';
        elements.patternAlternativeWrap.classList.toggle(
            'hidden', !pattern.everyday_alternative_it
        );
        elements.patternRegister.textContent = pattern.register_note_en || '';
        elements.patternRegisterFa.textContent = pattern.register_note_fa || '';
        elements.patternPanel.classList.remove('hidden');
        return Boolean(pattern.first_exposure);
    }

    async function playCorrectSentence() {
        const sentence = elements.correctSentence.textContent.trim();
        const voice = elements.pollyVoice.value || 'Beatrice';
        if (!sentence) return;
        if (correctAudio && correctAudioSentence === sentence && correctAudioVoice === voice) {
            correctAudio.currentTime = 0;
            await correctAudio.play();
            return;
        }
        elements.playCorrect.disabled = true;
        elements.playCorrect.textContent = 'Preparing AWS Polly audio…';
        elements.correctAudioStatus.textContent = '';
        try {
            const response = await fetch('/api/learning-lab/polly', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sentence,
                    voice,
                    apiKeys: {
                        aws_access: localStorage.getItem('awsAccessKey') || '',
                        aws_secret: localStorage.getItem('awsSecretKey') || '',
                    },
                }),
            });
            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.error || 'AWS Polly could not create the audio.');
            }
            stopCorrectAudio();
            correctAudioUrl = URL.createObjectURL(await response.blob());
            correctAudioSentence = sentence;
            correctAudioVoice = voice;
            correctAudio = new Audio(correctAudioUrl);
            correctAudio.onended = () => {
                elements.playCorrect.textContent = '🔊 Play again';
                elements.correctAudioStatus.textContent = `AWS Polly · ${voice} · Italian`;
                if (patternShadowMode) {
                    shadowListened = true;
                    if (recording) {
                        // True shadowing: the learner spoke along — end the
                        // capture as the model finishes and keep the take.
                        stopRequested = true;
                        if (recognition) recognition.stop();
                        else finishRecording().catch(error => setStatus(error.message, 'error'));
                    } else {
                        elements.recordButton.disabled = false;
                        elements.recordButtonText.textContent = 'Repeat the new pattern aloud';
                        elements.recordHint.textContent = 'Repeat the complete correct sentence once. This is practice, not a test.';
                    }
                }
            };
            await correctAudio.play();
            elements.playCorrect.textContent = '🔊 Playing…';
            elements.correctAudioStatus.textContent = `AWS Polly · ${voice} · Italian`;
            if (patternShadowMode) {
                // Shadowing means speaking WITH the model, not after it —
                // open the recorder while the audio is still playing.
                elements.recordButton.disabled = false;
                elements.recordButtonText.textContent = '🎙 Shadow along now';
                setRecordHint('Speak along with the audio from the first word to the last. Recording stops when the model ends.');
            }
        } catch (error) {
            elements.correctAudioStatus.textContent = error.message;
            elements.playCorrect.textContent = '🔊 Try AWS Polly again';
        } finally {
            elements.playCorrect.disabled = false;
        }
    }

    // --- Clickable word help (hint ladder) --------------------------------

    function renderClickablePrompt(text) {
        const source = String(text || '');
        const html = source.split(/(\s+)/).map(token => {
            if (!token.trim()) return escapeHtml(token);
            const core = token.replace(/^[^\p{L}\p{N}']+|[^\p{L}\p{N}']+$/gu, '');
            if (core.length < 2 || !/\p{L}/u.test(core)) return escapeHtml(token);
            return `<span class="speaking-word" data-word="${escapeHtml(core)}" role="button" tabindex="0">${escapeHtml(token)}</span>`;
        }).join('');
        elements.promptEn.innerHTML = html;
    }

    function recordWordHelpEvent(word, event, guessedCorrectly) {
        // Fire-and-forget lookup tracking; never blocks the sprint.
        fetch('/api/learning-lab/word-help', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                word,
                event,
                guessedCorrectly: Boolean(guessedCorrectly),
                recordOnly: true,
            }),
        }).catch(() => {});
    }

    function wordShapeHint(word) {
        const letters = String(word || '').replace(/\s/g, '');
        if (!letters) return '';
        const first = letters[0].toLocaleLowerCase('it');
        if (letters.length <= 10) {
            return `${first} ${Array.from(letters.slice(1)).map(() => '_').join(' ')}`;
        }
        return `${first} ${'_ '.repeat(4)}… (${letters.length} letters)`;
    }

    function normalizeGuess(value) {
        return String(value || '')
            .toLocaleLowerCase('it')
            .replace(/^[^\p{L}\p{N}']+|[^\p{L}\p{N}']+$/gu, '')
            .replace(/\s+/gu, ' ')
            .trim();
    }

    function showWordHelpMeaning(help) {
        elements.wordHelpLemma.textContent = help.lemma_it || activeWordHelp || '';
        elements.wordHelpPos.textContent = help.part_of_speech
            ? `· ${help.part_of_speech}${help.gender ? ` (${help.gender})` : ''}` : '';
        elements.wordHelpMeaningEn.textContent = help.meaning_en || '';
        elements.wordHelpMeaningFa.textContent = help.meaning_fa || '';
        elements.wordHelpExample.textContent = help.example_it || '';
        elements.wordHelpExampleEn.textContent = help.example_en || '';
        elements.wordHelpMeaning.classList.remove('hidden');
        elements.wordHelpShow.classList.add('hidden');
        elements.wordHelpPlay.classList.toggle('hidden', !help.lemma_it);
        elements.wordHelpMnemonic.classList.toggle('hidden', !help.lemma_it);
        if (help.mnemonic) renderWordHelpMnemonic(help.mnemonic);
        else elements.wordHelpMnemonicBlock.classList.add('hidden');
        const addWord = help.lemma_it || activeWordHelp;
        elements.wordHelpAdd.href = `/?word=${encodeURIComponent(addWord)}`;
        elements.wordHelpAdd.classList.remove('hidden');
    }

    function renderWordHelpMnemonic(mnemonic) {
        elements.wordHelpKeyword.textContent = mnemonic.keyword_fa || '';
        elements.wordHelpImage.textContent = mnemonic.image_en || '';
        elements.wordHelpImageFa.textContent = mnemonic.image_fa || '';
        elements.wordHelpMnemonicBlock.classList.remove('hidden');
        elements.wordHelpMnemonic.classList.add('hidden');
    }

    async function loadWordHelpMnemonic() {
        const help = wordHelpCache.get(activeWordHelp);
        const lemma = elements.wordHelpLemma.textContent.trim()
            || help?.lemma_it
            || activeWordHelp;
        if (!lemma) return;
        elements.wordHelpMnemonic.disabled = true;
        elements.wordHelpMnemonic.textContent = '🧠 Thinking…';
        try {
            const response = await fetch('/api/learning-lab/word-help', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    word: lemma,
                    meaning: help?.meaning_en
                        || elements.wordHelpMeaningEn.textContent.trim(),
                    mnemonic: true,
                    geminiKey: apiKey(),
                }),
            });
            const mnemonic = await response.json();
            if (!response.ok) throw new Error(mnemonic.error || 'Could not create a memory trick.');
            if (help) help.mnemonic = mnemonic;
            renderWordHelpMnemonic(mnemonic);
        } catch (error) {
            elements.wordHelpStatus.textContent = error.message;
        } finally {
            elements.wordHelpMnemonic.disabled = false;
            elements.wordHelpMnemonic.textContent = '🧠 Memory trick';
        }
    }

    function revealWordHelp({ record = true } = {}) {
        const help = wordHelpCache.get(activeWordHelp);
        if (!help) return;
        help.revealed = true;
        showWordHelpMeaning(help);
        elements.wordHelpGuessBtn.disabled = true;
        elements.wordHelpGuess.disabled = true;
        if (record && activeWordHelp) recordWordHelpEvent(activeWordHelp, 'reveal');
    }

    function setWordHelpGuessFeedback(message, type) {
        elements.wordHelpGuessFeedback.textContent = message;
        elements.wordHelpGuessFeedback.className =
            `speaking-word-guess-feedback${type ? ` ${type}` : ''}`;
        elements.wordHelpGuessFeedback.classList.remove('hidden');
    }

    function checkWordGuess() {
        const help = wordHelpCache.get(activeWordHelp);
        const guess = normalizeGuess(elements.wordHelpGuess.value);
        if (!activeWordHelp || !help || !guess) return;
        wordHelpGuesses += 1;
        const answers = new Set([
            normalizeGuess(help.lemma_it),
            normalizeGuess(activeWordHelp),
        ].filter(Boolean));
        if (answers.has(guess)) {
            setWordHelpGuessFeedback('✓ Esatto! You had it.', 'success');
            recordWordHelpEvent(activeWordHelp, 'guess', true);
            revealWordHelp();
            return;
        }
        if (wordHelpGuesses >= 2) {
            setWordHelpGuessFeedback('Not yet — here is the meaning.', 'error');
            recordWordHelpEvent(activeWordHelp, 'guess', false);
            revealWordHelp();
            return;
        }
        setWordHelpGuessFeedback('Not it — one more try, or show the meaning.', 'error');
        recordWordHelpEvent(activeWordHelp, 'guess', false);
        elements.wordHelpGuess.select();
    }

    function closeWordHelp() {
        elements.wordHelpPanel.classList.add('hidden');
        elements.wordHelpGuessFeedback.classList.add('hidden');
        activeWordHelp = null;
        wordHelpGuesses = 0;
    }

    function stopWordHelpAudio() {
        wordHelpAudio?.pause();
        wordHelpAudio = null;
        if (wordHelpAudioUrl) URL.revokeObjectURL(wordHelpAudioUrl);
        wordHelpAudioUrl = '';
        wordHelpAudioSentence = '';
    }

    async function playWordHelpAudio() {
        const sentence = elements.wordHelpLemma.textContent.trim();
        if (!sentence) return;
        const voice = elements.pollyVoice.value || 'Beatrice';
        if (wordHelpAudio && wordHelpAudioSentence === sentence) {
            wordHelpAudio.currentTime = 0;
            await wordHelpAudio.play();
            return;
        }
        elements.wordHelpPlay.disabled = true;
        elements.wordHelpStatus.textContent = 'Preparing AWS Polly audio…';
        try {
            const response = await fetch('/api/learning-lab/polly', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sentence,
                    voice,
                    apiKeys: {
                        aws_access: localStorage.getItem('awsAccessKey') || '',
                        aws_secret: localStorage.getItem('awsSecretKey') || '',
                    },
                }),
            });
            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.error || 'AWS Polly could not create the audio.');
            }
            stopWordHelpAudio();
            wordHelpAudioUrl = URL.createObjectURL(await response.blob());
            wordHelpAudioSentence = sentence;
            wordHelpAudio = new Audio(wordHelpAudioUrl);
            wordHelpAudio.onended = () => {
                elements.wordHelpPlay.textContent = '🔊 Play again';
            };
            await wordHelpAudio.play();
            elements.wordHelpPlay.textContent = '🔊 Playing…';
            elements.wordHelpStatus.textContent = `AWS Polly · ${voice} · Italian`;
        } catch (error) {
            elements.wordHelpStatus.textContent = error.message;
            elements.wordHelpPlay.textContent = '🔊 Try again';
        } finally {
            elements.wordHelpPlay.disabled = false;
        }
    }

    function renderWordHelpDeep(deep) {
        if (!deep || (!deep.usage_en && !deep.usage_fa && !deep.form_en && !deep.note_en)) {
            elements.wordHelpDeep.classList.add('hidden');
            return;
        }
        elements.wordHelpUsage.textContent = deep.usage_en || '';
        elements.wordHelpUsageFa.textContent = deep.usage_fa || '';
        elements.wordHelpFormIt.textContent = deep.form_it || '';
        elements.wordHelpFormIt.classList.toggle('hidden', !deep.form_it);
        elements.wordHelpFormEn.textContent = deep.form_en || '';
        elements.wordHelpFormFa.textContent = deep.form_fa || '';
        elements.wordHelpNote.textContent = deep.note_en || '';
        elements.wordHelpNoteFa.textContent = deep.note_fa || '';
        elements.wordHelpDeep.classList.remove('hidden');
    }

    function ensureWordHelpDeep(word) {
        const help = wordHelpCache.get(word);
        if (help?.deep) {
            renderWordHelpDeep(help.deep);
            elements.wordHelpDeepStatus.classList.add('hidden');
            return;
        }
        if (help?.deepFailed || wordHelpDeepLoading.has(word)) return;
        wordHelpDeepLoading.add(word);
        elements.wordHelpDeepStatus.classList.remove('hidden');
        fetch('/api/learning-lab/word-help', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                word,
                deep: true,
                lemma: help?.lemma_it || '',
                context: session?.task?.prompt_en || '',
                startingIt: session?.task?.hint_it || '',
                geminiKey: apiKey(),
            }),
        }).then(async response => {
            const deep = await response.json();
            if (!response.ok) throw new Error(deep.error || 'Could not load the explanation.');
            return deep;
        }).then(deep => {
            const cached = wordHelpCache.get(word);
            if (cached) cached.deep = deep;
            if (activeWordHelp === word) {
                renderWordHelpDeep(deep);
                elements.wordHelpDeepStatus.classList.add('hidden');
            }
        }).catch(() => {
            const cached = wordHelpCache.get(word);
            if (cached) cached.deepFailed = true;
            if (activeWordHelp === word) {
                elements.wordHelpDeepStatus.classList.add('hidden');
            }
        }).finally(() => wordHelpDeepLoading.delete(word));
    }

    async function openWordHelp(word) {
        activeWordHelp = word;
        wordHelpGuesses = 0;
        elements.wordHelpWord.textContent = word;
        elements.wordHelpStatus.textContent = '';
        elements.wordHelpShape.textContent = wordShapeHint(word);
        elements.wordHelpShape.classList.remove('hidden');
        elements.wordHelpGuess.value = '';
        elements.wordHelpGuess.disabled = false;
        elements.wordHelpGuessBtn.disabled = false;
        elements.wordHelpGuessFeedback.classList.add('hidden');
        elements.wordHelpHintBlock.classList.add('hidden');
        elements.wordHelpMeaning.classList.add('hidden');
        elements.wordHelpShow.classList.add('hidden');
        elements.wordHelpPlay.classList.add('hidden');
        elements.wordHelpAdd.classList.add('hidden');
        elements.wordHelpDeep.classList.add('hidden');
        elements.wordHelpDeepStatus.classList.add('hidden');
        elements.wordHelpMnemonic.classList.add('hidden');
        elements.wordHelpMnemonicBlock.classList.add('hidden');
        elements.wordHelpPanel.classList.remove('hidden');
        elements.wordHelpGuess.focus();
        // The contextual why-this-word / why-this-form explanation loads in
        // parallel so it is ready by the time the hint or meaning shows.
        ensureWordHelpDeep(word);

        const cached = wordHelpCache.get(word);
        if (cached) {
            if (cached.revealed) {
                showWordHelpMeaning(cached);
                elements.wordHelpGuess.disabled = true;
                elements.wordHelpGuessBtn.disabled = true;
            } else {
                elements.wordHelpHint.textContent = cached.hint_en || '';
                elements.wordHelpHintFa.textContent = cached.hint_fa || '';
                elements.wordHelpHintBlock.classList.remove('hidden');
                elements.wordHelpShow.classList.remove('hidden');
            }
            return;
        }
        elements.wordHelpStatus.textContent = 'Getting a hint…';
        elements.wordHelpGuessBtn.disabled = true;
        try {
            const response = await fetch('/api/learning-lab/word-help', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    word,
                    context: session?.task?.prompt_en || '',
                    event: 'peek',
                    geminiKey: apiKey(),
                }),
            });
            const help = await response.json();
            if (!response.ok) throw new Error(help.error || 'Could not build a hint for this word.');
            if (help.found === false) {
                elements.wordHelpStatus.textContent =
                    'This looks like a name or number — you can say it as is.';
                return;
            }
            help.revealed = false;
            wordHelpCache.set(word, help);
            elements.wordHelpStatus.textContent = '';
            elements.wordHelpHint.textContent = help.hint_en || '';
            elements.wordHelpHintFa.textContent = help.hint_fa || '';
            elements.wordHelpHintBlock.classList.remove('hidden');
            elements.wordHelpShow.classList.remove('hidden');
            elements.wordHelpGuessBtn.disabled = false;
            elements.wordHelpGuess.focus();
        } catch (error) {
            elements.wordHelpStatus.textContent = error.message;
            elements.wordHelpGuessBtn.disabled = false;
        }
    }

    function handleFeedback(data) {
        // The verdict is the moment that matters — bring it to the learner
        // instead of leaving it below the fold, and clear the now-stale
        // live caption preview.
        hideLiveCaptions();
        renderFeedback(data);
        showPronunciation(data);
        if (data.evaluation_reliable === false) {
            elements.lapBtn.classList.add('hidden');
            elements.correctPanel.classList.add('hidden');
            elements.patternPanel.classList.add('hidden');
            elements.checkButton.classList.add('hidden');
            elements.transcriptWrong.classList.add('hidden');
            resetCapture({ preserveTranscript: true });
            elements.feedback.classList.remove('hidden');
            elements.recordButton.disabled = false;
            elements.recordHint.textContent = 'Listen to your recording, then record again. This attempt did not affect your progress.';
            elements.feedback.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }
        showCorrectSentence(data);
        const firstPatternExposure = showNewPattern(data);
        elements.checkButton.classList.add('hidden');
        elements.transcriptWrong.classList.add('hidden');
        elements.recordButton.disabled = true;

        if (!data.retry_needed) {
            completedProductions += 1;
            lastSuccessSeconds = lastDuration;
            if (dailyGoal) {
                dailyCorrect = Math.min(dailyGoal, dailyCorrect + 1);
                updateDailyDisplay();
            }
            elements.lapBtn.classList.remove('hidden');
            elements.lapBtn.textContent =
                `⚡ Fluency lap — say it in under ${(Math.max(1.5, lastSuccessSeconds * 0.75)).toFixed(1)}s`;
            pendingTransferTask = !transferMode && data.transfer_task?.available
                ? data.transfer_task
                : null;
            if (firstPatternExposure) {
                patternShadowMode = true;
                shadowMode = true;
                shadowListened = false;
                elements.nextRound.classList.add('hidden');
                elements.recordButton.disabled = true;
                elements.recordButtonText.textContent = 'Listen with AWS Polly first';
                elements.recordHint.textContent = 'Play the correct sentence above, then repeat it once aloud.';
                return;
            }
            setNextAction(pendingTransferTask ? 'transfer' : 'round');
            elements.recordHint.textContent = pendingTransferTask
                ? 'Good. Now transfer the same language to a different everyday situation.'
                : 'Translation complete. Continue when you are ready.';
            if (pendingTransferTask && !transferMode) {
                elements.phaseLabel.textContent = '✓ Round complete — transfer it next';
            }
            // The prompt did its job; collapse it so the verdict and the
            // next action own the screen.
            collapsePrompt();
            elements.feedback.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }

        retries += 1;
        if (attempt < settings.max_feedback_attempts) {
            attempt += 1;
            elements.attemptLabel.textContent = `Attempt ${attempt}`;
            elements.lapBtn.classList.add('hidden');
            elements.feedback.insertAdjacentHTML('beforeend', `
                <div class="speaking-retry-hint">
                    <strong>One focused retry</strong>
                    <p>${escapeHtml(data.retry_instruction_en)}</p>
                    <p lang="fa" dir="rtl">${escapeHtml(data.retry_instruction_fa)}</p>
                </div>`);
            resetCapture({ preserveTranscript: true });
            elements.recordButtonText.textContent =
                `Prepare — attempt ${attempt} of ${settings.max_feedback_attempts}`;
            elements.feedback.classList.remove('hidden');
            elements.recordButton.disabled = false;
            elements.recordHint.textContent = 'Say the complete Italian translation again using the hint above.';
            elements.feedback.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }

        const answer = String(data.corrected_response_it || '').trim();
        if (!answer) {
            setNextAction('round');
            return;
        }
        pendingTransferTask = null;
        nextAction = 'round';
        shadowMode = true;
        shadowListened = false;
        resetCapture({ preserveTranscript: true });
        elements.feedback.classList.remove('hidden');
        elements.modelAnswer.textContent = answer;
        elements.modelPanel.classList.remove('hidden');
        elements.recordButton.disabled = true;
        elements.feedback.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function revealHint() {
        const hint = String(session?.task?.hint_it || '').trim();
        if (!hint || !elements.hintPanel.classList.contains('hidden')) return;
        elements.hintText.textContent = hint;
        elements.hintPanel.classList.remove('hidden');
        elements.hintButton.classList.add('hidden');
        hintsUsed += 1;
    }

    async function recheckAudio() {
        if (!lastAudioBlob?.size || !session) return;
        elements.transcriptWrong.disabled = true;
        elements.checkButton.classList.add('hidden');
        elements.recordHint.textContent = 'Gemini is listening to the audio directly…';
        elements.recordButton.disabled = true;
        try {
            const data = await evaluateAudio(lastAudioBlob);
            transcript = String(data.transcript_it || '').trim();
            elements.transcriptText.textContent = transcript;
            hideStatus();
            handleFeedback(data);
        } catch (error) {
            setRecordHint(`❌ ${error.message} — press Record again to try.`, 'error');
            elements.recordButton.disabled = false;
            elements.checkButton.classList.remove('hidden');
            elements.checkButton.disabled = false;
        } finally {
            elements.transcriptWrong.disabled = false;
        }
    }

    async function checkSpeech() {
        if (!transcript || !session) return;
        elements.checkButton.disabled = true;
        elements.checkButton.textContent = 'Checking your spoken Italian…';
        try {
            const response = await fetch('/api/learning-lab/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    targets: session.targets,
                    task: session.task,
                    response: transcript,
                    geminiKey: apiKey(),
                    mode: 'voice',
                    durationSeconds: lastDuration,
                    attempt,
                    round: roundNumber,
                    phase: transferMode ? 'transfer' : 'translation',
                    fluency: currentFluency(transcript.split(/\s+/u).filter(Boolean).length),
                }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not evaluate this response.');
            handleFeedback(data);
        } catch (error) {
            setStatus(error.message, 'error');
            elements.checkButton.disabled = false;
        } finally {
            elements.checkButton.textContent = 'Check spoken Italian';
        }
    }

    function playModelAnswer() {
        const answer = elements.modelAnswer.textContent.trim();
        if (!answer) return;
        window.speechSynthesis?.cancel();
        if (!window.speechSynthesis) {
            shadowListened = true;
            elements.recordButton.disabled = false;
            elements.shadowHint.textContent = 'Audio playback is unavailable. Read the model once, then repeat it aloud.';
            return;
        }
        const utterance = new SpeechSynthesisUtterance(answer);
        utterance.lang = 'it-IT';
        utterance.rate = 0.9;
        elements.playModel.disabled = true;
        elements.shadowHint.textContent = 'Listen carefully…';
        utterance.onend = () => {
            shadowListened = true;
            elements.playModel.disabled = false;
            elements.recordButton.disabled = false;
            elements.shadowHint.textContent = 'Now repeat the complete model answer aloud.';
            elements.recordHint.textContent = 'Repeat what you heard—live captions follow along as you speak.';
        };
        utterance.onerror = () => {
            shadowListened = true;
            elements.playModel.disabled = false;
            elements.recordButton.disabled = false;
            elements.shadowHint.textContent = 'Playback failed. Read the model once, then repeat it aloud.';
        };
        window.speechSynthesis.speak(utterance);
    }

    async function loadRound({ excludeWords = [], keepVisible = false } = {}) {
        setStatus('Selecting studied words for this round…');
        elements.intro.classList.add('hidden');
        elements.summary.classList.add('hidden');
        if (!keepVisible) elements.sprint.classList.add('hidden');
        elements.changeSentence.disabled = true;
        const response = await fetch('/api/learning-lab/session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sourceModel: localStorage.getItem('modelName') || 'Italian Vocab',
                ladderLevel: roundNumber,
                excludeWords,
            }),
        });
        const nextSession = await response.json();
        if (!response.ok) throw new Error(nextSession.error || 'Could not build a speaking round.');
        if (!nextSession.targets?.length) {
            elements.changeSentence.disabled = false;
            setStatus(
                excludeWords.length
                    ? 'There are no more different studied sentences in this sprint. You can use the current one or start a new sprint.'
                    : 'No studied production cards are available yet. Review some production-recall cards in Anki first.',
                'warning',
            );
            return;
        }
        session = nextSession;
        settings = { ...defaults, ...(session.sprint || {}) };
        seenWords.add(String(session.targets[0]?.word || '').toLocaleLowerCase('it'));

        attempt = 1;
        transferMode = false;
        pendingTransferTask = null;
        nextAction = 'round';
        shadowMode = false;
        shadowListened = false;
        patternShadowMode = false;
        elements.roundLabel.textContent = `Round ${roundNumber} of ${settings.rounds}`;
        elements.attemptLabel.textContent = 'Attempt 1';
        elements.phaseLabel.textContent = session.task.review_status?.scheduled
            ? 'Spaced spoken review'
            : 'Translate into Italian';
        elements.dailyProgress.textContent = `Today ${session.daily?.correct_sentences || 0}/${session.daily?.goal || 5}`;
        dailyCorrect = session.daily?.correct_sentences || 0;
        dailyGoal = session.daily?.goal || 0;
        updateDailyDisplay();
        elements.progressFill.style.width = `${((roundNumber - 1) / settings.rounds) * 100}%`;
        elements.roundTitle.textContent = session.task.title;
        renderClickablePrompt(session.task.prompt_en);
        elements.promptFa.textContent = session.task.prompt_fa;
        elements.hintText.textContent = session.task.hint_it || '';
        elements.hintPanel.classList.toggle('hidden', !session.task.hint_visible || !session.task.hint_it);
        elements.hintButton.classList.toggle('hidden', Boolean(session.task.hint_visible) || !session.task.hint_it);
        elements.changeSentence.classList.remove('hidden');
        closeWordHelp();
        resetLaps();
        expandPrompt();
        const frequentErrors = session.coach?.frequent_errors || [];
        const coachParts = [];
        if (session.coach?.due_review) coachParts.push('Due spoken review: retrieve it before using a hint.');
        if (frequentErrors.length) {
            coachParts.push(`Personal focus: ${frequentErrors.map(item => String(item.category || '').replaceAll('_', ' ')).join(' · ')}.`);
        }
        elements.coachStrip.textContent = coachParts.join(' ');
        elements.coachStrip.classList.toggle('hidden', !coachParts.length);
        renderTargets();
        elements.feedback.classList.add('hidden');
        elements.correctPanel.classList.add('hidden');
        elements.patternPanel.classList.add('hidden');
        elements.pronunciationPanel.classList.add('hidden');
        stopCorrectAudio();
        elements.modelPanel.classList.add('hidden');
        elements.nextRound.classList.add('hidden');
        resetCapture();
        elements.changeSentence.disabled = false;
        hideStatus();
        elements.sprint.classList.remove('hidden');
    }

    async function changeCurrentSentence() {
        if (recording || preparing) {
            setStatus('Stop the current recording before changing the sentence.', 'warning');
            return;
        }
        try {
            await loadRound({
                excludeWords: [...seenWords],
                keepVisible: true,
            });
        } catch (error) {
            elements.changeSentence.disabled = false;
            setStatus(error.message, 'error');
        }
    }

    function finishSprint() {
        elements.sprint.classList.add('hidden');
        elements.summaryRounds.textContent = String(settings.rounds);
        elements.summarySeconds.textContent = `${Math.round(totalSeconds)}s`;
        elements.summaryRetries.textContent = String(retries);
        elements.summaryHints.textContent = String(hintsUsed);
        elements.summaryCoach.textContent = completedProductions
            ? `${completedProductions} successful spoken productions were scheduled for future recall. Fluency numbers are descriptive—not grades.`
            : 'Your attempts were saved for targeted repair. Return later for the scheduled spoken review.';
        elements.summary.classList.remove('hidden');
    }

    async function nextRound() {
        if (roundNumber >= settings.rounds) {
            finishSprint();
            return;
        }
        roundNumber += 1;
        await loadRound();
    }

    async function advance() {
        if (nextAction === 'transfer') {
            beginTransfer();
            return;
        }
        await nextRound();
    }

    async function startSprint() {
        if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
            elements.intro.classList.add('hidden');
            setStatus('Voice-only mode requires microphone recording. Open this page in Chrome or Safari; typing fallback is intentionally disabled.', 'error');
            return;
        }
        roundNumber = 1;
        totalSeconds = 0;
        retries = 0;
        hintsUsed = 0;
        completedProductions = 0;
        seenWords = new Set();
        wordHelpCache = new Map();
        closeWordHelp();
        resetLaps();
        lastSuccessSeconds = 0;
        try {
            await loadRound();
        } catch (error) {
            setStatus(error.message, 'error');
        }
    }

    elements.startSprint.addEventListener('click', startSprint);
    elements.recordButton.addEventListener('click', prepareAndRecord);
    elements.checkButton.addEventListener('click', checkSpeech);
    elements.hintButton.addEventListener('click', revealHint);
    elements.changeSentence.addEventListener('click', changeCurrentSentence);
    elements.transcriptWrong.addEventListener('click', recheckAudio);
    elements.playModel.addEventListener('click', playModelAnswer);

    // --- Word help events ---
    elements.promptEn.addEventListener('click', event => {
        const wordNode = event.target.closest('.speaking-word');
        if (wordNode?.dataset.word) openWordHelp(wordNode.dataset.word);
    });
    elements.promptEn.addEventListener('keydown', event => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        const wordNode = event.target.closest('.speaking-word');
        if (wordNode?.dataset.word) {
            event.preventDefault();
            openWordHelp(wordNode.dataset.word);
        }
    });
    elements.wordHelpClose.addEventListener('click', closeWordHelp);
    elements.wordHelpGuessBtn.addEventListener('click', checkWordGuess);
    elements.wordHelpGuess.addEventListener('keydown', event => {
        if (event.key === 'Enter') {
            event.preventDefault();
            checkWordGuess();
        }
    });
    elements.wordHelpShow.addEventListener('click', () => revealWordHelp());
    elements.wordHelpPlay.addEventListener('click', () => playWordHelpAudio().catch(() => {}));
    elements.wordHelpMnemonic.addEventListener('click', () => loadWordHelpMnemonic());
    elements.lapBtn.addEventListener('click', startLap);
    elements.wordHelpAdd.addEventListener('click', () => {
        if (activeWordHelp) recordWordHelpEvent(activeWordHelp, 'add_requested');
    });

    elements.playCorrect.addEventListener('click', () => playCorrectSentence().catch(error => {
        elements.correctAudioStatus.textContent = error.message;
    }));
    elements.nextRound.addEventListener('click', () => advance().catch(error => setStatus(error.message, 'error')));
    elements.newSprint.addEventListener('click', startSprint);
    window.addEventListener('beforeunload', () => {
        stopTimers();
        recognition?.abort();
        stopCaptionRecognition();
        stopWordHelpAudio();
        stopCorrectAudio();
        stopOwnRecording();
        window.speechSynthesis?.cancel();
    });
})();
