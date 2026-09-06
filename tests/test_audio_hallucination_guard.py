import unittest
from unittest.mock import patch
from io import BytesIO

import app as flask_app
from learning_lab import transcript_plausibility_problem


class PlausibilityGateTests(unittest.TestCase):
    def test_short_clip_cannot_contain_full_model_sentence(self):
        problem = transcript_plausibility_problem(
            "considero questa scelta corretta domani",
            {"voice_ratio": 0.17},
            3.0,
        )
        self.assertIn("not graded", problem)

    def test_real_sentence_with_enough_voice_passes(self):
        self.assertEqual(
            transcript_plausibility_problem(
                "considero questa scelta corretta domani",
                {"voice_ratio": 0.8},
                3.0,
            ),
            "",
        )

    def test_silent_clip_with_no_transcript_passes(self):
        self.assertEqual(
            transcript_plausibility_problem("", {"voice_ratio": 0.0}, 3.0),
            "",
        )

    def test_missing_fluency_falls_back_to_duration(self):
        self.assertEqual(
            transcript_plausibility_problem("ciao", None, 5.0),
            "",
        )

    def test_no_measured_duration_means_no_veto(self):
        # Without any measurement the gate stays out of the way; the real
        # client always reports one.
        self.assertEqual(
            transcript_plausibility_problem("ciao", None, None),
            "",
        )


class HallucinatedTranscriptRouteTests(unittest.TestCase):
    def setUp(self):
        flask_app.app.config["TESTING"] = True
        self.client = flask_app.app.test_client()

    def test_deep_word_help_route_returns_usage_context_without_recording(self):
        deep = {
            "usage_en": "Ritenere is the standard verb for 'to consider' in opinions.",
            "usage_fa": "برای بیان نظر، ritenere فعل استاندارد است.",
            "form_it": "ritengo",
            "form_en": "First person singular present: 'I consider'.",
            "form_fa": "شخص اول مفرد زمان حال: «من می‌پندارم».",
            "note_en": "In opinions, Italian often drops the subject pronoun.",
            "note_fa": "در جملات نظر، ایتالیایی‌ها معمولاً ضمیر فاعل را حذف می‌کنند.",
        }
        with patch.object(flask_app, "generate_word_usage_help", return_value=deep) as deep_help, \
                patch.object(flask_app, "record_word_help") as record:
            response = self.client.post(
                "/api/learning-lab/word-help",
                json={
                    "word": "consider",
                    "deep": True,
                    "lemma": "ritenere",
                    "context": "I consider this choice to be correct.",
                    "startingIt": "Io ritengo che...",
                    "geminiKey": "test",
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), deep)
            self.assertEqual(deep_help.call_args.args[0], "consider")
            self.assertEqual(deep_help.call_args.args[1], "ritenere")
            record.assert_not_called()

    def test_text_route_refuses_implausible_transcript_without_grading(self):
        with patch.object(flask_app, "generate_practice_feedback") as grade, \
                patch.object(flask_app, "record_session") as record:
            response = self.client.post(
                "/api/learning-lab/feedback",
                json={
                    "targets": [{"word": "ritenere"}],
                    "task": {"task_type": "translation"},
                    # Six words "recognized" from under a second of voice.
                    "response": "io ritengo che questa scelta sia corretta",
                    "durationSeconds": 2.0,
                    "fluency": {"voice_ratio": 0.2},
                    "geminiKey": "test",
                    "mode": "voice",
                },
            )

            data = response.get_json()
            self.assertEqual(response.status_code, 200)
            self.assertTrue(data["not_graded"])
            self.assertFalse(data["evaluation_reliable"])
            grade.assert_not_called()
            record.assert_not_called()

    def test_text_route_grades_plausible_response(self):
        with patch.object(flask_app, "generate_practice_feedback") as grade, \
                patch.object(flask_app, "record_session") as record, \
                patch.object(flask_app, "save_state"):
            grade.return_value = {"correct": True}
            response = self.client.post(
                "/api/learning-lab/feedback",
                json={
                    "targets": [{"word": "ritenere"}],
                    "task": {"task_type": "translation"},
                    "response": "io ritengo che questa scelta sia corretta",
                    "durationSeconds": 4.0,
                    "fluency": {"voice_ratio": 0.8},
                    "geminiKey": "test",
                    "mode": "voice",
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {"correct": True})
            grade.assert_called_once()
            record.assert_called_once()

    def test_audio_route_refuses_hallucinated_transcription_without_recording(self):
        with patch.object(flask_app, "generate_practice_audio_feedback") as grade, \
                patch.object(flask_app, "record_session") as record:
            grade.return_value = {
                "transcript_it": "io ritengo che questa scelta sia corretta",
                "correct": True,
            }
            response = self.client.post(
                "/api/learning-lab/audio-feedback",
                data={
                    "audio": (BytesIO(b"fake-audio"), "practice.webm"),
                    "geminiKey": "test",
                    "context": (
                        '{"targets": [{"word": "ritenere"}], "task": {}, '
                        '"durationSeconds": 2.0, '
                        '"fluency": {"voice_ratio": 0.2}}'
                    ),
                },
                content_type="multipart/form-data",
            )

            data = response.get_json()
            self.assertEqual(response.status_code, 200)
            self.assertTrue(data["not_graded"])
            self.assertFalse(data["evaluation_reliable"])
            self.assertEqual(
                data["transcript_it"],
                "io ritengo che questa scelta sia corretta",
            )
            record.assert_not_called()

    def test_audio_route_records_plausible_attempt(self):
        with patch.object(flask_app, "generate_practice_audio_feedback") as grade, \
                patch.object(flask_app, "record_session") as record, \
                patch.object(flask_app, "load_state"), \
                patch.object(flask_app, "save_state"):
            grade.return_value = {
                "transcript_it": "io ritengo che questa scelta sia corretta",
                "correct": True,
            }
            response = self.client.post(
                "/api/learning-lab/audio-feedback",
                data={
                    "audio": (BytesIO(b"fake-audio"), "practice.webm"),
                    "geminiKey": "test",
                    "context": (
                        '{"targets": [{"word": "ritenere"}], "task": {}, '
                        '"durationSeconds": 4.0, '
                        '"fluency": {"voice_ratio": 0.8}}'
                    ),
                },
                content_type="multipart/form-data",
            )

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()["correct"])
            record.assert_called_once()


if __name__ == "__main__":
    unittest.main()
