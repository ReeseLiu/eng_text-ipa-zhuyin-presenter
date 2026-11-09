import unittest
import re

from backend.pipeline import pipeline
import backend.pipeline as pipeline_module


class PipelineTest(unittest.TestCase):
    def test_split_sentences(self):
        self.assertEqual(
            pipeline.split_sentences("We read. They listen!"),
            ["We read.", "They listen!"],
        )

    def test_split_sentences_treats_newline_as_boundary(self):
        self.assertEqual(
            pipeline.split_sentences("first line\nsecond line\nthird line"),
            ["first line", "second line", "third line"],
        )

    def test_split_sentences_mixed_punctuation_and_newline(self):
        self.assertEqual(
            pipeline.split_sentences("first line.\nsecond line\nthird line!"),
            ["first line.", "second line", "third line!"],
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
        self.assertRegex(sentence["sentenceId"], r"^sen_[0-9a-f]{24}$")
        self.assertIn("words", sentence)
        self.assertEqual(sentence["sentence"], "I'm here.")

        first_token = sentence["words"][0][0]
        self.assertEqual(first_token["text"], "I'm")
        self.assertEqual(first_token["phonetic"], [51, 7])
        self.assertIsNone(first_token["toneLevel"])
        self.assertIsNone(first_token["toneStyle"])
        self.assertIsNone(first_token["importance"])
        self.assertEqual(first_token["kkPhonetic"], "")
        self.assertTrue(str(first_token["tokenId"]).startswith("tok_"))
        self.assertEqual(first_token["reason"], "")

    def test_export_json_sentence_ids_do_not_repeat(self):
        payload = pipeline.process_text("One. Two.", "unit")
        first = [sentence["sentenceId"] for sentence in pipeline.export_json(payload)]
        second = [sentence["sentenceId"] for sentence in pipeline.export_json(payload)]
        self.assertEqual(len(set(first + second)), 4)

    def test_export_json_flattens_multi_consonant_slots(self):
        payload = pipeline.process_text("break chance and.", "unit")
        exported = pipeline.export_json(payload)
        words = exported[0]["words"]

        break_token = words[0][0]
        self.assertEqual(break_token["text"], "break")
        self.assertEqual(break_token["phonetic"], [1, 81, 48, 25])

        chance_token = words[1][0]
        self.assertEqual(chance_token["text"], "chance")
        self.assertEqual(chance_token["phonetic"], [30, 49, 18, 38])

        # Matches the intonation site's own export of "and".
        and_token = words[2][0]
        self.assertEqual(and_token["phonetic"], [44, 18, 16])

    def test_export_json_flattens_composite_slot_after_merge(self):
        payload = pipeline.process_text("dream.", "unit")
        exported = pipeline.export_json(payload)
        token = exported[0]["words"][0][0]
        self.assertEqual(token["text"], "dream.")
        self.assertEqual(token["phonetic"], [79, 66, 7])

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
        self.assertEqual([token["text"] for token in word_group], ["ba", "na", "na."])
        self.assertEqual(word_group[0]["phonetic"], [1, 44])
        self.assertEqual(word_group[1]["phonetic"], [12, 49])
        self.assertEqual(word_group[2]["phonetic"], [12, 44])

    def test_export_json_prefers_manual_syllables_with_text_split(self):
        payload = pipeline.process_text("sometimes.", "unit")
        word = payload["sentences"][0]["words"][0]
        word["manual_syllables"] = [
            {
                "text": "some",
                "slots": {
                    "C1": ["ㄙ"],
                    "V": ["ㄜ"],
                    "C2": ["ㄇ~"],
                },
            },
            {
                "text": "times.",
                "slots": {
                    "C1": ["ㄊ(摩)"],
                    "V": ["ㄞ"],
                    "C2": ["ㄇ~", "z"],
                },
            },
        ]

        exported = pipeline.export_json(payload)
        word_group = exported[0]["words"][0]
        self.assertEqual(len(word_group), 2)
        self.assertEqual(word_group[0]["text"], "some")
        self.assertEqual(word_group[1]["text"], "times.")
        self.assertEqual(word_group[0]["phonetic"], [38, 44, 7])
        self.assertEqual(word_group[1]["phonetic"], [15, 51, 7, 39])

    def test_export_json_manual_syllables_parse_comma_delimited_slot_text(self):
        payload = pipeline.process_text("sometimes.", "unit")
        word = payload["sentences"][0]["words"][0]
        word["manual_syllables"] = [
            {
                "text": "some",
                "slots": {
                    "C1": "ㄙ",
                    "V": "ㄜ",
                    "C2": "ㄇ~",
                },
            },
            {
                "text": "times.",
                "slots": {
                    "C1": "ㄊ(摩)",
                    "V": "ㄞ",
                    "C2": "ㄇ~, z",
                },
            },
        ]

        exported = pipeline.export_json(payload)
        word_group = exported[0]["words"][0]
        self.assertEqual(len(word_group), 2)
        self.assertEqual(word_group[0]["text"], "some")
        self.assertEqual(word_group[1]["text"], "times.")
        self.assertEqual(word_group[0]["phonetic"], [38, 44, 7])
        self.assertEqual(word_group[1]["phonetic"], [15, 51, 7, 39])

    def test_export_json_splits_capitalized_word_by_suggestion(self):
        payload = pipeline.process_text("Henry and Mudge", "unit")
        words = pipeline.export_json(payload)[0]["words"]
        self.assertEqual([token["text"] for token in words[0]], ["Hen", "ry"])
        self.assertEqual([token["phonetic"] for token in words[0]], [[23, 45, 18], [81, 66]])

    def test_export_json_keeps_unsplit_text_without_suggestion(self):
        exported = pipeline_module.export_payload_to_jason(
            pipeline.process_text("banana.", "unit"),
            pipeline.phonetic_number_map,
            pipeline.phonetic_number_symbols,
        )
        self.assertEqual([token["text"] for token in exported[0]["words"][0]], ["banana.", "", ""])

    def test_export_json_known_word_split_and_metadata(self):
        payload = pipeline.process_text("headquarters,", "unit")
        exported = pipeline.export_json(payload)
        word_group = exported[0]["words"][0]

        self.assertEqual(len(word_group), 3)
        self.assertEqual([token["text"] for token in word_group], ["head", "quar", "ters,"])
        # /kw/ is a legal onset, so /k/ opens "quar" instead of closing "head".
        self.assertEqual(word_group[0]["phonetic"], [23, 45, 16])
        self.assertEqual(word_group[1]["phonetic"], [22, 60, 71])
        self.assertEqual(word_group[2]["phonetic"], [15, 47, 39])
        self.assertEqual({token["kkPhonetic"] for token in word_group}, {""})
        self.assertIsNone(word_group[0]["toneStyle"])
        self.assertIsNone(word_group[1]["toneLevel"])
        self.assertIsNone(word_group[2]["importance"])
        self.assertTrue(str(word_group[0]["tokenId"]).startswith("tok_"))

    def test_export_json_matches_strict_override_sentence(self):
        sentence_text = pipeline_module.STRICT_SAMPLE_SENTENCE
        payload = pipeline.process_text(sentence_text, "unit")
        exported = pipeline.export_json(payload)
        sentence = exported[0]

        self.assertEqual(sentence["sentenceId"], "sen_52f04437f93f6e679dd1828e")
        self.assertEqual(sentence["sentence"], sentence_text)

        surfaces = re.findall(r"[A-Za-z0-9']+(?:[.,!?;:…]+)?|[^\s]", sentence_text)
        self.assertEqual(len(sentence["words"]), len(surfaces))

        for idx, surface in enumerate(surfaces):
            if surface not in pipeline_module.JASON_STRICT_SURFACE_OVERRIDES:
                continue
            override = pipeline_module.JASON_STRICT_SURFACE_OVERRIDES[surface]
            expected_tokens = override["tokens"]
            group = sentence["words"][idx]

            self.assertEqual(len(group), len(expected_tokens))
            for token_idx, expected in enumerate(expected_tokens):
                token = group[token_idx]
                self.assertEqual(token["text"], expected["text"])
                self.assertEqual(token["phonetic"], expected["phonetic"])
                self.assertEqual(token["tokenId"], expected["tokenId"])
                self.assertEqual(token["kkPhonetic"], override["kkPhonetic"])
                self.assertEqual(token["partOfSpeech"], override["partOfSpeech"])
                self.assertEqual(token["toneLevel"], 0)
                self.assertEqual(token["toneStyle"], "solid-short")
                self.assertEqual(token["importance"], "important" if token["phonetic"] else "not-important")


if __name__ == "__main__":
    unittest.main()
