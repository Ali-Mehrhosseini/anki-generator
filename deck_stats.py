"""Read-only deck statistics."""
import re
import unicodedata
from html.parser import HTMLParser

class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)

def normalized_word(value):
    parser = _Text()
    parser.feed(re.sub(r'\[sound:[^\]]*\]', '', value))
    return ' '.join(unicodedata.normalize('NFC', ''.join(parser.parts)).casefold().split())

FILTERS = {
    'new': 'is:new', 'learning': 'is:learn',
    'review': 'is:review -is:learn',
    'mature': 'is:review -is:learn prop:ivl>=21',
    'due': 'is:due -is:suspended -is:buried',
    'suspended': 'is:suspended', 'buried': 'is:buried', 'added_week': 'added:7',
}

def get_deck_stats(invoke, deck):
    if not deck or deck not in (invoke('deckNames') or []):
        raise ValueError(f'Deck not found: {deck}')
    escaped = deck.replace(chr(92), chr(92)*2).replace('"', chr(92)+'"')
    query = f'deck:"{escaped}"'
    note_ids = invoke('findNotes', {'query': query}) or []
    words = set()
    vocabulary_notes = 0
    for offset in range(0, len(note_ids), 500):
        for note in invoke('notesInfo', {'notes': note_ids[offset:offset + 500]}) or []:
            word = normalized_word(str(note.get('fields', {}).get('Word', {}).get('value', '')))
            if word:
                words.add(word)
                vocabulary_notes += 1
    result = {'deck': deck, 'words': len(words), 'notes': len(note_ids),
              'vocabulary_notes': vocabulary_notes,
              'cards': len(invoke('findCards', {'query': query}) or [])}
    for name, suffix in FILTERS.items():
        result[name] = len(invoke('findCards', {'query': f'{query} {suffix}'}) or [])
    return result

def print_deck_stats(invoke, deck):
    stats = get_deck_stats(invoke, deck)
    print(f"\nDeck overview — {stats['deck']} (including subdecks)")
    for key, label in [('words', 'Unique vocabulary entries'), ('notes', 'Notes'),
                       ('cards', 'Cards'), ('due', 'Due now'), ('new', 'New cards'),
                       ('learning', 'Learning / relearning'), ('review', 'Review cards'),
                       ('mature', 'Mature cards (21+ day interval)'),
                       ('suspended', 'Suspended'), ('buried', 'Buried'),
                       ('added_week', 'Cards added in last 7 days')]:
        print(f"  {label}: {stats[key]:,}")
    print('Vocabulary counts distinct non-empty Word fields, ignoring case and HTML.')
    print('Phrases count as one entry; notes without Word fields are excluded.')
    print('Card categories overlap. Mature cards do not necessarily mean words you know.')
