(() => {
    const status = document.getElementById('deckStatsStatus');
    const grid = document.getElementById('deckStatsGrid');
    const button = document.getElementById('refreshDeckStats');
    let revision = 0;
    const filters = [
        ['Due now', 'is:due -is:suspended -is:buried'],
        ['New cards', 'is:new'], ['Learning / relearning', 'is:learn'],
        ['Review cards', 'is:review -is:learn'],
        ['Mature cards', 'is:review -is:learn prop:ivl>=21'],
        ['Suspended', 'is:suspended'], ['Buried', 'is:buried'],
        ['Cards added in 7 days', 'added:7']
    ];
    async function read(action, params = {}) {
        const response = await fetch(ANKICONNECT_URL, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action, version: 6, params}),
            signal: AbortSignal.timeout(15000)
        });
        if (!response.ok) throw new Error('AnkiConnect could not be reached.');
        const data = await response.json();
        if (data.error) throw new Error(data.error);
        return data.result;
    }
    async function refresh() {
        const current = ++revision;
        const deck = localStorage.getItem('isCreatingNewDeck') === 'true'
            ? (localStorage.getItem('newDeckName') || 'Default')
            : (localStorage.getItem('deckName') || 'Italian');
        grid.replaceChildren();
        status.textContent = 'Loading ' + deck + '…';
        button.disabled = true;
        try {
            const decks = await read('deckNames');
            if (!decks.includes(deck)) throw new Error('Deck not found: ' + deck);
            const escaped = deck.replaceAll(String.fromCharCode(92), String.fromCharCode(92,92))
                .replaceAll('"', String.fromCharCode(92) + '"');
            const query = 'deck:"' + escaped + '"';
            const notes = await read('findNotes', {query});
            const words = new Set();
            for (let i = 0; i < notes.length; i += 500) {
                const batch = await read('notesInfo', {notes: notes.slice(i, i + 500)});
                for (const note of batch) {
                    const value = note.fields?.Word?.value || '';
                    const doc = new DOMParser().parseFromString(value.replace(/\[sound:[^\]]*\]/g, ''), 'text/html');
                    const word = doc.body.textContent.normalize('NFC').toLowerCase()
                        .replace(/ß/g, 'ss').replace(/ς/g, 'σ').trim().replace(/\s+/g, ' ');
                    if (word) words.add(word);
                }
            }
            const metrics = [['Unique vocabulary entries', words.size], ['Notes', notes.length]];
            for (const [label, filter] of [['Cards', ''], ...filters]) {
                metrics.push([label, (await read('findCards', {query: query + (filter ? ' ' + filter : '')})).length]);
            }
            if (current !== revision) return;
            for (const [label, count] of metrics) {
                const item = document.createElement('div');
                const term = document.createElement('dt');
                const value = document.createElement('dd');
                term.textContent = label;
                value.textContent = count.toLocaleString();
                item.append(term, value);
                grid.append(item);
            }
            status.textContent = deck + ' · Updated ' + new Date().toLocaleTimeString();
        } catch (error) {
            if (current === revision) status.textContent =
                'Statistics unavailable. Keep Anki open with AnkiConnect enabled. ' + error.message;
        } finally {
            if (current === revision) button.disabled = false;
        }
    }
    button.addEventListener('click', refresh);
    window.addEventListener('anki-deck-changed', refresh);
    window.addEventListener('focus', refresh);
    window.addEventListener('storage', event => {
        if (['deckName', 'newDeckName', 'isCreatingNewDeck'].includes(event.key)) refresh();
    });
    refresh();
})();
