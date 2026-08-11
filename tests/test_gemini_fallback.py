import unittest
import io
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

import httpx
from google.genai import errors

import main
from main import (
    GEMINI_MODEL_CHAIN,
    GEMINI_WORD_TIMEOUT_MS,
    generate_with_gemini_fallback,
)


class GeminiFallbackTests(unittest.TestCase):
    @staticmethod
    def _api_error(code, status):
        return errors.APIError(
            code,
            {"error": {"code": code, "status": status, "message": status}},
        )

    def test_quota_error_falls_back_to_next_model(self):
        client = Mock()
        expected = object()
        client.models.generate_content.side_effect = [
            self._api_error(429, "RESOURCE_EXHAUSTED"),
            expected,
        ]

        response, model = generate_with_gemini_fallback(
            client,
            contents="entro",
            config=object(),
        )

        self.assertIs(response, expected)
        self.assertEqual(model, GEMINI_MODEL_CHAIN[1])
        self.assertEqual(
            [call.kwargs["model"] for call in client.models.generate_content.call_args_list],
            list(GEMINI_MODEL_CHAIN[:2]),
        )

    def test_all_three_models_are_tried_for_temporary_failures(self):
        client = Mock()
        expected = object()
        client.models.generate_content.side_effect = [
            self._api_error(503, "UNAVAILABLE"),
            self._api_error(429, "RESOURCE_EXHAUSTED"),
            expected,
        ]

        response, model = generate_with_gemini_fallback(
            client,
            contents="entro",
            config=object(),
        )

        self.assertIs(response, expected)
        self.assertEqual(model, GEMINI_MODEL_CHAIN[2])

    def test_authentication_error_does_not_fall_back(self):
        client = Mock()
        client.models.generate_content.side_effect = self._api_error(
            401,
            "UNAUTHENTICATED",
        )

        with self.assertRaises(errors.APIError):
            generate_with_gemini_fallback(
                client,
                contents="entro",
                config=object(),
            )

        client.models.generate_content.assert_called_once()

    def test_timeout_falls_back_with_a_clear_message(self):
        client = Mock()
        expected = object()
        client.models.generate_content.side_effect = [
            httpx.ReadTimeout("request timed out"),
            expected,
        ]
        output = io.StringIO()

        with redirect_stdout(output):
            response, model = generate_with_gemini_fallback(
                client,
                contents="entro",
                config=object(),
            )

        self.assertIs(response, expected)
        self.assertEqual(model, GEMINI_MODEL_CHAIN[1])
        self.assertIn("did not respond in time", output.getvalue())

    def test_google_deadline_exceeded_falls_back(self):
        client = Mock()
        expected = object()
        client.models.generate_content.side_effect = [
            self._api_error(504, "DEADLINE_EXCEEDED"),
            expected,
        ]
        output = io.StringIO()

        with redirect_stdout(output):
            response, model = generate_with_gemini_fallback(
                client,
                contents="entro",
                config=object(),
            )

        self.assertIs(response, expected)
        self.assertEqual(model, GEMINI_MODEL_CHAIN[1])
        self.assertIn("did not respond in time", output.getvalue())

    def test_word_generation_client_has_a_deadline_and_no_hidden_retries(self):
        sentinel = RuntimeError("stop after client creation")

        with (
            patch.object(main.genai, "Client") as client_class,
            patch.object(
                main,
                "generate_with_gemini_fallback",
                side_effect=sentinel,
            ),
            self.assertRaisesRegex(RuntimeError, "stop after client creation"),
        ):
            main.generate_content("costarci", "Italian", "test-key")

        options = client_class.call_args.kwargs["http_options"]
        self.assertEqual(options.timeout, GEMINI_WORD_TIMEOUT_MS)
        self.assertEqual(options.retry_options.attempts, 1)


if __name__ == "__main__":
    unittest.main()
