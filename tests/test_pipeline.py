import unittest

from backend.pipeline import pipeline


class PipelineTest(unittest.TestCase):
    def test_split_sentences(self):
        self.assertEqual(
            pipeline.split_sentences("We read. They listen!"),
            ["We read.", "They listen!"],
        )

    def test_process_text_shape(self):
        result = pipeline.process_text("We read the text.", "unit")
        self.assertEqual(result["schema_version"], "0.1.0")
        self.assertEqual(len(result["sentences"]), 1)
        self.assertGreater(len(result["sentences"][0]["words"]), 0)
        first_word = result["sentences"][0]["words"][0]
        self.assertIn("ipa", first_word)
        self.assertIn("zhuyin_plus", first_word["display"])

    def test_display_for_ipa(self):
        result = pipeline.display_for_ipa(["ɹ", "i", "d"], word_text="read")
        self.assertEqual(result["ipa"], ["ɹ", "i", "d"])
        self.assertIn("zhuyin_plus", result["display"])
        self.assertEqual(len(result["token_details"]), 3)

    def test_display_table_available(self):
        table = pipeline.get_display_table()
        self.assertIn("p", table)
        self.assertEqual(table["p"]["ipa"], "p")
        self.assertTrue(table["p"]["zhuyin_plus"])


if __name__ == "__main__":
    unittest.main()
