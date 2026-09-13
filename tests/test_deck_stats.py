import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
import cli
from deck_stats import get_deck_stats, normalized_word

class DeckStatsTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalized_word('<b>CITTÀ</b>&nbsp;[sound:a.mp3]'), 'città')
        self.assertEqual(normalized_word('fare   una pausa'), 'fare una pausa')

    def test_counts_words_independently_from_cards(self):
        calls = []
        def invoke(action, params=None):
            calls.append((action, params))
            if action == 'deckNames': return ['Italian']
            if action == 'findNotes': return [1, 2, 3, 4]
            if action == 'notesInfo':
                return [{'fields': {'Word': {'value': w}}} for w in ['Ciao', '<b>ciao</b>', 'fare una pausa', '']]
            if action == 'findCards': return [1, 2, 3, 4, 5, 6] if params['query'] == 'deck:"Italian"' else []
            raise AssertionError(action)
        stats = get_deck_stats(invoke, 'Italian')
        self.assertEqual((stats['words'], stats['notes'], stats['cards']), (2, 4, 6))
        self.assertEqual(stats['due'], 0)
        self.assertTrue(all(a in {'deckNames', 'findNotes', 'notesInfo', 'findCards'} for a, _ in calls))

    def test_missing_deck(self):
        with self.assertRaisesRegex(ValueError, 'Deck not found'):
            get_deck_stats(lambda *a: [], 'Missing')

    def test_stats_cli_needs_no_generation_keys(self):
        with patch.object(cli.sys, 'argv', ['anki', 'stats', '--deck', 'Test']), patch.object(cli, 'print_deck_stats') as show, patch.object(cli, '_require_generation_keys') as keys:
            self.assertEqual(cli.main(), 0)
            show.assert_called_once_with(cli.invoke_anki, 'Test')
            keys.assert_not_called()

    def test_offline_cli(self):
        with patch.object(cli.sys, 'argv', ['anki', '--stats']), patch.object(cli, 'print_deck_stats', side_effect=RuntimeError('offline')), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(), 1)
        self.assertIn('Keep Anki open', output.getvalue())

    def test_stats_rejects_generation_inputs(self):
        for argv in [['stats', '--file', 'x'], ['--stats', 'ciao'], ['stats', '--context', 'x']]:
            parser = cli.build_parser()
            with self.assertRaises(SystemExit):
                cli._validate_operation_args(parser, parser.parse_args(argv))
