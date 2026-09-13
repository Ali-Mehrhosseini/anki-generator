/**
 * grammar.js — Italian Grammar Deck UI
 *
 * Handles the topic browser, generation requests, card preview,
 * and saving grammar cards to Anki.
 */

(function () {
    'use strict';

    // --- State ---
    let currentData = null;
    let currentAudios = null;
    let generating = false;
    let topicsCache = null;
    let currentMode = 'standard';
    let adaptiveSessionData = null;
    let adaptiveItemIndex = 0;
    let currentView = 'today';
    let conversationContext = null;
    let speechRecognition = null;

    // --- DOM ---
    const topicInput = document.getElementById('topicInput');
    const grammarForm = document.getElementById('grammarForm');
    const generateBtn = document.getElementById('generateBtn');
    const progressContainer = document.getElementById('progressContainer');
    const activityLog = document.getElementById('activityLog');
    const statusMessage = document.getElementById('statusMessage');
    const topicGrid = document.getElementById('topicGrid');
    const topicSearch = document.getElementById('topicSearch');
    const previewSection = document.getElementById('previewSection');
    const frontHtml = document.getElementById('frontHtml');
    const backHtml = document.getElementById('backHtml');
    const saveToAnkiBtn = document.getElementById('saveToAnkiBtn');
    const saveStatus = document.getElementById('saveStatus');
    const progressSummary = document.getElementById('progressSummary');
    const ankiStatus = document.getElementById('ankiStatus');
    const modeSwitcher = document.getElementById('modeSwitcher');
    const adaptiveStartBtn = document.getElementById('adaptiveStartBtn');
    const adaptiveStatus = document.getElementById('adaptiveStatus');
    const adaptiveSession = document.getElementById('adaptiveSession');
    const adaptiveProgress = document.getElementById('adaptiveProgress');
    const adaptiveTopic = document.getElementById('adaptiveTopic');
    const adaptiveFront = document.getElementById('adaptiveFront');
    const adaptiveInputs = document.getElementById('adaptiveInputs');
    const adaptiveSubmitBtn = document.getElementById('adaptiveSubmitBtn');
    const adaptiveFeedback = document.getElementById('adaptiveFeedback');
    const adaptiveNextBtn = document.getElementById('adaptiveNextBtn');
    const adaptiveTransfer = document.getElementById('adaptiveTransfer');
    const transferPromptEn = document.getElementById('transferPromptEn');
    const transferPromptFa = document.getElementById('transferPromptFa');
    const transferResponse = document.getElementById('transferResponse');
    const transferSubmitBtn = document.getElementById('transferSubmitBtn');
    const transferFeedback = document.getElementById('transferFeedback');
    const adaptiveFinishBtn = document.getElementById('adaptiveFinishBtn');
    const workspaceTabs = document.querySelectorAll('.grammar-workspace-tab');
    const workspacePanels = document.querySelectorAll('[data-view-panel]');
    const todayCardCount = document.getElementById('todayCardCount');
    const todayMinutes = document.getElementById('todayMinutes');
    const todayDelayed = document.getElementById('todayDelayed');
    const todayCoachLine = document.getElementById('todayCoachLine');
    const schedulerNote = document.getElementById('schedulerNote');
    const masteryStageGrid = document.getElementById('masteryStageGrid');
    const weakTopicList = document.getElementById('weakTopicList');
    const errorNotebook = document.getElementById('errorNotebook');
    const crossTrainingErrors = document.getElementById('crossTrainingErrors');
    const sessionSteps = document.getElementById('sessionSteps');
    const adaptiveConversation = document.getElementById('adaptiveConversation');
    const conversationScenario = document.getElementById('conversationScenario');
    const conversationScenarioFa = document.getElementById('conversationScenarioFa');
    const scenarioChips = document.getElementById('scenarioChips');
    const conversationLog = document.getElementById('conversationLog');
    const conversationResponse = document.getElementById('conversationResponse');
    const conversationSubmitBtn = document.getElementById('conversationSubmitBtn');
    const conversationFeedback = document.getElementById('conversationFeedback');
    const startConversationBtn = document.getElementById('startConversationBtn');
    const adaptiveSpeaking = document.getElementById('adaptiveSpeaking');
    const startSpeakingBtn = document.getElementById('startSpeakingBtn');
    const speakingRecordBtn = document.getElementById('speakingRecordBtn');
    const speakingTranscript = document.getElementById('speakingTranscript');
    const speakingSubmitBtn = document.getElementById('speakingSubmitBtn');
    const speakingFeedback = document.getElementById('speakingFeedback');
    const adaptiveSummary = document.getElementById('adaptiveSummary');
    const sessionSummaryContent = document.getElementById('sessionSummaryContent');
    const summaryDoneBtn = document.getElementById('summaryDoneBtn');
    // Dictogloss (listen & reconstruct)
    const dictoglossForm = document.getElementById('dictoglossForm');
    const dictoglossTopic = document.getElementById('dictoglossTopic');
    const dictoglossStartBtn = document.getElementById('dictoglossStartBtn');
    const dictoglossStatus = document.getElementById('dictoglossStatus');
    const dictoglossSession = document.getElementById('dictoglossSession');
    const dictoglossLevel = document.getElementById('dictoglossLevel');
    const dictoglossFocus = document.getElementById('dictoglossFocus');
    const dictoglossAudio = document.getElementById('dictoglossAudio');
    const dictoglossResponse = document.getElementById('dictoglossResponse');
    const dictoglossCheckBtn = document.getElementById('dictoglossCheckBtn');
    const dictoglossResult = document.getElementById('dictoglossResult');
    const dictoglossRetryBtn = document.getElementById('dictoglossRetryBtn');
    let dictoglossSessionId = null;
    // Card graduation (recognition → production when mature)
    const graduationStats = document.getElementById('graduationStats');
    const graduationDetail = document.getElementById('graduationDetail');
    const graduationRunBtn = document.getElementById('graduationRunBtn');
    let graduationPlanData = null;

    // --- API Keys (from localStorage, same as main app) ---
    function getApiKeys() {
        const direct = {
            gemini: localStorage.getItem('geminiKey') || '',
            aws_access: localStorage.getItem('awsAccessKey') || '',
            aws_secret: localStorage.getItem('awsSecretKey') || '',
        };
        if (direct.gemini || direct.aws_access || direct.aws_secret) return direct;
        try {
            return JSON.parse(localStorage.getItem('ankiApiKeys') || '{}');
        } catch { return {}; }
    }

    function activateView(view) {
        currentView = view;
        workspaceTabs.forEach(tab => tab.classList.toggle('active', tab.dataset.view === view));
        workspacePanels.forEach(panel => panel.classList.toggle('hidden', panel.dataset.viewPanel !== view));
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function renderOverview(data) {
        todayCardCount.textContent = String(data.recommended_cards || 0);
        todayMinutes.textContent = String(data.estimated_minutes || 0);
        todayDelayed.textContent = String((data.delayed_due || []).length);
        schedulerNote.textContent = data.scheduler_note || 'Anki/FSRS schedules long-term recall';
        todayCoachLine.textContent = data.available_cards
            ? `${data.recommended_cards} mixed prompts, then free use, conversation, and speaking. Your weakest rules appear first.`
            : 'Create and save grammar cards to build your first adaptive session.';

        const stageMeta = {
            recognition: ['Recognition', 'Recall the form when Anki schedules it.'],
            input: ['Interpretation', 'Process the form for meaning before producing.'],
            controlled: ['Controlled', 'Produce the form in a focused prompt.'],
            free: ['Free use', 'Use it in a new written situation.'],
            speaking: ['Speaking', 'Use it under conversational time pressure.'],
        };
        masteryStageGrid.innerHTML = Object.entries(stageMeta).map(([key, meta]) => {
            const value = Math.max(0, Math.min(100, Number((data.stage_averages || {})[key] || 0)));
            return `<div class="grammar-stage-card"><div class="grammar-stage-card-head"><span>${meta[0]}</span><strong>${value}%</strong></div><small>${meta[1]}</small><div class="grammar-stage-meter"><span style="width:${value}%"></span></div></div>`;
        }).join('');

        const weak = data.weakest_topics || [];
        weakTopicList.innerHTML = weak.length ? weak.map(item => `<div class="grammar-insight-item"><div><strong>${escapeHtml(item.topic || item.topic_key.replaceAll('_', ' '))}</strong><small>${escapeHtml(String(item.status || 'new').replace('-', ' '))}</small></div><span class="grammar-insight-score">${Number(item.score || 0)}%</span></div>`).join('')
            : '<div class="grammar-empty-insight">Your weakest topics will appear after cards are saved.</div>';

        const errors = data.errors || [];
        errorNotebook.innerHTML = errors.length ? errors.map(item => `<div class="grammar-insight-item"><div><strong>${escapeHtml(String(item.error_type || 'grammar').replaceAll('_', ' '))}</strong><small>${escapeHtml(item.topic || '')} · ${escapeHtml(item.stage || '')}</small></div><span class="grammar-insight-score">×${Number(item.count || 0)}</span></div>`).join('')
            : '<div class="grammar-empty-insight">No recurring error pattern yet. That is a good place to start.</div>';
    }

    async function loadPracticeOverview() {
        try {
            const response = await fetch('/api/grammar/practice/overview');
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load today’s practice.');
            renderOverview(data);
        } catch (error) {
            todayCoachLine.textContent = error.message;
            masteryStageGrid.innerHTML = '<div class="grammar-empty-insight">Connect Anki to calculate mastery.</div>';
        }
    }

    function setSessionStep(step) {
        const order = ['controlled', 'free', 'conversation', 'speaking'];
        const activeIndex = order.indexOf(step);
        sessionSteps.querySelectorAll('[data-step]').forEach((node, index) => {
            node.classList.toggle('active', index === activeIndex);
            node.classList.toggle('complete', index < activeIndex);
        });
    }

    // --- Anki Status ---
    async function checkAnkiStatus() {
        try {
            const resp = await fetch('http://localhost:8765', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'version', version: 6 }),
            });
            const data = await resp.json();
            if (data.result) {
                ankiStatus.classList.add('connected');
                ankiStatus.classList.remove('disconnected');
                ankiStatus.title = 'Anki is connected';
            }
        } catch {
            ankiStatus.classList.add('disconnected');
            ankiStatus.classList.remove('connected');
            ankiStatus.title = 'Anki is not connected';
        }
    }

    // --- Mode Switcher ---
    if (modeSwitcher) {
        modeSwitcher.querySelectorAll('.grammar-mode-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                modeSwitcher.querySelectorAll('.grammar-mode-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                currentMode = tab.dataset.mode || 'standard';

                // Update input placeholder
                if (currentMode === 'contrast') {
                    topicInput.placeholder = "Enter a contrast pair, e.g. 'lo vs gli' or 'essere vs avere'...";
                } else if (currentMode === 'mistake') {
                    topicInput.placeholder = "Enter an error topic, e.g. 'auxiliary mistakes' or 'gender traps'...";
                } else if (currentMode === 'input') {
                    topicInput.placeholder = "Enter a topic to interpret, e.g. 'pronomi indiretti' or 'passato prossimo'...";
                } else {
                    topicInput.placeholder = "Enter a grammar topic, e.g. 'pronomi indiretti' or 'preposizioni'...";
                }

                loadTopics();
            });
        });
    }

    // --- Load Topics ---
    async function loadTopics() {
        try {
            const resp = await fetch(`/api/grammar/topics?mode=${encodeURIComponent(currentMode)}`);
            topicsCache = await resp.json();
            const levelFilter = document.querySelector('.grammar-level-btn.active')?.dataset.level || 'all';
            const filter = topicSearch ? topicSearch.value.trim() : '';
            renderTopicGrid(topicsCache, filter, levelFilter);
        } catch (error) {
            topicGrid.innerHTML = '<p style="opacity:0.6;text-align:center;">Could not load topics. Make sure the server is running.</p>';
        }
    }

    // --- Render Topic Grid ---
    function renderTopicGrid(topics, filter = '', levelFilter = 'all') {
        const searchLower = filter.toLowerCase();
        let html = '';
        let total = 0;
        let completed = 0;

        const levelOrder = ['A1', 'A2', 'B1'];
        const levelMeta = {
            A1: { icon: '🟢', label: 'Beginner', color: '#4caf50' },
            A2: { icon: '🔵', label: 'Elementary', color: '#2196f3' },
            B1: { icon: '🟣', label: 'Intermediate', color: '#9c27b0' },
        };

        for (const level of levelOrder) {
            const levelTopics = topics[level] || [];
            if (levelFilter !== 'all' && levelFilter !== level) continue;

            const filtered = levelTopics.filter(t => {
                if (!searchLower) return true;
                return (
                    (t.title_it || '').toLowerCase().includes(searchLower) ||
                    (t.title_en || '').toLowerCase().includes(searchLower) ||
                    (t.prompt_hint || '').toLowerCase().includes(searchLower)
                );
            });

            if (filtered.length === 0) continue;

            const meta = levelMeta[level];
            html += `<div class="grammar-level-section">`;
            html += `<div class="grammar-level-header" style="--level-color: ${meta.color}">`;
            html += `<span class="grammar-level-icon">${meta.icon}</span>`;
            html += `<span class="grammar-level-name">${level}</span>`;
            html += `<span class="grammar-level-label">${meta.label}</span>`;
            html += `<span class="grammar-level-count">${filtered.length} topics</span>`;
            html += `</div>`;
            html += `<div class="grammar-topic-cards">`;

            for (const topic of filtered) {
                total++;
                const mastery = topic.mastery || { score: 0, status: 'new' };
                const isDone = mastery.status === 'mastered';
                if (isDone) completed++;

                const completedClass = isDone ? ' grammar-topic-completed' : '';
                const statusIcon = isDone ? '✅' : (topic.has_cards ? '📚' : '');
                const checkmark = statusIcon ? `<span class="grammar-check">${statusIcon}</span>` : '';
                const recommendedBadge = topic.recommended
                    ? `<span class="grammar-recommend-badge" title="${escapeAttr(topic.recommendation_reason || 'Recommended from your recent errors')}">🎯 Study next</span>`
                    : '';

                html += `<div class="grammar-topic-card${completedClass}" data-topic="${escapeAttr(topic.title_it)}" data-level="${level}">`;
                html += `<div class="grammar-topic-card-header">`;
                html += `<span class="grammar-topic-level-badge" style="--level-color: ${meta.color}">${level}</span>`;
                html += checkmark;
                html += `</div>`;
                html += recommendedBadge;
                html += `<div class="grammar-topic-title">${escapeHtml(topic.title_it)}</div>`;
                html += `<div class="grammar-topic-subtitle">${escapeHtml(topic.title_en)}</div>`;
                html += `<div class="grammar-topic-hint">${escapeHtml(topic.prompt_hint || '')}</div>`;
                html += `<div class="grammar-mastery-row"><span>${escapeHtml(String(mastery.status || 'new').replace('-', ' '))}</span><strong>${Number(mastery.score || 0)}%</strong></div>`;
                html += `<div class="grammar-mastery-track"><span style="width:${Math.max(0, Math.min(100, Number(mastery.score || 0)))}%"></span></div>`;
                const stages = mastery.stages || {};
                html += `<div class="grammar-topic-stage-dots" title="Recognition · Interpretation · Controlled · Free use · Speaking">`;
                ['recognition', 'input', 'controlled', 'free', 'speaking'].forEach(stage => {
                    const stageValue = Math.max(0, Math.min(100, Number(stages[stage] || 0)));
                    html += `<span class="grammar-topic-stage-dot"><span style="width:${stageValue}%"></span></span>`;
                });
                html += `</div>`;
                html += `<button class="grammar-topic-gen-btn" title="Generate this card">Generate →</button>`;
                html += `</div>`;
            }

            html += `</div></div>`;
        }

        topicGrid.innerHTML = html || '<p style="opacity:0.6;text-align:center;padding:20px;">No topics match your search.</p>';

        // Update progress summary
        progressSummary.textContent = `${completed} / ${total} mastered`;

        // Attach click handlers
        topicGrid.querySelectorAll('.grammar-topic-gen-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const card = btn.closest('.grammar-topic-card');
                const topic = card.dataset.topic;
                topicInput.value = topic;
                activateView('create');
                generateGrammarCard(topic, currentMode);
            });
        });

        topicGrid.querySelectorAll('.grammar-topic-card').forEach(card => {
            card.addEventListener('click', () => {
                topicInput.value = card.dataset.topic;
                activateView('create');
                topicInput.focus();
            });
        });

        // Animate cards in
        if (typeof gsap !== 'undefined') {
            gsap.fromTo('.grammar-topic-card', { opacity: 0, y: 20 }, {
                opacity: 1, y: 0, duration: 0.4, stagger: 0.03, ease: 'power2.out'
            });
        }
    }

    // --- Generate Grammar Card ---
    async function generateGrammarCard(topic, mode = currentMode) {
        if (generating) return;
        generating = true;

        currentData = null;
        currentAudios = null;
        previewSection.classList.add('hidden');
        progressContainer.classList.remove('hidden');
        activityLog.innerHTML = '';
        statusMessage.classList.add('hidden');
        generateBtn.disabled = true;
        generateBtn.querySelector('.btn-text').textContent = 'Generating…';

        addLogEntry(`🔍 Sending ${mode} grammar request to AI...`);

        const apiKeys = getApiKeys();

        try {
            const resp = await fetch('/api/grammar/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ topic, apiKeys, mode }),
            });

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const payload = JSON.parse(line.slice(6));

                        if (payload.status) {
                            addLogEntry(payload.status);
                        }

                        if (payload.error) {
                            addLogEntry('❌ ' + payload.error);
                            showStatus(payload.error, 'error');
                        }

                        if (payload.result && payload.result.success) {
                            currentData = payload.result.data;
                            currentAudios = payload.result.audios || {};
                            addLogEntry('✅ Flashcard deck ready!');
                            showPreview(currentData);
                        }
                    } catch { /* skip malformed lines */ }
                }
            }
        } catch (error) {
            addLogEntry('❌ ' + error.message);
            showStatus('Network error: ' + error.message, 'error');
        }

        generating = false;
        generateBtn.disabled = false;
        generateBtn.querySelector('.btn-text').textContent = 'Generate Card';
    }

    // --- Preview State & Handlers ---
    let currentCardIndex = 0;

    function renderActiveCard() {
        if (!currentData || !currentData.cards || !currentData.cards.length) return;
        const cards = currentData.cards;
        const card = cards[currentCardIndex];

        // Update front & back HTML
        frontHtml.innerHTML = card.front_html || '<p>No front HTML</p>';
        backHtml.innerHTML = card.back_html || '<p>No back HTML</p>';

        // Update count badge
        const badge = document.getElementById('cardCountBadge');
        if (badge) badge.textContent = `${currentCardIndex + 1} / ${cards.length}`;

        // Update pills
        document.querySelectorAll('.grammar-card-pill').forEach((pill, idx) => {
            pill.classList.toggle('active', idx === currentCardIndex);
        });

        // Update prev/next disabled state
        const prevBtn = document.getElementById('prevCardBtn');
        const nextBtn = document.getElementById('nextCardBtn');
        if (prevBtn) prevBtn.disabled = currentCardIndex === 0;
        if (nextBtn) nextBtn.disabled = currentCardIndex === cards.length - 1;
    }

    function showPreview(data) {
        const cards = data.cards || [];
        if (!cards.length) return;

        currentCardIndex = 0;
        const mode = data.mode || currentMode;

        const titleEl = document.getElementById('previewTopicTitle');
        const subEl = document.getElementById('previewTopicSubtitle');
        const icons = { contrast: '⚖️', mistake: '🔍', input: '🧭', standard: '📐' };
        const icon = icons[mode] || '📐';
        if (titleEl) titleEl.textContent = `${icon} ${data.topic || 'Grammar'} (${data.topic_en || ''})`;
        if (subEl) subEl.textContent = data.overview_en || '';

        // Render card pills based on mode
        const pillsContainer = document.getElementById('cardPillsContainer');
        if (pillsContainer) {
            pillsContainer.innerHTML = cards.map((c, i) => {
                let label = '';
                if (mode === 'contrast') {
                    label = c.pair_label || (c.sentence_a_target && c.sentence_b_target ? `${c.sentence_a_target} vs ${c.sentence_b_target}` : `Pair ${i + 1}`);
                } else if (mode === 'mistake') {
                    label = (c.error_element && c.corrected_element) ? `❌ ${c.error_element} → ✅ ${c.corrected_element}` : `Mistake #${i + 1}`;
                } else if (mode === 'input') {
                    label = c.target_form || `Interpretation ${i + 1}`;
                } else {
                    label = c.target_form || `Card ${i + 1}`;
                }

                return `
                    <button type="button" class="grammar-card-pill ${i === 0 ? 'active' : ''}" data-idx="${i}">
                        <span class="pill-num">${i + 1}</span>
                        <span class="pill-target">${escapeHtml(label)}</span>
                    </button>
                `;
            }).join('');

            pillsContainer.querySelectorAll('.grammar-card-pill').forEach(pill => {
                pill.addEventListener('click', () => {
                    currentCardIndex = parseInt(pill.dataset.idx, 10);
                    renderActiveCard();
                });
            });
        }

        renderActiveCard();
        previewSection.classList.remove('hidden');
        saveToAnkiBtn.disabled = false;
        saveStatus.textContent = '';

        if (typeof gsap !== 'undefined') {
            gsap.fromTo(previewSection, { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power2.out' });
        }

    }

    // Prev / Next button listeners
    const prevBtn = document.getElementById('prevCardBtn');
    const nextBtn = document.getElementById('nextCardBtn');
    if (prevBtn) {
        prevBtn.addEventListener('click', () => {
            if (currentCardIndex > 0) {
                currentCardIndex--;
                renderActiveCard();
            }
        });
    }
    if (nextBtn) {
        nextBtn.addEventListener('click', () => {
            if (currentData && currentData.cards && currentCardIndex < currentData.cards.length - 1) {
                currentCardIndex++;
                renderActiveCard();
            }
        });
    }


    // --- Save to Anki ---
    async function saveToAnki() {
        if (!currentData) return;

        saveToAnkiBtn.disabled = true;
        saveStatus.textContent = 'Saving…';
        saveStatus.className = '';

        try {
            const resp = await fetch('/api/grammar/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ data: currentData, audios: currentAudios }),
            });
            const result = await resp.json();

            if (result.success) {
                const countMsg = result.count ? `Saved ${result.count} cards for "${result.topic}" to Anki!` : (result.message || `Saved "${result.topic}" to Anki!`);
                saveStatus.textContent = `✅ ${countMsg}`;
                saveStatus.className = 'grammar-save-success';
                // Refresh topics to update completion status
                loadTopics();
            } else {
                saveStatus.textContent = `❌ ${result.error}`;
                saveStatus.className = 'grammar-save-error';
                saveToAnkiBtn.disabled = false;
            }
        } catch (error) {
            saveStatus.textContent = `❌ ${error.message}`;
            saveStatus.className = 'grammar-save-error';
            saveToAnkiBtn.disabled = false;
        }
    }

    // --- Helpers ---
    function addLogEntry(text) {
        const entry = document.createElement('div');
        entry.className = 'activity-entry';
        entry.textContent = text;
        activityLog.appendChild(entry);
        activityLog.scrollTop = activityLog.scrollHeight;
    }

    function showStatus(message, type) {
        statusMessage.textContent = message;
        statusMessage.className = type === 'error' ? 'status-error' : 'status-success';
        statusMessage.classList.remove('hidden');
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function escapeAttr(str) {
        return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function adaptiveMessage(message, type = '') {
        adaptiveStatus.textContent = message;
        adaptiveStatus.className = `grammar-adaptive-status ${type}`.trim();
        adaptiveStatus.classList.remove('hidden');
    }

    async function startAdaptivePractice() {
        adaptiveStartBtn.disabled = true;
        adaptiveMessage('Selecting weak and contrasting grammar cards…');
        setSessionStep('controlled');
        adaptiveSession.classList.add('hidden');
        adaptiveTransfer.classList.add('hidden');
        adaptiveConversation.classList.add('hidden');
        adaptiveSpeaking.classList.add('hidden');
        adaptiveSummary.classList.add('hidden');
        try {
            const response = await fetch('/api/grammar/practice/session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ count: 6 }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not start practice.');
            if (!data.items || !data.items.length) {
                adaptiveMessage(data.message || 'Save some new grammar cards first.', 'warning');
                return;
            }
            adaptiveSessionData = data;
            adaptiveItemIndex = 0;
            adaptiveStatus.classList.add('hidden');
            loadScenarioChips();
            renderAdaptiveItem();
        } catch (error) {
            adaptiveMessage(error.message, 'error');
        } finally {
            adaptiveStartBtn.disabled = false;
        }
    }

    function renderAdaptiveItem() {
        const item = adaptiveSessionData.items[adaptiveItemIndex];
        adaptiveProgress.textContent = `${adaptiveItemIndex + 1} / ${adaptiveSessionData.items.length}`;
        adaptiveTopic.textContent = `${item.level || ''} · ${item.topic || 'Grammar'} · ${String(item.mode || 'standard').replace('-', ' ')}`;
        adaptiveFront.innerHTML = item.front_html || '<p>Practice prompt unavailable.</p>';
        adaptiveInputs.innerHTML = '';
        if (item.mode === 'input') {
            // Interpretation items are answered by choosing one meaning —
            // the correct option is never sent to the browser.
            const wrapper = document.createElement('div');
            wrapper.className = 'grammar-option-group';
            (item.answer_options || []).forEach((option, index) => {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'grammar-option-btn';
                button.textContent = option;
                button.addEventListener('click', () => {
                    wrapper.querySelectorAll('.grammar-option-btn').forEach(node => node.classList.remove('selected'));
                    button.classList.add('selected');
                    wrapper.dataset.selected = option;
                });
                wrapper.appendChild(button);
            });
            adaptiveInputs.appendChild(wrapper);
        } else {
            const labels = item.input_count === 2 ? ['Sentence 1', 'Sentence 2'] : ['Your answer'];
            labels.forEach((label, index) => {
                const wrapper = document.createElement('label');
                wrapper.className = 'grammar-adaptive-input-label';
                wrapper.textContent = label;
                const input = document.createElement(item.mode === 'mistake' ? 'textarea' : 'input');
                input.className = 'grammar-adaptive-input';
                input.dataset.answerIndex = String(index);
                input.autocomplete = 'off';
                if (input.tagName === 'TEXTAREA') input.rows = 3;
                input.addEventListener('keydown', event => {
                    if (event.key === 'Enter' && !event.shiftKey && input.tagName !== 'TEXTAREA') {
                        event.preventDefault();
                        checkAdaptiveAnswer();
                    }
                });
                wrapper.appendChild(input);
                adaptiveInputs.appendChild(wrapper);
            });
        }
        adaptiveFeedback.innerHTML = '';
        adaptiveFeedback.classList.add('hidden');
        adaptiveNextBtn.classList.add('hidden');
        adaptiveSubmitBtn.disabled = false;
        adaptiveSubmitBtn.textContent = 'Check answer';
        adaptiveSession.classList.remove('hidden');
        adaptiveTransfer.classList.add('hidden');
        const firstInput = adaptiveInputs.querySelector('.grammar-adaptive-input');
        if (firstInput) firstInput.focus();
    }

    function collectAdaptiveResponses() {
        if (adaptiveSessionData.items[adaptiveItemIndex].mode === 'input') {
            const wrapper = adaptiveInputs.querySelector('.grammar-option-group');
            const selected = wrapper ? wrapper.dataset.selected : '';
            return selected ? [selected] : [];
        }
        return Array.from(adaptiveInputs.querySelectorAll('.grammar-adaptive-input')).map(input => input.value.trim());
    }

    async function requestExplanation(kind, payload) {
        const response = await fetch('/api/grammar/practice/explain', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kind, apiKeys: getApiKeys(), ...payload }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Could not explain this answer.');
        return result;
    }

    function renderExplanation(container, explanation) {
        const block = document.createElement('div');
        block.className = 'grammar-explanation';
        block.innerHTML = `
            <div class="grammar-explanation-title">🤔 Why your answer was off</div>
            <p>${escapeHtml(explanation.explanation_en || '')}</p>
            <p lang="fa" dir="rtl">${escapeHtml(explanation.explanation_fa || '')}</p>
            ${explanation.focus_hint_en ? `<div class="grammar-focused-rule">${escapeHtml(explanation.focus_hint_en)}</div>` : ''}
            ${explanation.focus_hint_fa ? `<div class="grammar-focused-rule" lang="fa" dir="rtl">${escapeHtml(explanation.focus_hint_fa)}</div>` : ''}`;
        container.appendChild(block);
    }

    function attachExplainButton(container, kind, payload) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'grammar-explain-btn';
        button.textContent = '🤔 Explain my answer';
        button.addEventListener('click', async () => {
            button.disabled = true;
            button.textContent = 'Thinking…';
            try {
                const explanation = await requestExplanation(kind, payload);
                renderExplanation(container, explanation);
                button.remove();
            } catch (error) {
                button.disabled = false;
                button.textContent = '🤔 Explain my answer';
                const note = document.createElement('div');
                note.className = 'grammar-explain-error';
                note.textContent = error.message;
                container.appendChild(note);
            }
        });
        container.appendChild(button);
    }

    async function checkAdaptiveAnswer() {
        const responses = collectAdaptiveResponses();
        if (responses.some(value => !value)) {
            adaptiveFeedback.textContent = 'Choose or write every answer before checking.';
            adaptiveFeedback.className = 'grammar-adaptive-feedback error';
            return;
        }
        adaptiveSubmitBtn.disabled = true;
        try {
            const response = await fetch('/api/grammar/practice/check', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sessionId: adaptiveSessionData.session_id, itemIndex: adaptiveItemIndex, responses }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Could not check the answer.');
            const answerBlock = result.answers && result.answers.length
                ? `<div class="grammar-model-answer"><strong>Model answer:</strong> ${result.answers.map(escapeHtml).join(' · ')}</div>` : '';
            const backBlock = result.back_html
                ? `<details><summary>Full explanation</summary><div class="grammar-revealed-back">${result.back_html}</div></details>` : '';
            adaptiveFeedback.innerHTML = `
                <div class="grammar-feedback-title">${result.correct ? '✓ Correct' : (result.retry_required ? 'Try once more' : 'Model correction')}</div>
                <p>${escapeHtml(result.feedback_en || '')}</p>
                <p lang="fa" dir="rtl">${escapeHtml(result.feedback_fa || '')}</p>
                ${result.rule_en ? `<div class="grammar-focused-rule">${escapeHtml(result.rule_en)}</div>` : ''}
                ${result.rule_fa ? `<div class="grammar-focused-rule" lang="fa" dir="rtl">${escapeHtml(result.rule_fa)}</div>` : ''}
                ${answerBlock}${backBlock}`;
            adaptiveFeedback.className = `grammar-adaptive-feedback ${result.correct ? 'correct' : 'error'}`;
            adaptiveFeedback.classList.remove('hidden');
            if (result.retry_required) {
                attachExplainButton(adaptiveFeedback, 'controlled', {
                    sessionId: adaptiveSessionData.session_id,
                    itemIndex: adaptiveItemIndex,
                    responses,
                });
                adaptiveSubmitBtn.disabled = false;
                adaptiveSubmitBtn.textContent = 'Check retry';
                const firstInput = adaptiveInputs.querySelector('.grammar-adaptive-input');
                if (firstInput) firstInput.focus();
            } else {
                adaptiveInputs.querySelectorAll('.grammar-adaptive-input, .grammar-option-btn').forEach(node => { node.disabled = true; });
                adaptiveNextBtn.classList.remove('hidden');
                adaptiveNextBtn.textContent = adaptiveItemIndex === adaptiveSessionData.items.length - 1
                    ? 'Use these forms in a real situation →' : 'Next challenge →';
            }
        } catch (error) {
            adaptiveFeedback.textContent = error.message;
            adaptiveFeedback.className = 'grammar-adaptive-feedback error';
            adaptiveSubmitBtn.disabled = false;
        }
    }

    function showTransferTask() {
        const transfer = adaptiveSessionData.transfer || {};
        setSessionStep('free');
        adaptiveSession.classList.add('hidden');
        adaptiveTransfer.classList.remove('hidden');
        transferPromptEn.textContent = transfer.prompt_en || '';
        transferPromptFa.textContent = transfer.prompt_fa || '';
        transferResponse.value = '';
        transferResponse.disabled = false;
        transferSubmitBtn.disabled = false;
        transferSubmitBtn.textContent = 'Get focused feedback';
        transferFeedback.classList.add('hidden');
        startConversationBtn.classList.add('hidden');
        transferResponse.focus();
    }

    async function checkTransferResponse() {
        const learnerResponse = transferResponse.value.trim();
        if (!learnerResponse) return;
        transferSubmitBtn.disabled = true;
        try {
            const response = await fetch('/api/grammar/practice/transfer-feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sessionId: adaptiveSessionData.session_id, response: learnerResponse, apiKeys: getApiKeys() }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Could not evaluate transfer response.');
            const correction = result.corrected_response_it
                ? `<div class="grammar-model-answer"><strong>Suggested correction:</strong> ${escapeHtml(result.corrected_response_it)}</div>` : '';
            transferFeedback.innerHTML = `
                <div class="grammar-feedback-title">${result.correct ? '✓ Grammar used successfully' : (result.retry_required ? 'Repair and retry' : 'Model correction')}</div>
                <p>${escapeHtml(result.feedback_en || '')}</p>
                <p lang="fa" dir="rtl">${escapeHtml(result.feedback_fa || '')}</p>
                ${result.retry_required ? `<div class="grammar-focused-rule">${escapeHtml(result.retry_instruction_en || '')}</div><div class="grammar-focused-rule" lang="fa" dir="rtl">${escapeHtml(result.retry_instruction_fa || '')}</div>` : correction}`;
            transferFeedback.className = `grammar-adaptive-feedback ${result.correct ? 'correct' : 'error'}`;
            if (result.retry_required) {
                attachExplainButton(transferFeedback, 'transfer', {
                    sessionId: adaptiveSessionData.session_id,
                    response: learnerResponse,
                });
                transferSubmitBtn.disabled = false;
                transferSubmitBtn.textContent = 'Check transfer retry';
                transferResponse.focus();
            } else if (result.can_continue) {
                transferResponse.disabled = true;
                startConversationBtn.classList.remove('hidden');
            }
        } catch (error) {
            transferFeedback.textContent = error.message;
            transferFeedback.className = 'grammar-adaptive-feedback error';
            transferSubmitBtn.disabled = false;
        }
    }

    function addConversationBubble(role, text) {
        const bubble = document.createElement('div');
        bubble.className = `grammar-chat-bubble ${role}`;
        bubble.textContent = text;
        conversationLog.appendChild(bubble);
        conversationLog.scrollTop = conversationLog.scrollHeight;
    }

    async function loadScenarioChips() {
        if (!scenarioChips) return;
        try {
            const response = await fetch('/api/grammar/practice/scenarios');
            const scenarios = await response.json();
            if (!Array.isArray(scenarios) || !scenarios.length) return;
            scenarioChips.innerHTML = '<span class="grammar-scenario-label">Choose a situation:</span>' + scenarios.map(scenario =>
                `<button type="button" class="grammar-scenario-chip" data-scenario="${escapeAttr(scenario.key)}" title="${escapeAttr(scenario.focus_en || '')}">${escapeHtml(scenario.title_en)} <small>${escapeHtml(scenario.level || '')}</small></button>`
            ).join('');
            scenarioChips.classList.remove('hidden');
            scenarioChips.querySelectorAll('.grammar-scenario-chip').forEach(chip => {
                chip.addEventListener('click', () => startConversation(chip.dataset.scenario));
            });
        } catch { /* scenario picker stays hidden without the server list */ }
    }

    async function startConversation(scenarioKey) {
        setSessionStep('conversation');
        adaptiveTransfer.classList.add('hidden');
        adaptiveConversation.classList.remove('hidden');
        conversationLog.innerHTML = '';
        conversationFeedback.classList.add('hidden');
        startSpeakingBtn.classList.add('hidden');
        conversationResponse.value = '';
        conversationResponse.disabled = false;
        conversationSubmitBtn.disabled = true;
        try {
            const response = await fetch('/api/grammar/practice/conversation', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sessionId: adaptiveSessionData.session_id,
                    scenario: scenarioKey || null,
                }),
            });
            conversationContext = await response.json();
            if (!response.ok) throw new Error(conversationContext.error || 'Could not start the conversation.');
            scenarioChips?.querySelectorAll('.grammar-scenario-chip').forEach(chip =>
                chip.classList.toggle('active', chip.dataset.scenario === (scenarioKey || ''))
            );
            conversationScenario.textContent = conversationContext.scenario_en || 'A short Italian conversation';
            conversationScenarioFa.textContent = conversationContext.scenario_fa || '';
            conversationLog.innerHTML = '';
            addConversationBubble('tutor', conversationContext.opening_it || 'Parliamo in italiano.');
            conversationSubmitBtn.disabled = false;
            conversationResponse.focus();
        } catch (error) {
            conversationFeedback.textContent = error.message;
            conversationFeedback.className = 'grammar-adaptive-feedback error';
        }
    }

    async function submitConversationTurn() {
        const text = conversationResponse.value.trim();
        if (!text) return;
        conversationSubmitBtn.disabled = true;
        addConversationBubble('learner', text);
        try {
            const response = await fetch('/api/grammar/practice/conversation-turn', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sessionId: adaptiveSessionData.session_id, response: text, apiKeys: getApiKeys() }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Could not evaluate this reply.');
            const conversationCorrection = !result.correct && result.corrected_response_it
                ? `<div class="grammar-model-answer"><strong>Suggested correction:</strong> ${escapeHtml(result.corrected_response_it)}</div>` : '';
            conversationFeedback.innerHTML = `<div class="grammar-feedback-title">${result.correct ? '✓ Target grammar used' : (result.retry_required ? 'Repair this turn' : 'Model correction')}</div><p>${escapeHtml(result.feedback_en || '')}</p><p lang="fa" dir="rtl">${escapeHtml(result.feedback_fa || '')}</p>${result.retry_required ? `<div class="grammar-focused-rule">${escapeHtml(result.retry_hint_en || '')}</div><div class="grammar-focused-rule" lang="fa" dir="rtl">${escapeHtml(result.retry_hint_fa || '')}</div>` : conversationCorrection}`;
            conversationFeedback.className = `grammar-adaptive-feedback ${result.correct ? 'correct' : 'error'}`;
            conversationResponse.value = '';
            if (result.retry_required) {
                conversationSubmitBtn.disabled = false;
                conversationSubmitBtn.textContent = 'Send corrected reply';
                conversationResponse.focus();
                return;
            }
            if (result.reply_it) addConversationBubble('tutor', result.reply_it);
            conversationSubmitBtn.textContent = 'Send reply';
            if (result.complete) {
                conversationResponse.disabled = true;
                conversationSubmitBtn.disabled = true;
                startSpeakingBtn.classList.remove('hidden');
            } else {
                conversationSubmitBtn.disabled = false;
                conversationResponse.focus();
            }
        } catch (error) {
            conversationFeedback.textContent = error.message;
            conversationFeedback.className = 'grammar-adaptive-feedback error';
            conversationSubmitBtn.disabled = false;
        }
    }

    function startSpeaking() {
        setSessionStep('speaking');
        adaptiveConversation.classList.add('hidden');
        adaptiveSpeaking.classList.remove('hidden');
        speakingTranscript.value = '';
        speakingTranscript.disabled = false;
        speakingSubmitBtn.disabled = false;
        speakingSubmitBtn.textContent = 'Check spoken grammar';
        speakingFeedback.classList.add('hidden');
        adaptiveFinishBtn.classList.add('hidden');
    }

    function toggleSpeechRecognition() {
        const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!Recognition) {
            speakingFeedback.textContent = 'Live transcription is not available in this browser. Type what you said, then check the grammar.';
            speakingFeedback.className = 'grammar-adaptive-feedback error';
            speakingTranscript.focus();
            return;
        }
        if (speechRecognition) {
            speechRecognition.stop();
            return;
        }
        speechRecognition = new Recognition();
        speechRecognition.lang = 'it-IT';
        speechRecognition.interimResults = true;
        speechRecognition.continuous = false;
        speechRecognition.onstart = () => {
            speakingRecordBtn.classList.add('recording');
            speakingRecordBtn.textContent = '■ Stop recording';
        };
        speechRecognition.onresult = event => {
            speakingTranscript.value = Array.from(event.results).map(result => result[0].transcript).join(' ');
        };
        speechRecognition.onend = () => {
            speakingRecordBtn.classList.remove('recording');
            speakingRecordBtn.textContent = '🎙 Start recording';
            speechRecognition = null;
        };
        speechRecognition.onerror = event => {
            speakingFeedback.textContent = `Could not transcribe speech: ${event.error}. You can type the transcript manually.`;
            speakingFeedback.className = 'grammar-adaptive-feedback error';
        };
        speechRecognition.start();
    }

    async function checkSpeaking() {
        const text = speakingTranscript.value.trim();
        if (!text) return;
        speakingSubmitBtn.disabled = true;
        try {
            const response = await fetch('/api/grammar/practice/transfer-feedback', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sessionId: adaptiveSessionData.session_id, response: text, stage: 'speaking', apiKeys: getApiKeys() }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Could not check spoken grammar.');
            speakingFeedback.innerHTML = `<div class="grammar-feedback-title">${result.correct ? '✓ Grammar available in speech' : (result.retry_required ? 'Say it once more' : 'Speaking correction')}</div><p>${escapeHtml(result.feedback_en || '')}</p><p lang="fa" dir="rtl">${escapeHtml(result.feedback_fa || '')}</p>${result.retry_required ? `<div class="grammar-focused-rule">${escapeHtml(result.retry_instruction_en || '')}</div>` : (result.corrected_response_it ? `<div class="grammar-model-answer"><strong>Suggested form:</strong> ${escapeHtml(result.corrected_response_it)}</div>` : '')}`;
            speakingFeedback.className = `grammar-adaptive-feedback ${result.correct ? 'correct' : 'error'}`;
            if (result.retry_required) {
                attachExplainButton(speakingFeedback, 'transfer', {
                    sessionId: adaptiveSessionData.session_id,
                    response: text,
                });
                speakingSubmitBtn.disabled = false;
                speakingSubmitBtn.textContent = 'Check speaking retry';
                speakingTranscript.focus();
            } else {
                speakingTranscript.disabled = true;
                adaptiveFinishBtn.classList.remove('hidden');
            }
        } catch (error) {
            speakingFeedback.textContent = error.message;
            speakingFeedback.className = 'grammar-adaptive-feedback error';
            speakingSubmitBtn.disabled = false;
        }
    }

    async function showSessionSummary() {
        adaptiveSpeaking.classList.add('hidden');
        adaptiveSummary.classList.remove('hidden');
        sessionSummaryContent.innerHTML = '<div class="grammar-empty-insight">Building your summary…</div>';
        try {
            const response = await fetch('/api/grammar/practice/summary', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sessionId: adaptiveSessionData.session_id }),
            });
            const summary = await response.json();
            if (!response.ok) throw new Error(summary.error || 'Could not build the summary.');

            const stageLabels = { input: 'Interpretation', controlled: 'Controlled', free: 'Free use', conversation: 'Conversation', speaking: 'Speaking' };
            const stageAccuracy = summary.stage_accuracy || {};
            const stageBars = Object.entries(stageLabels).map(([key, label]) => {
                const value = Math.max(0, Math.min(100, Number(stageAccuracy[key] ?? 0)));
                const attempted = stageAccuracy[key] !== null && stageAccuracy[key] !== undefined;
                return `<div class="grammar-report-stage"><span>${label}</span><div class="grammar-stage-meter"><span style="width:${value}%"></span></div><strong>${attempted ? `${value}%` : '—'}</strong></div>`;
            }).join('');

            const patterns = (summary.error_patterns || []).map(item =>
                `<span class="grammar-pattern-tag">${escapeHtml(String(item.error_type || 'grammar').replaceAll('_', ' '))} ×${Number(item.count || 0)}</span>`
            ).join('') || '<span class="grammar-empty-insight">No error pattern in this session.</span>';

            const topicRows = (summary.topic_report || []).map(topic => {
                const misses = Number(topic.controlled_misses || 0) + Number(topic.input_misses || 0)
                    + Number(topic.transfer_failures || 0) + Number(topic.speaking_failures || 0)
                    + Number(topic.conversation_failures || 0);
                return `<div class="grammar-report-topic"><div><strong>${escapeHtml(topic.topic)}</strong><small>${misses ? `${misses} miss${misses > 1 ? 'es' : ''}` : 'clean'}</small></div>${topic.needs_repair ? `<button type="button" class="grammar-repair-btn" data-topic="${escapeAttr(topic.topic)}" data-key="${escapeAttr(topic.topic_key)}">🛠 Repair cards</button>` : '<span class="grammar-report-clean">✓</span>'}</div>`;
            }).join('');

            sessionSummaryContent.innerHTML = `
                <div class="grammar-report-stages">${stageBars}</div>
                <div class="grammar-report-section"><h4>Error patterns</h4><div class="grammar-pattern-tags">${patterns}</div></div>
                <div class="grammar-report-section"><h4>Topic outcomes</h4><div class="grammar-report-topics">${topicRows || '<span class="grammar-empty-insight">No topics recorded.</span>'}</div></div>
                <div class="grammar-summary-card" style="grid-column:1/-1"><span>${escapeHtml(summary.next_review || '')}</span></div>`;

            sessionSummaryContent.querySelectorAll('.grammar-repair-btn').forEach(button => {
                button.addEventListener('click', () => {
                    const topic = button.dataset.topic;
                    modeSwitcher.querySelectorAll('.grammar-mode-tab').forEach(tab =>
                        tab.classList.toggle('active', tab.dataset.mode === 'mistake'));
                    currentMode = 'mistake';
                    summaryDoneBtn.click();
                    activateView('create');
                    topicInput.value = topic;
                    generateGrammarCard(topic, 'mistake');
                });
            });
        } catch (error) {
            sessionSummaryContent.innerHTML = `<div class="grammar-empty-insight">${escapeHtml(error.message)}</div>`;
        }
    }

    async function loadCrossTrainingErrors() {
        if (!crossTrainingErrors) return;
        try {
            const response = await fetch('/api/insights/errors');
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load error insights.');
            const patterns = data.top || [];
            crossTrainingErrors.innerHTML = patterns.length ? patterns.map(item =>
                `<div class="grammar-insight-item"><div><strong>${escapeHtml(String(item.label || 'general'))}</strong><small>${escapeHtml(item.source_label || item.source || '')} · ${escapeHtml(String(item.error_type || '').replaceAll('_', ' '))}</small></div><span class="grammar-insight-score">×${Number(item.count || 0)}</span></div>`
            ).join('')
                : '<div class="grammar-empty-insight">Nothing recurring yet across practice surfaces.</div>';
        } catch (error) {
            crossTrainingErrors.innerHTML = `<div class="grammar-empty-insight">${escapeHtml(error.message)}</div>`;
        }
    }

    // --- Dictogloss (listen & reconstruct) ---

    function dictoglossMessage(message, type = '') {
        dictoglossStatus.textContent = message;
        dictoglossStatus.className = `grammar-adaptive-status ${type}`.trim();
        dictoglossStatus.classList.remove('hidden');
    }

    async function startDictogloss(event) {
        event.preventDefault();
        const topic = dictoglossTopic.value.trim();
        if (!topic || dictoglossStartBtn.disabled) return;
        dictoglossStartBtn.disabled = true;
        dictoglossSession.classList.add('hidden');
        dictoglossResult.classList.add('hidden');
        dictoglossRetryBtn.classList.add('hidden');
        dictoglossMessage('Writing a short text and generating the audio…');
        try {
            const response = await fetch('/api/grammar/dictogloss/text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ topic, apiKeys: getApiKeys() }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not build the dictogloss text.');
            dictoglossSessionId = data.session_id;
            dictoglossAudio.src = `data:audio/mp3;base64,${data.audio_b64}`;
            dictoglossLevel.textContent = `${data.level || ''} · ${data.word_count || '?'} words`;
            dictoglossFocus.textContent = data.grammar_focus_en || '';
            dictoglossResponse.value = '';
            dictoglossResponse.disabled = false;
            dictoglossCheckBtn.disabled = false;
            dictoglossCheckBtn.textContent = 'Check reconstruction';
            dictoglossSession.classList.remove('hidden');
            hideDictoglossStatus();
        } catch (error) {
            dictoglossMessage(error.message, 'error');
        } finally {
            dictoglossStartBtn.disabled = false;
        }
    }

    function hideDictoglossStatus() {
        dictoglossStatus.classList.add('hidden');
    }

    async function checkDictogloss() {
        const text = dictoglossResponse.value.trim();
        if (!text || !dictoglossSessionId || dictoglossCheckBtn.disabled) return;
        dictoglossCheckBtn.disabled = true;
        dictoglossCheckBtn.textContent = 'Comparing with the original…';
        try {
            const response = await fetch('/api/grammar/dictogloss/check', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sessionId: dictoglossSessionId,
                    response: text,
                    apiKeys: getApiKeys(),
                }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Could not check the reconstruction.');
            const originalBlock = `
                <div class="grammar-model-answer"><strong>Original text:</strong> ${escapeHtml(result.text_it || '')}</div>
                ${result.translation_en ? `<div class="grammar-focused-rule">${escapeHtml(result.translation_en)}</div>` : ''}`;
            const correction = !result.correct && result.corrected_response_it
                ? `<div class="grammar-model-answer"><strong>Your text, corrected:</strong> ${escapeHtml(result.corrected_response_it)}</div>` : '';
            dictoglossResult.innerHTML = `
                <div class="grammar-feedback-title">${result.correct ? '✓ Reconstructed' : (result.retry_required ? 'Listen once more and retry' : 'Model text')}</div>
                <p>${escapeHtml(result.feedback_en || '')}</p>
                <p lang="fa" dir="rtl">${escapeHtml(result.feedback_fa || '')}</p>
                ${result.retry_required ? correction : correction + originalBlock}`;
            dictoglossResult.className = `grammar-adaptive-feedback ${result.correct ? 'correct' : 'error'}`;
            dictoglossResult.classList.remove('hidden');
            if (result.retry_required) {
                dictoglossRetryBtn.classList.remove('hidden');
                dictoglossResponse.disabled = false;
            } else {
                dictoglossRetryBtn.classList.add('hidden');
                dictoglossResponse.disabled = true;
            }
        } catch (error) {
            dictoglossResult.textContent = error.message;
            dictoglossResult.className = 'grammar-adaptive-feedback error';
            dictoglossResult.classList.remove('hidden');
        } finally {
            dictoglossCheckBtn.disabled = false;
            dictoglossCheckBtn.textContent = 'Check reconstruction';
        }
    }

    // --- Card graduation ---

    function renderMySentenceNudge(data) {
        const nudge = data.my_sentence;
        if (!nudge || !nudge.notes) return;
        const item = document.createElement('div');
        item.className = 'grammar-insight-item';
        item.innerHTML = `<div><strong>Personal sentences</strong><small>${nudge.personalized} of ${nudge.notes} cards have your own sentence — fill the ✏️ box when you review</small></div><span class="grammar-insight-score">${nudge.personalized}/${nudge.notes}</span>`;
        graduationDetail.appendChild(item);
    }

    async function loadGraduation() {
        if (!graduationStats) return;
        try {
            const [gradResponse, overviewResponse] = await Promise.all([
                fetch('/api/anki/graduation'),
                fetch('/api/grammar/practice/overview'),
            ]);
            graduationPlanData = await gradResponse.json();
            if (!gradResponse.ok) throw new Error(graduationPlanData.error || 'Could not load graduation data.');
            const plan = graduationPlanData;
            graduationStats.innerHTML =
                `<span><strong>${plan.production_cards || 0}</strong> production cards</span>` +
                `<span><strong>${plan.mature || 0}</strong> ready for production</span>` +
                `<span><strong>${plan.immature || 0}</strong> still recognition-only</span>`;
            graduationDetail.innerHTML = '';
            const changes = (plan.to_release || []).length + (plan.to_suspend || []).length;
            if (plan.to_release?.length) {
                graduationDetail.insertAdjacentHTML('beforeend',
                    `<div class="grammar-insight-item"><div><strong>Release ${plan.to_release.length} production card${plan.to_release.length > 1 ? 's' : ''}</strong><small>Anki shows the recognition card is maturing</small></div><span class="grammar-insight-score">▶</span></div>`);
            }
            if (plan.to_suspend?.length) {
                graduationDetail.insertAdjacentHTML('beforeend',
                    `<div class="grammar-insight-item"><div><strong>Hold back ${plan.to_suspend.length} production card${plan.to_suspend.length > 1 ? 's' : ''}</strong><small>Recognition needs ${plan.graduation_min_reps || 3} reviews first</small></div><span class="grammar-insight-score">⏸</span></div>`);
            }
            if (!changes) {
                graduationDetail.insertAdjacentHTML('beforeend',
                    '<div class="grammar-insight-item"><div><strong>Everything is in its right stage</strong><small>No graduation changes needed right now</small></div><span class="grammar-insight-score">✓</span></div>');
            }
            graduationRunBtn.classList.toggle('hidden', !changes);
            graduationRunBtn.textContent = `Apply ${changes} graduation change${changes > 1 ? 's' : ''}`;
            if (overviewResponse.ok) renderMySentenceNudge(await overviewResponse.json());
        } catch (error) {
            graduationStats.innerHTML = `<span>${escapeHtml(error.message)}</span>`;
        }
    }

    async function runGraduation() {
        if (!graduationPlanData || graduationRunBtn.disabled) return;
        graduationRunBtn.disabled = true;
        try {
            const response = await fetch('/api/anki/graduation/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ apply: true }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Could not apply graduation.');
            loadGraduation();
        } catch (error) {
            graduationStats.innerHTML = `<span>${escapeHtml(error.message)}</span>`;
        } finally {
            graduationRunBtn.disabled = false;
        }
    }

    // --- Event Listeners ---
    grammarForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const topic = topicInput.value.trim();
        if (topic) generateGrammarCard(topic);
    });

    saveToAnkiBtn.addEventListener('click', saveToAnki);
    workspaceTabs.forEach(tab => tab.addEventListener('click', () => activateView(tab.dataset.view || 'today')));
    adaptiveStartBtn?.addEventListener('click', startAdaptivePractice);
    adaptiveSubmitBtn?.addEventListener('click', checkAdaptiveAnswer);
    adaptiveNextBtn?.addEventListener('click', () => {
        if (adaptiveItemIndex < adaptiveSessionData.items.length - 1) {
            adaptiveItemIndex++;
            renderAdaptiveItem();
        } else {
            showTransferTask();
        }
    });
    transferSubmitBtn?.addEventListener('click', checkTransferResponse);
    dictoglossForm?.addEventListener('submit', startDictogloss);
    dictoglossCheckBtn?.addEventListener('click', checkDictogloss);
    graduationRunBtn?.addEventListener('click', runGraduation);
    dictoglossRetryBtn?.addEventListener('click', () => {
        dictoglossResult.classList.add('hidden');
        dictoglossRetryBtn.classList.add('hidden');
        dictoglossResponse.focus();
    });
    startConversationBtn?.addEventListener('click', startConversation);
    conversationSubmitBtn?.addEventListener('click', submitConversationTurn);
    startSpeakingBtn?.addEventListener('click', startSpeaking);
    speakingRecordBtn?.addEventListener('click', toggleSpeechRecognition);
    speakingSubmitBtn?.addEventListener('click', checkSpeaking);
    adaptiveFinishBtn?.addEventListener('click', showSessionSummary);
    summaryDoneBtn?.addEventListener('click', () => {
        adaptiveSummary.classList.add('hidden');
        adaptiveMessage('Session complete. Your next delayed transfer will appear here when it is due.', 'success');
        adaptiveSessionData = null;
        setSessionStep('controlled');
        loadPracticeOverview();
        loadTopics();
        loadCrossTrainingErrors();
    });

    // Search
    topicSearch.addEventListener('input', () => {
        if (topicsCache) {
            const activeLevel = document.querySelector('.grammar-level-btn.active')?.dataset.level || 'all';
            renderTopicGrid(topicsCache, topicSearch.value, activeLevel);
        }
    });

    // Level filter buttons
    document.querySelectorAll('.grammar-level-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.grammar-level-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            if (topicsCache) {
                renderTopicGrid(topicsCache, topicSearch.value, btn.dataset.level);
            }
        });
    });

    // --- Init ---
    checkAnkiStatus();
    loadPracticeOverview();
    loadTopics();
    loadCrossTrainingErrors();
    loadGraduation();
})();
