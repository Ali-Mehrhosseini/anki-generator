import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import cli
from main import (
    ContextCardValidationError,
    FrontCardValidationError,
    ProductionCardValidationError,
)


class ProductionRetryTests(unittest.TestCase):
    def test_cli_retries_one_inconsistent_production_sentence(self):
        expected = {"word": "scattare"}
        error = ProductionCardValidationError("sentence mismatch")

        with patch.object(
            cli,
            "generate_content",
            side_effect=[error, expected],
        ) as generate:
            output = io.StringIO()
            with redirect_stdout(output):
                result = cli._generate_content_with_production_retry(
                    "scattare",
                    "Italian",
                    "key",
                )

        self.assertIs(result, expected)
        self.assertEqual(generate.call_count, 2)
        self.assertIn("regenerating the card once", output.getvalue())

    def test_cli_stops_after_one_automatic_retry(self):
        error = ProductionCardValidationError("sentence mismatch")

        with patch.object(
            cli,
            "generate_content",
            side_effect=[error, error],
        ) as generate:
            with self.assertRaises(ProductionCardValidationError):
                cli._generate_content_with_production_retry(
                    "scattare",
                    "Italian",
                    "key",
                )

        self.assertEqual(generate.call_count, 2)

    def test_cli_retries_context_drift(self):
        expected = {"word": "scattare"}
        error = ContextCardValidationError("context drift")

        with patch.object(
            cli,
            "generate_content",
            side_effect=[error, expected],
        ) as generate:
            output = io.StringIO()
            with redirect_stdout(output):
                result = cli._generate_content_with_production_retry(
                    "scattati",
                    "Italian",
                    "key",
                    usage_context="Sono scattati i controlli.",
                )

        self.assertIs(result, expected)
        self.assertEqual(generate.call_count, 2)
        self.assertIn("drifted away", output.getvalue())

    def test_cli_retries_malformed_recognition_front(self):
        expected = {"word": "godersi"}
        error = FrontCardValidationError(
            "invalid stress marker",
            data={
                "word": "godersi",
                "front_html": "<div>go-di-ti</div>",
            },
        )

        with patch.object(
            cli,
            "generate_content",
            side_effect=[error, expected],
        ) as generate:
            output = io.StringIO()
            with redirect_stdout(output):
                result = cli._generate_content_with_production_retry(
                    "goditi",
                    "Italian",
                    "key",
                    None,
                    "Both (English + Persian)",
                )

        self.assertIs(result, expected)
        self.assertEqual(generate.call_count, 2)
        self.assertIn("recognition Front was malformed", output.getvalue())
        retry_call = generate.call_args_list[1]
        retry_prompt = retry_call.kwargs.get("custom_prompt")
        if retry_prompt is None and len(retry_call.args) > 3:
            retry_prompt = retry_call.args[3]
        self.assertIsNotNone(retry_prompt)
        self.assertIn('Canonical lemma from your previous response: "godersi"', retry_prompt)
        self.assertIn('Rejected visible Front: "go-di-ti"', retry_prompt)
        self.assertIn("Never insert a hyphen", retry_prompt)


if __name__ == "__main__":
    unittest.main()
