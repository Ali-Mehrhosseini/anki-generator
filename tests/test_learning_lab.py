import os
import io
import unittest
from unittest.mock import patch

import app as web_app
from learning_lab import (
    SPEAKING_SPRINT_CONFIG,
    _italian_scaffold,
    _translation_task,
    default_state,
    record_session,
    select_targets,
)


class LearningLabVoiceTests(unittest.TestCase):
    def test_default_state_and_sprint_require_spoken_output(self):
        state = default_state()

        self.assertEqual(state["speaking_seconds"], 0)
        self.assertEqual(SPEAKING_SPRINT_CONFIG["rounds"], 3)
        self.assertEqual(SPEAKING_SPRINT_CONFIG["minimum_seconds"], 0)
        self.assertEqual(SPEAKING_SPRINT_CONFIG["minimum_words"], 2)
        self.assertEqual(SPEAKING_SPRINT_CONFIG["max_feedback_attempts"], 2)

    def test_voice_attempt_records_metadata_without_audio(self):
        state = default_state()
        result = record_session(
            state,
            [{"word": "distruggere"}],
            response="Il vento ha distrutto tutto.",
            feedback={"retry_needed": False},
            mode="voice",
            duration_seconds=12.34,
            attempt=2,
            round_number=3,
        )

        self.assertEqual(result["mode"], "voice")
        self.assertEqual(result["duration_seconds"], 12.3)
        self.assertEqual(result["attempt"], 2)
        self.assertEqual(result["round"], 3)
        self.assertEqual(state["speaking_seconds"], 12.3)
        self.assertNotIn("audio", result)

    def test_translation_task_uses_one_english_sentence(self):
        task = _translation_task({
            "word": "intanto",
            "example_en": "Meanwhile, I clean the kitchen.",
            "example_it": "Tu fai la spesa, io intanto pulisco la cucina.",
        }, 1)

        self.assertEqual(task["prompt_en"], "Meanwhile, I clean the kitchen.")
        self.assertEqual(task["source_en"], task["prompt_en"])
        self.assertEqual(task["target_words"], ["intanto"])
        self.assertEqual(task["task_type"], "translation")
        self.assertEqual(task["response_mode"], "voice")
        self.assertEqual(task["hint_it"], "Tu fai la …")
        self.assertTrue(task["hint_visible"])

    def test_ladder_removes_automatic_hint_after_guided_round(self):
        target = {
            "word": "intanto",
            "example_en": "Meanwhile, I clean.",
            "example_it": "Io intanto pulisco la cucina.",
        }
        self.assertTrue(_translation_task(target, 1)["hint_visible"])
        self.assertFalse(_translation_task(target, 2)["hint_visible"])
        self.assertFalse(_translation_task(target, 3)["hint_visible"])
        self.assertEqual(_italian_scaffold("Intanto pulisco.", "intanto"), "Intanto …")

    def test_sentence_change_excludes_already_seen_words(self):
        candidates = [
            {"word": "mentre", "identity": "mentre", "example_it": "A", "example_en": "A", "weakness": 2},
            {"word": "intanto", "identity": "intanto", "example_it": "B", "example_en": "B", "weakness": 1},
        ]
        with patch(
            "learning_lab.discover_practice_candidates", return_value=candidates,
        ), patch(
            "learning_lab.select_practice_targets",
            side_effect=lambda items, state, count: items[:count],
        ):
            selected = select_targets(
                lambda *_args, **_kwargs: [],
                default_state(),
                "Italian Vocab",
                "AG Production Recall v1",
                exclude_words=["mentre"],
            )

        self.assertEqual([item["word"] for item in selected], ["intanto"])

    def test_failed_words_enter_and_leave_the_repair_queue(self):
        state = default_state()
        target = [{"word": "intanto"}]
        record_session(
            state, target, response="...",
            feedback={"target_results": [{"word": "intanto", "correct": False}]},
        )
        self.assertEqual(state["trouble_words"]["intanto"]["misses"], 1)
        record_session(
            state, target, response="Intanto pulisco.",
            feedback={"target_results": [{"word": "intanto", "correct": True}]},
        )
        self.assertNotIn("intanto", state["trouble_words"])

    def test_new_grammar_pattern_exposure_is_remembered(self):
        state = default_state()
        record_session(
            state,
            [{"word": "ritenere"}],
            response="Ritengo che sia utile.",
            feedback={
                "target_results": [{"word": "ritenere", "correct": True}],
                "new_pattern": {
                    "detected": True,
                    "key": "congiuntivo_dopo_opinione",
                    "label_it": "ritenere che + congiuntivo",
                },
            },
        )

        saved = state["grammar_patterns"]["congiuntivo_dopo_opinione"]
        self.assertEqual(saved["exposures"], 1)
        self.assertEqual(saved["label_it"], "ritenere che + congiuntivo")

    def test_invalid_client_metadata_is_safely_bounded(self):
        state = default_state()
        result = record_session(
            state,
            [],
            response="Parlo.",
            feedback={},
            mode="unexpected",
            duration_seconds=99_999,
            attempt=-2,
            round_number="bad",
        )

        self.assertEqual(result["mode"], "text")
        self.assertEqual(result["duration_seconds"], 300)
        self.assertEqual(result["attempt"], 1)
        self.assertEqual(result["round"], 1)
        self.assertEqual(state["speaking_seconds"], 0)

    def test_feedback_route_falls_back_to_project_gemini_key(self):
        feedback = {"retry_needed": False, "target_results": []}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "server-key"}), patch.object(
            web_app,
            "load_state",
            return_value=default_state(),
        ), patch.object(
            web_app,
            "generate_practice_feedback",
            return_value=feedback,
        ) as generate, patch.object(
            web_app,
            "record_session",
        ), patch.object(
            web_app,
            "save_state",
        ):
            response = web_app.app.test_client().post(
                "/api/learning-lab/feedback",
                json={
                    "targets": [{"word": "parlare"}],
                    "task": {"title": "Speak"},
                    "response": "Parlo in italiano.",
                    "mode": "voice",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(generate.call_args.args[3], "server-key")
        self.assertEqual(generate.call_args.kwargs["response_mode"], "voice")

    def test_transcription_route_uses_temporary_audio_and_server_key(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "server-key"}), patch.object(
            web_app,
            "transcribe_practice_audio",
            return_value="Parlo in italiano.",
        ) as transcribe:
            response = web_app.app.test_client().post(
                "/api/learning-lab/transcribe",
                data={"audio": (io.BytesIO(b"short-audio"), "practice.webm")},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["transcript"], "Parlo in italiano.")
        self.assertEqual(transcribe.call_args.args[0], b"short-audio")
        self.assertEqual(transcribe.call_args.args[2], "server-key")

    def test_audio_feedback_route_records_the_combined_result(self):
        feedback = {
            "transcript_it": "Parlo in italiano.",
            "retry_needed": False,
            "target_results": [{"word": "parlare", "correct": True}],
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "server-key"}), patch.object(
            web_app, "generate_practice_audio_feedback", return_value=feedback,
        ), patch.object(web_app, "load_state", return_value=default_state()), patch.object(
            web_app, "save_state",
        ) as save:
            response = web_app.app.test_client().post(
                "/api/learning-lab/audio-feedback",
                data={
                    "audio": (io.BytesIO(b"short-audio"), "practice.webm"),
                    "context": '{"targets":[{"word":"parlare"}],"task":{}}',
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["transcript_it"], "Parlo in italiano.")
        save.assert_called_once()

    def test_polly_route_returns_correct_sentence_audio(self):
        with patch.dict(os.environ, {
            "AWS_ACCESS_KEY": "server-access",
            "AWS_SECRET_KEY": "server-secret",
        }), patch.object(
            web_app, "generate_audio", return_value=b"mp3-audio",
        ) as generate:
            response = web_app.app.test_client().post(
                "/api/learning-lab/polly",
                json={"sentence": "Io studio mentre tu cucini."},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "audio/mpeg")
        self.assertEqual(response.data, b"mp3-audio")
        generate.assert_called_once_with(
            "Io studio mentre tu cucini.",
            "Beatrice",
            "it-IT",
            "server-access",
            "server-secret",
            engine="generative",
        )


if __name__ == "__main__":
    unittest.main()
