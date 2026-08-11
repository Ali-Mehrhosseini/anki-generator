import unittest
import io
from contextlib import redirect_stdout
from unittest.mock import patch

import cli


INTERPRETATION_OPTIONS = [
    {
        "headword": "entro",
        "part_of_speech": "preposition",
        "meaning_en": "by; within",
        "meaning_fa": "تا؛ در عرض",
        "explanation": "Used for a deadline.",
    },
    {
        "headword": "entrare",
        "part_of_speech": "verb",
        "meaning_en": "to enter",
        "meaning_fa": "وارد شدن",
        "explanation": "Entro means I enter.",
    },
]


class CliParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = cli.build_parser()

    def test_backfill_is_preview_without_apply(self):
        args = self.parser.parse_args(["--backfill-production"])
        selected = cli._validate_operation_args(self.parser, args)
        self.assertTrue(selected)
        self.assertFalse(args.apply)

    def test_apply_and_dry_run_are_mutually_exclusive(self):
        args = self.parser.parse_args([
            "--backfill-production",
            "--apply",
            "--dry-run",
        ])
        with self.assertRaises(SystemExit) as error:
            cli._validate_operation_args(self.parser, args)
        self.assertEqual(error.exception.code, 2)

    def test_words_cannot_be_combined_with_migration(self):
        args = self.parser.parse_args([
            "rispettare",
            "--backfill-production",
        ])
        with self.assertRaises(SystemExit) as error:
            cli._validate_operation_args(self.parser, args)
        self.assertEqual(error.exception.code, 2)

    def test_force_is_rollback_only(self):
        args = self.parser.parse_args([
            "--backfill-production",
            "--force",
        ])
        with self.assertRaises(SystemExit) as error:
            cli._validate_operation_args(self.parser, args)
        self.assertEqual(error.exception.code, 2)

    def test_existing_word_command_remains_valid(self):
        args = self.parser.parse_args([
            "rispettare",
            "--no-common-phrases",
        ])
        selected = cli._validate_operation_args(self.parser, args)
        self.assertFalse(selected)
        self.assertEqual(args.words, ["rispettare"])

    def test_teach_is_a_valid_clipboard_command(self):
        args = self.parser.parse_args(["teach"])

        selected = cli._validate_operation_args(self.parser, args)

        self.assertFalse(selected)
        self.assertEqual(args.words, ["teach"])

    def test_practice_is_a_valid_standalone_command(self):
        args = self.parser.parse_args(["practice"])

        selected = cli._validate_operation_args(self.parser, args)

        self.assertFalse(selected)
        self.assertEqual(args.words, ["practice"])

    def test_practice_rejects_words_file_and_context(self):
        for argv in (
            ["practice", "entro"],
            ["practice", "--file", "words.txt"],
            ["practice", "--context", "example"],
        ):
            with self.subTest(argv=argv):
                args = self.parser.parse_args(argv)
                with self.assertRaises(SystemExit) as error:
                    cli._validate_operation_args(self.parser, args)
                self.assertEqual(error.exception.code, 2)

    def test_teach_rejects_extra_text_file_or_context(self):
        for argv in (
            ["teach", "article text"],
            ["teach", "--file", "article.txt"],
            ["teach", "--context", "article text"],
        ):
            with self.subTest(argv=argv):
                args = self.parser.parse_args(argv)
                with self.assertRaises(SystemExit) as error:
                    cli._validate_operation_args(self.parser, args)
                self.assertEqual(error.exception.code, 2)

    def test_context_is_optional_and_preserves_normal_word_command(self):
        normal = self.parser.parse_args(["entro"])
        contextual = self.parser.parse_args([
            "entro",
            "--context",
            "Il servizio è offerto entro i 27 anni.",
        ])

        self.assertIsNone(normal.context)
        self.assertEqual(contextual.words, ["entro"])
        self.assertIn("entro i 27 anni", contextual.context)
        self.assertFalse(
            cli._validate_operation_args(self.parser, contextual)
        )

    def test_context_requires_one_word_and_no_file(self):
        for argv in (
            ["entro", "offerto", "--context", "example"],
            ["--file", "words.txt", "--context", "example"],
        ):
            with self.subTest(argv=argv):
                args = self.parser.parse_args(argv)
                with self.assertRaises(SystemExit) as error:
                    cli._validate_operation_args(self.parser, args)
                self.assertEqual(error.exception.code, 2)

    def test_limit_is_backfill_only_and_positive(self):
        for argv in (
            ["rispettare", "--limit", "1"],
            ["--backfill-production", "--limit", "0"],
            ["--backfill-production", "--note-id", "-1"],
        ):
            with self.subTest(argv=argv):
                args = self.parser.parse_args(argv)
                with self.assertRaises(SystemExit) as error:
                    cli._validate_operation_args(self.parser, args)
                self.assertEqual(error.exception.code, 2)

    def test_learning_flags_are_rejected_for_migrations(self):
        args = self.parser.parse_args([
            "--backfill-production",
            "--no-smart-grammar",
        ])
        with self.assertRaises(SystemExit) as error:
            cli._validate_operation_args(self.parser, args)
        self.assertEqual(error.exception.code, 2)

    def test_saved_migration_language_cannot_be_overridden(self):
        args = self.parser.parse_args([
            "--resume-production-backfill",
            "abc",
            "--language",
            "Spanish",
        ])
        with self.assertRaises(SystemExit) as error:
            cli._validate_operation_args(self.parser, args)
        self.assertEqual(error.exception.code, 2)

    def test_recall_sort_field_is_a_previewable_operation(self):
        args = self.parser.parse_args([
            "--recall-sort-field",
            "word",
        ])
        selected = cli._validate_operation_args(self.parser, args)
        self.assertTrue(selected)
        self.assertFalse(args.apply)

    def test_recall_sort_field_is_mutually_exclusive_with_backfill(self):
        with self.assertRaises(SystemExit) as error:
            self.parser.parse_args([
                "--backfill-production",
                "--recall-sort-field",
                "word",
            ])
        self.assertEqual(error.exception.code, 2)

    def test_recall_sort_helper_install_is_previewable(self):
        args = self.parser.parse_args([
            "--install-recall-sort-helper",
        ])
        selected = cli._validate_operation_args(self.parser, args)
        self.assertTrue(selected)
        self.assertFalse(args.apply)

    def test_production_audio_upgrade_is_previewable(self):
        args = self.parser.parse_args([
            "--upgrade-production-audio",
        ])
        selected = cli._validate_operation_args(self.parser, args)
        self.assertTrue(selected)
        self.assertFalse(args.apply)

    def test_word_command_ctrl_c_exits_cleanly_without_traceback(self):
        output = io.StringIO()
        with (
            patch.object(cli, "_require_generation_keys"),
            patch.object(cli, "add_word_to_anki", side_effect=KeyboardInterrupt),
            patch.object(cli.sys, "argv", ["anki", "costarci"]),
            redirect_stdout(output),
        ):
            result = cli.main()

        self.assertEqual(result, 130)
        self.assertIn("Cancelled safely", output.getvalue())
        self.assertIn("Completed before stopping: 0 of 1", output.getvalue())


class ProductionAudioUpgradeTests(unittest.TestCase):
    def test_upgrade_changes_templates_not_notes(self):
        models = {
            cli.NOTE_TYPE: {
                cli.PRODUCTION_TEMPLATE_NAME: {
                    "Front": cli.PRODUCTION_TEMPLATE_FRONT,
                    "Back": cli.PRODUCTION_TEMPLATE_BACK_LEGACY,
                },
            },
            cli.OWNED_MODEL_NAME: {
                cli.OWNED_TEMPLATE_NAME: {
                    "Front": cli.OWNED_TEMPLATE_FRONT,
                    "Back": cli.OWNED_TEMPLATE_BACK_LEGACY,
                },
            },
        }
        calls = []

        def fake_invoke(action, params=None):
            params = params or {}
            calls.append((action, params))
            if action == "modelNamesAndIds":
                return {name: index + 1 for index, name in enumerate(models)}
            if action == "modelTemplates":
                return models[params["modelName"]]
            if action == "findNotes":
                return [1, 2, 3]
            if action == "notesInfo":
                # Both target note types have three production notes in this
                # focused fake; only the non-empty field matters here.
                return [
                    {
                        "fields": {
                            cli.PRODUCTION_BACK_FIELD: {"value": "card"},
                            "ProductionBack": {"value": "card"},
                        },
                    }
                    for _ in params["notes"]
                ]
            if action == "updateModelTemplates":
                model = params["model"]
                models[model["name"]].update(model["templates"])
                return None
            raise AssertionError(action)

        original = cli.invoke_anki
        cli.invoke_anki = fake_invoke
        try:
            preview = cli._inspect_production_audio_upgrade()
            upgraded = cli._apply_production_audio_upgrade(preview)
        finally:
            cli.invoke_anki = original

        self.assertEqual(len(upgraded), 2)
        self.assertTrue(all(item["note_count"] == 3 for item in upgraded))
        self.assertEqual(
            models[cli.NOTE_TYPE][cli.PRODUCTION_TEMPLATE_NAME]["Back"],
            cli.PRODUCTION_TEMPLATE_BACK,
        )
        self.assertEqual(
            models[cli.OWNED_MODEL_NAME][cli.OWNED_TEMPLATE_NAME]["Back"],
            cli.OWNED_TEMPLATE_BACK,
        )
        actions = [action for action, _ in calls]
        self.assertEqual(actions.count("updateModelTemplates"), 2)
        self.assertNotIn("updateNoteFields", actions)
        self.assertNotIn("updateNote", actions)


class CliInterpretationTests(unittest.TestCase):
    def test_duplicate_explanation_uses_generated_relation_note(self):
        explanation = cli.get_duplicate_form_explanation(
            "offerto",
            "offrire",
            {
                "back_html": (
                    "<div><ul><li>Offerto is the past participle of offrire.</li>"
                    "<li>Origin: from Latin offerre.</li></ul></div>"
                ),
            },
        )

        self.assertEqual(
            explanation,
            "Offerto is the past participle of offrire.",
        )

    def test_past_participle_explanation_does_not_depend_on_html(self):
        explanation = cli.get_duplicate_form_explanation(
            "offerto",
            "offrire",
            {
                "back_html": "",
                "smart_grammar": {"past_participle": "offerto"},
            },
        )

        self.assertIn("past participle of 'offrire'", explanation)
        self.assertIn("not a separate verb", explanation)

    def test_duplicate_explanation_has_safe_fallback(self):
        explanation = cli.get_duplicate_form_explanation(
            "contattarci",
            "contattare",
            {"back_html": "<div><li>Origin: from contatto.</li></div>"},
        )

        self.assertIn("attached-pronoun", explanation)
        self.assertIn("contattare", explanation)

    def test_user_can_select_the_base_verb(self):
        selected = cli.choose_interpretation_cli(
            "entro",
            INTERPRETATION_OPTIONS,
            input_func=lambda _: "2",
            interactive=True,
        )

        self.assertEqual(selected["headword"], "entrare")
        self.assertEqual(selected["part_of_speech"], "verb")

    def test_user_can_cancel_without_creating_a_card(self):
        selected = cli.choose_interpretation_cli(
            "entro",
            INTERPRETATION_OPTIONS,
            input_func=lambda _: "q",
            interactive=True,
        )

        self.assertIsNone(selected)

    def test_user_can_select_all_interpretations(self):
        selected = cli.choose_interpretation_cli(
            "entro",
            INTERPRETATION_OPTIONS,
            input_func=lambda _: "a",
            interactive=True,
        )

        self.assertEqual(
            [option["headword"] for option in selected],
            ["entro", "entrare"],
        )

    def test_noninteractive_use_fails_safely(self):
        selected = cli.choose_interpretation_cli(
            "entro",
            INTERPRETATION_OPTIONS,
            interactive=False,
        )

        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
