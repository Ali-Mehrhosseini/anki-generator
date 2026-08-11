import json
import io
import os
import subprocess
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cli
import main


LESSON = {
    "title": "Un incidente ferroviario",
    "difficulty": "B1",
    "summary_en": "A young man survived a railway accident.",
    "summary_fa": "یک جوان از یک حادثه راه‌آهن جان سالم به در برد.",
    "section_explanations": [
        {
            "source_excerpt": "Un ragazzo è stato investito",
            "explanation_en": "The opening reports the accident.",
            "explanation_fa": "بخش آغازین حادثه را گزارش می‌کند.",
            "learning_focus": "News reporting and the passive voice.",
        },
    ],
    "learning_items": [
        {
            "term": "passaggio a livello",
            "card_target": "passaggio a livello",
            "kind": "expression",
            "part_of_speech": "noun",
            "meaning_en": "level crossing",
            "meaning_fa": "تقاطع هم‌سطح راه‌آهن",
            "source_excerpt": "al passaggio a livello",
            "teaching_note": "A common transport expression.",
        },
        {
            "term": "riprendere",
            "card_target": "riprendere",
            "kind": "word",
            "part_of_speech": "verb",
            "meaning_en": "to resume",
            "meaning_fa": "از سر گرفتن",
            "source_excerpt": "la circolazione è ripresa",
            "teaching_note": "Here it describes traffic starting again.",
        },
    ],
    "grammar_points": [
        {
            "pattern": "essere + participio",
            "source_excerpt": "è stato soccorso",
            "explanation_en": "This is a passive construction.",
            "explanation_fa": "این یک ساختار مجهول است.",
        },
    ],
    "comprehension_questions": [
        {
            "question_it": "Che cosa è successo?",
            "answer_en": "There was a railway accident.",
            "answer_fa": "یک حادثه راه‌آهن رخ داد.",
        },
    ],
}

LESSON["parts"] = [
    {
        "part_title": "The accident",
        "source_text": "Un ragazzo è stato investito.",
        "translation_en": "A young man was struck.",
        "translation_fa": "یک جوان مورد برخورد قرار گرفت.",
        "learning_focus": "Reporting the event",
        "learning_items": [LESSON["learning_items"][0]],
        "grammar_points": [LESSON["grammar_points"][0]],
        "comprehension_questions": [LESSON["comprehension_questions"][0]],
    },
    {
        "part_title": "Service resumes",
        "source_text": "La circolazione è ripresa.",
        "translation_en": "Traffic service resumed.",
        "translation_fa": "حرکت قطارها از سر گرفته شد.",
        "learning_focus": "Describing recovery",
        "learning_items": [LESSON["learning_items"][1]],
        "grammar_points": [LESSON["grammar_points"][0]],
        "comprehension_questions": [LESSON["comprehension_questions"][0]],
    },
]


class ReadingLessonGenerationTests(unittest.TestCase):
    def test_source_text_is_tagged_and_result_tracks_model(self):
        response = Mock(text=json.dumps(LESSON))
        with patch.object(main.genai, "Client") as client_class, patch.object(
            main,
            "generate_with_gemini_fallback",
            return_value=(response, "gemini-3.5-flash-lite"),
        ) as generate:
            result = main.generate_reading_lesson(
                "Un ragazzo è stato soccorso dopo un incidente ferroviario.",
                "Italian",
                "test-key",
            )

        client_class.assert_called_once()
        client_options = client_class.call_args.kwargs
        self.assertEqual(client_options["api_key"], "test-key")
        self.assertEqual(
            client_options["http_options"].timeout,
            main.GEMINI_TEACH_MIN_TIMEOUT_MS,
        )
        self.assertEqual(
            client_options["http_options"].retry_options.attempts,
            1,
        )
        contents = generate.call_args.kwargs["contents"]
        config = generate.call_args.kwargs["config"]
        instruction = config.system_instruction
        self.assertIn("<SOURCE_TEXT", contents)
        self.assertIn("incidente ferroviario", contents)
        self.assertIn("complete, faithful translations", instruction)
        self.assertIn("do not omit information", instruction)
        self.assertIn("parts", config.response_schema["required"])
        self.assertNotIn("learning_items", config.response_schema["required"])
        self.assertEqual(result["difficulty"], "B1")
        self.assertEqual(result["_gemini_model"], "gemini-3.5-flash-lite")

    def test_source_text_length_is_bounded(self):
        for text, message in (
            ("short", "too short"),
            ("x" * (main.MAX_READING_TEXT_CHARS + 1), "too long"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    main.generate_reading_lesson(text, "Italian", "test-key")

    def test_longer_sources_receive_broader_lesson_budgets(self):
        short = main._reading_lesson_budgets("parola " * 300)
        long = main._reading_lesson_budgets("parola " * 1_800)

        self.assertGreater(long["items"], short["items"])
        self.assertGreater(long["grammar"], short["grammar"])
        self.assertGreater(long["questions"], short["questions"])

    def test_longer_sources_receive_bounded_generation_time(self):
        self.assertEqual(
            main._reading_lesson_timeout_ms(47),
            main.GEMINI_TEACH_MIN_TIMEOUT_MS,
        )
        self.assertEqual(
            main._reading_lesson_timeout_ms(100_000),
            main.GEMINI_TEACH_MAX_TIMEOUT_MS,
        )

    def test_short_sources_get_a_compact_lesson(self):
        budgets = main._reading_lesson_budgets("parola " * 47)

        self.assertEqual(budgets["sections"], 1)
        self.assertEqual(budgets["items"], 4)
        self.assertEqual(budgets["grammar"], 2)
        self.assertEqual(budgets["questions"], 2)


class TeacherCliTests(unittest.TestCase):
    @patch.object(cli, "_render_persian_png", return_value=b"test-png")
    def test_iterm_persian_image_uses_inline_image_protocol(self, _render):
        output = io.StringIO()

        with redirect_stdout(output):
            displayed = cli._print_iterm_persian_image("متن فارسی")

        self.assertTrue(displayed)
        self.assertIn("\033]1337;File=inline=1", output.getvalue())
        self.assertIn("dGVzdC1wbmc=", output.getvalue())

    def test_terminal_lesson_wraps_dense_content_to_readable_width(self):
        lesson = json.loads(json.dumps(LESSON))
        lesson["parts"][0]["translation_en"] = "word " * 80
        output = io.StringIO()

        with patch.object(
            cli.shutil,
            "get_terminal_size",
            return_value=os.terminal_size((80, 24)),
        ), redirect_stdout(output):
            cli.print_reading_lesson(lesson)

        visible_lines = output.getvalue().splitlines()
        self.assertTrue(visible_lines)
        self.assertLessEqual(max(map(len, visible_lines)), 76)
        self.assertIn("PART 1 OF 2 · THE ACCIDENT", output.getvalue())
        self.assertIn("GRAMMAR IN THIS PART", output.getvalue())
        self.assertIn("CHECK THIS PART", output.getvalue())
        self.assertIn("\n    ENGLISH  word", output.getvalue())
        self.assertIn("\n    PERSIAN\n      ", output.getvalue())
        self.assertNotIn("\033[", output.getvalue())
        self.assertNotIn("\u2067", output.getvalue())
        self.assertNotIn("\u2069", output.getvalue())

    def test_story_parts_return_card_items_in_display_order(self):
        output = io.StringIO()

        with redirect_stdout(output):
            items = cli.print_reading_lesson(LESSON)

        self.assertEqual(
            [item["card_target"] for item in items],
            ["passaggio a livello", "riprendere"],
        )
        self.assertIn("01  passaggio a livello", output.getvalue())
        self.assertIn("02  riprendere", output.getvalue())

    def test_clipboard_reader_uses_pbpaste_without_a_shell(self):
        runner = Mock(
            return_value=SimpleNamespace(
                returncode=0,
                stdout="Un testo italiano.\n",
                stderr="",
            )
        )

        text = cli.read_clipboard_text(run_func=runner)

        self.assertEqual(text, "Un testo italiano.")
        self.assertEqual(runner.call_args.args[0], ["pbpaste"])
        self.assertNotIn("shell", runner.call_args.kwargs)

    def test_empty_clipboard_fails_before_gemini(self):
        runner = Mock(
            return_value=SimpleNamespace(returncode=0, stdout="", stderr="")
        )

        with self.assertRaisesRegex(ValueError, "clipboard is empty"):
            cli.read_clipboard_text(run_func=runner)

    def test_clipboard_timeout_has_clear_error(self):
        runner = Mock(side_effect=subprocess.TimeoutExpired("pbpaste", 5))

        with self.assertRaisesRegex(RuntimeError, "timed out"):
            cli.read_clipboard_text(run_func=runner)

    def test_numbered_selection_is_explicit_and_deduplicated(self):
        selected = cli.choose_lesson_items_cli(
            LESSON["learning_items"],
            input_func=lambda _: "2, 1, 2",
            interactive=True,
        )

        self.assertEqual(
            [item["card_target"] for item in selected],
            ["riprendere", "passaggio a livello"],
        )

    def test_q_selects_nothing(self):
        selected = cli.choose_lesson_items_cli(
            LESSON["learning_items"],
            input_func=lambda _: "q",
            interactive=True,
        )

        self.assertEqual(selected, [])

    @patch.object(cli, "add_word_to_anki")
    @patch.object(cli, "choose_lesson_items_cli", return_value=[])
    @patch.object(cli, "print_reading_lesson", return_value=LESSON["learning_items"])
    @patch.object(cli, "generate_reading_lesson", return_value=LESSON)
    @patch.object(cli, "_require_generation_keys")
    @patch.object(cli, "read_clipboard_text", return_value="Un articolo italiano abbastanza lungo.")
    def test_teacher_mode_does_not_add_cards_when_nothing_selected(
        self,
        _clipboard,
        _keys,
        _generate,
        _print,
        _choose,
        add_word,
    ):
        args = cli.build_parser().parse_args(["teach"])
        args.language = "Italian"
        args.translation = "Both (English + Persian)"

        result = cli._run_teacher_cli(args)

        self.assertEqual(result, 0)
        add_word.assert_not_called()

    @patch.object(cli, "GEMINI_API_KEY", "normal-key")
    @patch.object(cli, "GEMINI_TEACH_API_KEY", "teach-key")
    @patch.object(cli, "choose_lesson_items_cli", return_value=[])
    @patch.object(cli, "print_reading_lesson", return_value=[])
    @patch.object(cli, "generate_reading_lesson", return_value=LESSON)
    @patch.object(cli, "read_clipboard_text", return_value="Un articolo italiano abbastanza lungo.")
    def test_teacher_mode_uses_dedicated_key_for_lesson(
        self,
        _clipboard,
        generate,
        _print,
        _choose,
    ):
        args = cli.build_parser().parse_args(["teach"])
        args.language = "Italian"
        args.translation = "Both (English + Persian)"

        result = cli._run_teacher_cli(args)

        self.assertEqual(result, 0)
        self.assertEqual(generate.call_args.args[2], "teach-key")

    @patch.object(
        cli,
        "generate_reading_lesson",
        side_effect=KeyboardInterrupt,
    )
    @patch.object(cli, "_require_generation_keys")
    @patch.object(
        cli,
        "read_clipboard_text",
        return_value="Un articolo italiano abbastanza lungo.",
    )
    def test_ctrl_c_while_generating_exits_without_traceback(
        self,
        _clipboard,
        _keys,
        _generate,
    ):
        args = cli.build_parser().parse_args(["teach"])
        args.language = "Italian"
        args.translation = "Both (English + Persian)"
        output = io.StringIO()

        with redirect_stdout(output):
            result = cli._run_teacher_cli(args)

        self.assertEqual(result, 130)
        self.assertIn("Cancelled — Anki was not changed.", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    @patch.object(cli, "add_word_to_anki", return_value=True)
    @patch.object(
        cli,
        "choose_lesson_items_cli",
        return_value=[LESSON["learning_items"][1]],
    )
    @patch.object(cli, "print_reading_lesson", return_value=LESSON["learning_items"])
    @patch.object(cli, "generate_reading_lesson", return_value=LESSON)
    @patch.object(cli, "_require_generation_keys")
    @patch.object(cli, "read_clipboard_text", return_value="Un articolo italiano abbastanza lungo.")
    def test_selected_item_uses_existing_context_card_pipeline(
        self,
        _clipboard,
        _keys,
        _generate,
        _print,
        _choose,
        add_word,
    ):
        args = cli.build_parser().parse_args(["teach"])
        args.language = "Italian"
        args.translation = "Both (English + Persian)"

        result = cli._run_teacher_cli(args)

        self.assertEqual(result, 0)
        self.assertEqual(add_word.call_args.args[:2], ("riprendere", "Italian"))
        self.assertEqual(
            add_word.call_args.kwargs["usage_context"],
            "la circolazione è ripresa",
        )
        self.assertEqual(
            add_word.call_args.kwargs["gemini_api_key"],
            cli.GEMINI_TEACH_API_KEY or cli.GEMINI_API_KEY,
        )


if __name__ == "__main__":
    unittest.main()
