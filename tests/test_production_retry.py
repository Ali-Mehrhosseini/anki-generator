import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import cli
from main import ContextCardValidationError, ProductionCardValidationError


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


if __name__ == "__main__":
    unittest.main()
