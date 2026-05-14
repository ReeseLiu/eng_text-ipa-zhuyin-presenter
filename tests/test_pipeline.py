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

    def test_export_json_returns_jason_shape(self):
        payload = pipeline.process_text("I'm here.", "unit")
        exported = pipeline.export_json(payload)
        self.assertIsInstance(exported, list)
        self.assertEqual(len(exported), 1)

        sentence = exported[0]
        self.assertIn("sentenceId", sentence)
        self.assertIn("words", sentence)
        self.assertEqual(sentence["sentence"], "I'm here.")

        first_token = sentence["words"][0][0]
        self.assertEqual(first_token["text"], "I'm")
        self.assertEqual(first_token["phonetic"], [51, 7])
        self.assertIsNone(first_token["toneLevel"])
        self.assertEqual(first_token["reason"], "")

    def test_export_json_wraps_multi_consonant_slots(self):
        payload = pipeline.process_text("break chance.", "unit")
        exported = pipeline.export_json(payload)
        words = exported[0]["words"]

        break_token = words[0][0]
        self.assertEqual(break_token["text"], "break")
        self.assertEqual(break_token["phonetic"], [[1, 81], 48, 25])

        chance_token = words[1][0]
        self.assertEqual(chance_token["text"], "chance.")
        self.assertEqual(chance_token["phonetic"], [30, 49, [18, 38]])

    def test_export_json_wraps_composite_slot_after_merge(self):
        payload = pipeline.process_text("dream.", "unit")
        exported = pipeline.export_json(payload)
        token = exported[0]["words"][0][0]
        self.assertEqual(token["text"], "dream.")
        self.assertEqual(token["phonetic"], [[79], 66, 7])

    def test_missing_word_record_has_syllable_guess(self):
        word = pipeline._record_to_word(
            {
                "word": "blorptastic",
                "word_norm": "blorptastic",
                "canonical_ipa": [],
                "canonical_stress_levels": [],
                "g2p_source": "missing",
            },
            1,
        )
        self.assertEqual(word["g2p_source"], "missing")
        self.assertIn("syllable_count_guess", word)
        self.assertGreaterEqual(word["syllable_count_guess"], 1)

    def test_export_json_uses_manual_syllable_count_when_details_missing(self):
        payload = {
            "sentences": [
                {
                    "sentence_id": "1",
                    "text": "blorp",
                    "words": [
                        {
                            "word": "blorp",
                            "g2p_source": "missing",
                            "ipa": [],
                            "display": {"zhuyin_plus": ["ㄅ", "ㄌ", "ㄛ", "ㄆ"]},
                            "token_details": [],
                            "manual_syllable_count": 2,
                        }
                    ],
                }
            ]
        }

        exported = pipeline.export_json(payload)
        word_group = exported[0]["words"][0]
        self.assertEqual(len(word_group), 2)
        self.assertEqual(word_group[0]["text"], "blorp")
        self.assertEqual(word_group[0]["phonetic"], [1, 13])
        self.assertEqual(word_group[1]["text"], "")
        self.assertEqual(word_group[1]["phonetic"], [43, 2])

    def test_export_json_splits_multisyllable_word_into_parallel_tokens(self):
        payload = pipeline.process_text("banana.", "unit")
        exported = pipeline.export_json(payload)
        word_group = exported[0]["words"][0]

        self.assertEqual(len(word_group), 3)
        self.assertEqual(word_group[0]["text"], "banana.")
        self.assertEqual(word_group[1]["text"], "")
        self.assertEqual(word_group[2]["text"], "")
        self.assertEqual(word_group[0]["phonetic"], [1, 44])
        self.assertEqual(word_group[1]["phonetic"], [12, 49])
        self.assertEqual(word_group[2]["phonetic"], [12, 44])


if __name__ == "__main__":
    unittest.main()
