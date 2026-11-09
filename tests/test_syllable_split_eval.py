import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_eval():
    spec = importlib.util.spec_from_file_location("eval_syllable_split", ROOT / "scripts" / "eval_syllable_split.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyllableSplitEvalTest(unittest.TestCase):
    """Fast subset: gold sources only plus one tiny text; no table rebuild."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_eval()
        # "synapse" keeps a missing_gold text item: its only CMUdict IPA (s ɪ æ p s) drops the n, so it is unlikely ever to get gold.
        cls.report = cls.module.evaluate(texts=["The story was read aloud by a synapse."])

    def test_counts_add_up(self):
        overall = self.report["overall"]
        self.assertEqual(
            overall["items"],
            overall["exact"]
            + overall["mismatch"]["total"]
            + overall["no_suggestion"]["total"]
            + overall["missing_gold"]
            + overall["gold_conflict"]
            + overall["not_applicable"]["total"],
        )
        self.assertEqual(overall["items"], len(self.report["items"]))
        self.assertEqual(
            overall["no_suggestion"]["total"],
            sum(n for code, n in overall["no_suggestion"].items() if code != "total"),
        )

    def test_fixture_golds_match_exactly(self):
        fixture = self.report["by_source"]["fixture"]
        self.assertGreater(fixture["items"], 0)
        self.assertEqual(fixture["exact"], fixture["items"])

    def test_curated_gold_exercises_failure_codes(self):
        no_suggestion = self.report["by_source"]["curated"]["no_suggestion"]
        for code in ("low_confidence", "cut_inside_chunk", "no_alignment"):
            self.assertGreaterEqual(no_suggestion[code], 1, code)

    def test_gold_is_consistent(self):
        self.assertEqual(self.report["gold_conflicts"], {"resolved_by_review": 0, "unresolved": 0})
        for item in self.report["items"]:
            if item["gold"] is not None:
                self.assertEqual("".join(item["gold"]), item["word"], item["word"])
            if item["outcome"] == "exact":
                self.assertEqual(item["suggestion"], item["gold"])

    def test_invalid_gold_is_reported_not_scored(self):
        invalid = self.report["invalid_gold"]
        self.assertNotIn("curated", {bad["source"] for bad in invalid})
        # A word can have an invalid entry in one source and a valid one in another (e.g. wherever);
        # only an item that still carries the invalid source must be unscored.
        for bad in invalid:
            for item in self.report["items"]:
                if item["word"] == bad["word"] and bad["source"] in item["sources"]:
                    self.assertIsNone(item["gold"], item["word"])

    def test_text_words_without_gold_are_missing_gold(self):
        text_items = [item for item in self.report["items"] if item["sources"] == ["text"]]
        self.assertTrue(any(item["outcome"] == "missing_gold" for item in text_items))
        self.assertTrue(all(item["gold"] is None for item in text_items))

    def test_contract_and_candidate_sources_do_not_count_as_reviewed(self):
        # Reviewed gold comes only from reviewed curated entries; the tiers partition all gold.
        self.assertGreater(self.report["gold_reviewed"], 0)
        self.assertEqual(self.report["gold_reviewed"] + self.report["gold_candidate"], self.report["gold_items"])
        self.assertEqual(self.report["by_tier"]["reviewed"]["items"], self.report["gold_reviewed"])
        for item in self.report["items"]:
            if item["reviewed"]:
                self.assertEqual(set(item["sources"]), {"curated"}, item["word"])
            if "fixture" in item["sources"] or "known_word_table" in item["sources"]:
                self.assertFalse(item["reviewed"], item["word"])
        # Contract fixtures are still scored, just in the candidate tier.
        self.assertEqual(
            self.report["by_tier"]["reviewed"]["exact"] + self.report["by_tier"]["candidate"]["exact"],
            self.report["overall"]["exact"],
        )

    def test_cli_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(self.module.main(["--out", str(out)]), 0)
            self.assertIn("exact:", stdout.getvalue())
            report = json.loads(out.read_text(encoding="utf-8"))
            # Pinned literally: bumping the report format must be a deliberate test change too.
            self.assertEqual(report["report_version"], 3)
            required = {
                "report_version", "align_table", "gold_items", "gold_reviewed", "gold_candidate", "gold_conflicts",
                "invalid_gold", "stale_reviewed", "ipa_source_human", "rates", "reviewed_rates_by_stratum",
                "overall", "by_tier", "reviewed_by_stratum", "by_source", "items",
            }
            self.assertLessEqual(required, set(report))
            self.assertEqual(set(report["rates"]), {"reviewed", "candidate", "all_gold"})
            for rates in report["rates"].values():
                self.assertEqual(set(rates), {"compared", "with_gold", "exact_rate_when_suggested", "suggestion_rate_on_gold"})
            self.assertEqual(set(report["gold_conflicts"]), {"resolved_by_review", "unresolved"})


def counts(module, exact=0, mismatch=0, no_suggestion=0, multi=0, single=0):
    c = module._empty_counts()
    c["exact"] = exact
    c["mismatch"]["total"] = mismatch
    c["no_suggestion"]["total"] = no_suggestion
    c["not_applicable"]["gold_multi_segment"] = multi
    c["not_applicable"]["gold_single_segment"] = single
    return c


def syllables(n):
    """An IPA with n syllables, so synthetic golds pass the segment-count legality rule."""
    return ["ɑ"] + ["b", "ɑ"] * (n - 1)


def raw(word, gold, label, source="curated", ipa=None):
    return {"word": word, "ipa": list(ipa) if ipa is not None else syllables(len(gold)), "gold": gold, "source": source, "label": label}


def reviewed_entry(module, word, ipa, segments, **extra):
    return {"id": word, "word": word, "ipa": ipa, "segments": segments, "reviewed": True,
            "reviewed_fingerprint": module.batch_gold.reviewed_fingerprint(word, ipa, segments), **extra}


class GoldSemanticsTest(unittest.TestCase):
    """Pure helpers plus small curated files; explicit IPA keeps the merge offline."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_eval()

    def test_rate_denominators_and_rounding(self):
        rates = self.module.compute_rates(counts(self.module, exact=2, mismatch=1, no_suggestion=1, multi=1, single=4))
        self.assertEqual(rates["compared"], 3)
        self.assertEqual(rates["with_gold"], 5)  # single-segment not_applicable agrees with gold and stays out
        self.assertEqual(rates["exact_rate_when_suggested"], 0.6667)
        self.assertEqual(rates["suggestion_rate_on_gold"], 0.6)
        self.assertEqual(self.module.compute_rates(counts(self.module, exact=1, mismatch=2))["exact_rate_when_suggested"], 0.3333)

    def test_rates_are_null_on_empty_denominators(self):
        rates = self.module.compute_rates(counts(self.module, single=3))
        self.assertEqual((rates["compared"], rates["with_gold"]), (0, 0))
        self.assertIsNone(rates["exact_rate_when_suggested"])
        self.assertIsNone(rates["suggestion_rate_on_gold"])
        rates = self.module.compute_rates(counts(self.module, no_suggestion=2))
        self.assertIsNone(rates["exact_rate_when_suggested"])
        self.assertEqual(rates["suggestion_rate_on_gold"], 0.0)

    def test_not_applicable_is_split_by_gold(self):
        na = {"status": "not_applicable", "code": None, "segments": []}
        self.assertEqual(self.module.classify(na, None), ("not_applicable", "no_gold"))
        self.assertEqual(self.module.classify(na, ["cat"]), ("not_applicable", "gold_single_segment"))
        self.assertEqual(self.module.classify(na, ["c", "at"]), ("not_applicable", "gold_multi_segment"))
        self.assertEqual(self.module.classify(na, ["c", "at"], conflicted=True), ("gold_conflict", None))

    def test_agreeing_sources_merge_without_conflict(self):
        rows, _ = self.module.merge_gold(
            None, [raw("ab", ["a", "b"], "candidate", "known_word_table"), raw("ab", ["a", "b"], "reviewed")]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["gold"], ["a", "b"])
        self.assertTrue(rows[0]["reviewed"])
        self.assertEqual(rows[0]["labels"], ["candidate", "reviewed"])
        self.assertIsNone(rows[0]["conflict"])

    def test_single_reviewed_split_wins_a_conflict(self):
        for order in (1, -1):
            sources = [raw("abc", ["a", "bc"], "contract", "fixture"), raw("abc", ["ab", "c"], "reviewed")][::order]
            (row,), _ = self.module.merge_gold(None, sources)
            self.assertEqual(row["gold"], ["ab", "c"])
            self.assertTrue(row["reviewed"])
            self.assertEqual(row["conflict"]["resolution"], "reviewed")
            self.assertEqual(len(row["conflict"]["golds"]), 2)

    def test_conflict_without_a_single_reviewed_split_is_unresolved(self):
        cases = {
            "candidates": [raw("abc", ["a", "bc"], "candidate", "known_word_table"), raw("abc", ["ab", "c"], "contract", "fixture")],
            "reviewed": [raw("abc", ["a", "bc"], "reviewed"), raw("abc", ["ab", "c"], "reviewed")],
        }
        for name, sources in cases.items():
            for order in (1, -1):
                (row,), _ = self.module.merge_gold(None, sources[::order])
                self.assertIsNone(row["gold"], name)
                self.assertFalse(row["reviewed"], name)
                self.assertEqual(row["conflict"]["resolution"], "unresolved", name)

    def test_different_ipa_is_not_a_conflict(self):
        rows, _ = self.module.merge_gold(
            None, [raw("ab", ["a", "b"], "candidate"), raw("ab", ["ab"], "candidate")]
        )
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["conflict"] is None for row in rows))

    def test_only_literal_true_marks_curated_reviewed(self):
        entries = [
            reviewed_entry(self.module, "w1", ["x"], ["w1"]),
            {"word": "w2", "segments": ["w2"], "ipa": ["x"], "reviewed": "yes"},
            {"word": "w3", "segments": ["w3"], "ipa": ["x"], "reviewed": 1},
            {"word": "w4", "segments": ["w4"], "ipa": ["x"]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gold.json"
            path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
            rows = self.module.load_raw_gold(path)
        labels = {source: {row["label"] for row in rows if row["source"] == source} for source in ("fixture", "known_word_table")}
        self.assertEqual(labels, {"fixture": {"contract"}, "known_word_table": {"candidate"}})
        curated = {row["word"]: row["label"] for row in rows if row["source"] == "curated"}
        self.assertEqual(curated, {"w1": "reviewed", "w2": "candidate", "w3": "candidate", "w4": "candidate"})

    def test_evaluate_scores_tiers_and_conflicts_separately(self):
        m = self.module
        somebody_ipa = m.default_pipeline.process_word("somebody")["ipa"]
        entries = [
            # Reviewed and matched by the aligner (the known-table morpheme split some|body is invalid gold).
            reviewed_entry(m, "somebody", somebody_ipa, ["some", "bo", "dy"]),
            # Overrides the contract fixture li|ttle with a reviewed split the aligner does not give.
            reviewed_entry(m, "little", ["l", "ɪ", "t", "ə", "l"], ["lit", "tle"]),
            # Disagrees with the contract fixture know|ledge and is not reviewed: unresolved, never scored.
            {"id": "knowledge", "word": "knowledge", "ipa": ["n", "ɑ", "l", "ə", "dʒ"], "segments": ["knowl", "edge"], "reviewed": False},
            # Two segments on a one-syllable IPA: invalid_gold first, so not also stale despite the missing fingerprint.
            {"id": "cat", "word": "cat", "segments": ["c", "at"], "reviewed": True},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gold.json"
            path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
            report = m.evaluate(curated_path=path)
        items = {item["word"]: item for item in report["items"]}
        self.assertEqual(report["gold_reviewed"], 2)
        self.assertEqual(report["gold_conflicts"], {"resolved_by_review": 1, "unresolved": 1})
        self.assertEqual(report["stale_reviewed"], [])
        cat = [bad for bad in report["invalid_gold"] if bad["source"] == "curated"]
        self.assertEqual([(bad["id"], bad["reason"]) for bad in cat], [("cat", "syllable_count_mismatch")])
        self.assertNotIn("cat", items)

        self.assertEqual((items["somebody"]["tier"], items["somebody"]["outcome"]), ("reviewed", "exact"))
        self.assertEqual((items["little"]["tier"], items["little"]["detail"]), ("reviewed", "boundary_differs"))
        self.assertEqual(items["knowledge"]["outcome"], "gold_conflict")

        reviewed = report["by_tier"]["reviewed"]
        self.assertEqual((reviewed["items"], reviewed["exact"], reviewed["mismatch"]["total"]), (2, 1, 1))
        self.assertEqual(report["rates"]["reviewed"]["exact_rate_when_suggested"], 0.5)
        self.assertEqual(report["rates"]["reviewed"]["suggestion_rate_on_gold"], 1.0)
        self.assertEqual(report["by_tier"]["candidate"]["gold_conflict"], 0)
        self.assertEqual(report["overall"]["gold_conflict"], 1)
        all_gold = report["rates"]["all_gold"]
        candidate = report["rates"]["candidate"]
        self.assertEqual(all_gold["with_gold"], candidate["with_gold"] + report["rates"]["reviewed"]["with_gold"])

    def test_by_source_counts_duplicate_rows_once(self):
        entries = [
            reviewed_entry(self.module, "cat", ["k", "æ", "t"], ["cat"]),
            reviewed_entry(self.module, "cat", ["k", "æ", "t"], ["cat"]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gold.json"
            path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
            report = self.module.evaluate(curated_path=path)
        (item,) = [item for item in report["items"] if item["word"] == "cat"]
        self.assertEqual(item["sources"], ["curated", "curated"])
        self.assertEqual(report["by_source"]["curated"]["items"], 1)
        self.assertEqual(report["by_tier"]["reviewed"]["items"], 1)


if __name__ == "__main__":
    unittest.main()
