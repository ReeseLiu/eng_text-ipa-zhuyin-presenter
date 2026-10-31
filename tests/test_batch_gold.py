import importlib.util
import io
import json
import random
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BADGER_IPA = ["b", "æ", "dʒ", "ɚ"]


class FingerprintAndWriterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bg = load_script("eval_syllable_split").batch_gold

    def test_spec_test_vector(self):
        self.assertEqual(
            self.bg.reviewed_fingerprint("badger", BADGER_IPA, ["bad", "ger"]),
            "50da880ad28212fb6900b790c70e8a5cf16d8fe865f0c5ed1d69daccd17bb38e",
        )

    def test_fingerprint_normalizes_to_nfc(self):
        self.assertEqual(
            self.bg.reviewed_fingerprint("café", ["k"], ["café"]),
            self.bg.reviewed_fingerprint("café", ["k"], ["café"]),
        )

    def test_update_entry_revokes_on_bound_fields_only(self):
        entry = self.bg.mark_reviewed({"id": "badger", "word": "badger", "ipa": BADGER_IPA, "segments": ["bad", "ger"]}, "t1", "2026-10-31")
        self.assertIsNone(self.bg.stale_reason(entry))
        for changes in ({"segments": ["ba", "dger"]}, {"word": "Badger", "segments": ["Bad", "ger"]}, {"ipa": ["b", "æ", "dʒ", "ə"]}):
            updated = self.bg.update_entry(entry, **changes)
            self.assertIs(updated["reviewed"], False, changes)
            self.assertIsNone(updated["reviewed_fingerprint"], changes)
        kept = self.bg.update_entry(entry, audit=[{"segments": ["bad", "ger"], "source": "local_model"}], note="x")
        self.assertIs(kept["reviewed"], True)
        self.assertEqual(kept["reviewed_fingerprint"], entry["reviewed_fingerprint"])
        # Re-review recomputes the binding.
        rereviewed = self.bg.mark_reviewed(self.bg.update_entry(entry, segments=["ba", "dger"]))
        self.assertIsNone(self.bg.stale_reason(rereviewed))

    def test_mark_reviewed_requires_ipa_and_legal_segments(self):
        with self.assertRaises(ValueError):
            self.bg.mark_reviewed({"word": "badger", "segments": ["bad", "ger"]})
        with self.assertRaises(ValueError):
            self.bg.mark_reviewed({"word": "badger", "ipa": BADGER_IPA, "segments": ["badger"]})

    def test_legality_rules(self):
        two = ["ɑ", "b", "ɑ"]
        cases = {
            ("ab", ("a", "")): "empty_segment",
            ("ab", ()): "empty_segment",
            ("ab", ("a", "c")): "concat_mismatch",
            ("a\U0001F600", ("a\ud83d", "\ude00")): "codepoint_split",
            ("ée", ("e", "́e")): "concat_mismatch",  # splits a base letter from its combining mark
            ("abc", ("abc",)): "syllable_count_mismatch",
            ("ab", ("a", "b")): None,
        }
        for (word, segments), expected in cases.items():
            self.assertEqual(self.bg.legality_error(word, list(segments), two), expected, (word, segments))
        self.assertEqual(self.bg.legality_error("ab", "ab", two), "segments_not_string_list")
        self.assertEqual(self.bg.legality_error("hm", ["hm"], ["h", "m"]), None)  # vowel-less IPA counts as one syllable
        self.assertEqual(self.bg.legality_error("ab", ["a", "b"], ["ɑ", "b\ud800", "ɑ"]), "ipa_lone_surrogate")


class GoldLoadingTest(unittest.TestCase):
    """Curated gold files on disk -> stale_reviewed / invalid_gold / reviewed, through evaluate()."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_script("eval_syllable_split")
        cls.bg = cls.module.batch_gold

    def good(self, **extra):
        return {**self.bg.mark_reviewed({"id": "badger", "word": "badger", "ipa": BADGER_IPA, "segments": ["bad", "ger"]}), **extra}

    def run_entries(self, entries):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gold.json"
            path.write_text(json.dumps({"version": 1, "description": "t", "entries": entries}), encoding="utf-8")
            return self.module.evaluate(curated_path=path)

    def curated_item(self, report, word):
        return next(item for item in report["items"] if item["word"] == word and "curated" in item["sources"])

    def test_valid_reviewed_entry_counts(self):
        report = self.run_entries([self.good()])
        self.assertEqual(report["gold_reviewed"], 1)
        self.assertEqual(report["stale_reviewed"], [])
        self.assertEqual(self.curated_item(report, "badger")["tier"], "reviewed")

    def test_audit_only_change_stays_reviewed(self):
        entry = self.good(audit=[{"segments": ["ba", "dger"], "source": "local_model", "model_id": "m", "score": 0.2, "abstained": False}])
        report = self.run_entries([entry])
        self.assertEqual((report["gold_reviewed"], report["stale_reviewed"]), (1, []))

    def test_hand_edits_downgrade_to_stale_candidate(self):
        edits = {
            "segments": {"segments": ["ba", "dger"]},
            "word": {"word": "Badger", "segments": ["Bad", "ger"]},
            "ipa": {"ipa": ["b", "æ", "dʒ", "ə"]},
        }
        for name, change in edits.items():
            entry = {**self.good(), **change}  # fingerprint left as is
            report = self.run_entries([entry])
            self.assertEqual(report["gold_reviewed"], 0, name)
            self.assertEqual([(s["id"], s["reason"]) for s in report["stale_reviewed"]], [("badger", "fingerprint_mismatch")], name)
            self.assertEqual(self.curated_item(report, entry["word"])["tier"], "candidate", name)
            self.assertEqual(report["by_tier"]["reviewed"]["items"], 0, name)

    def test_missing_ipa_or_fingerprint_is_stale(self):
        no_ipa = {k: v for k, v in self.good().items() if k != "ipa"}
        no_key = {k: v for k, v in self.good().items() if k != "reviewed_fingerprint"}
        cases = {"ipa_missing": no_ipa, "fingerprint_missing": self.good(reviewed_fingerprint=None)}
        for reason, entry in [*cases.items(), ("fingerprint_missing", no_key)]:
            report = self.run_entries([entry])
            self.assertEqual([s["reason"] for s in report["stale_reviewed"]], [reason])
            self.assertEqual(report["gold_reviewed"], 0)

    def test_invalid_gold_is_not_scored_and_not_stale(self):
        entries = [
            self.good(id="empty", segments=["badger", ""]),
            self.good(id="concat", segments=["bad", "gex"]),
            self.good(id="count", segments=["badger"]),
            {"id": "badtype", "word": "badger", "ipa": BADGER_IPA, "segments": "bad|ger", "reviewed": True},
        ]
        report = self.run_entries(entries)
        curated = {bad["id"]: bad["reason"] for bad in report["invalid_gold"] if bad["source"] == "curated"}
        self.assertEqual(
            curated, {"empty": "empty_segment", "concat": "concat_mismatch", "count": "syllable_count_mismatch", "badtype": "segments_not_string_list"}
        )
        self.assertEqual(report["stale_reviewed"], [])
        self.assertEqual(report["by_source"].get("curated", {"items": 0})["items"], 0)

    def test_lone_surrogates_are_invalid_before_fingerprinting(self):
        entries = [
            self.good(),
            # Fingerprinting these would raise UnicodeEncodeError; legality must reject them first.
            {"id": "seg", "word": "bad\U0001F600ger", "ipa": BADGER_IPA, "segments": ["bad\ud83d", "\ude00ger"],
             "reviewed": True, "reviewed_fingerprint": "0" * 64},
            {"id": "ipa", "word": "badger", "ipa": ["b", "æ\ud800", "dʒ", "ɚ"], "segments": ["bad", "ger"],
             "reviewed": True, "reviewed_fingerprint": "0" * 64},
        ]
        report = self.run_entries(entries)
        curated = {bad["id"]: bad["reason"] for bad in report["invalid_gold"] if bad["source"] == "curated"}
        self.assertEqual(curated, {"seg": "codepoint_split", "ipa": "ipa_lone_surrogate"})
        self.assertEqual(report["stale_reviewed"], [])
        # The legal entry is still evaluated as reviewed gold.
        self.assertEqual(report["gold_reviewed"], 1)
        self.assertEqual(self.curated_item(report, "badger")["tier"], "reviewed")

    def test_cli_survives_lone_surrogates_in_invalid_gold(self):
        entry = {"id": "seg", "word": "bad\U0001F600ger", "ipa": BADGER_IPA, "segments": ["bad\ud83d", "\ude00ger"], "reviewed": True}
        with tempfile.TemporaryDirectory() as tmp:
            gold, out = Path(tmp) / "gold.json", Path(tmp) / "report.json"
            gold.write_text(json.dumps({"entries": [self.good(), entry]}), encoding="utf-8")
            # A strict UTF-8 stdout, like a real terminal, rather than StringIO which accepts surrogates.
            stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
            with redirect_stdout(stdout):
                self.assertEqual(self.module.main(["--gold", str(gold), "--out", str(out)]), 0)
            stdout.flush()
            self.assertIn("codepoint_split", stdout.buffer.getvalue().decode("utf-8"))
            report = json.loads(out.read_text(encoding="utf-8"))
        (bad,) = [bad for bad in report["invalid_gold"] if bad["source"] == "curated"]
        self.assertEqual((bad["id"], bad["gold"]), ("seg", ["bad\ud83d", "\ude00ger"]))
        self.assertEqual(report["gold_reviewed"], 1)

    def test_present_ipa_of_wrong_type_is_invalid_not_defaulted(self):
        cases = {"null": None, "string": " ".join(BADGER_IPA), "non_string_item": ["b", "æ", 3, "ɚ"]}
        for reviewed in (True, False):
            for name, ipa in cases.items():
                entry = {"id": name, "word": "badger", "ipa": ipa, "segments": ["bad", "ger"], "reviewed": reviewed}
                report = self.run_entries([entry])
                curated = [(bad["id"], bad["reason"]) for bad in report["invalid_gold"] if bad["source"] == "curated"]
                self.assertEqual(curated, [(name, "ipa_not_string_list")], (name, reviewed))
                self.assertEqual(report["stale_reviewed"], [], (name, reviewed))
                self.assertEqual(report["by_source"].get("curated", {"items": 0})["items"], 0, (name, reviewed))

    def test_omitted_ipa_uses_the_product_default(self):
        default_ipa = list(self.module.default_pipeline.process_word("badger")["ipa"])
        for reviewed, stale in ((False, []), (True, ["ipa_missing"])):
            report = self.run_entries([{"id": "omitted", "word": "badger", "segments": ["bad", "ger"], "reviewed": reviewed}])
            self.assertEqual([bad for bad in report["invalid_gold"] if bad["source"] == "curated"], [], reviewed)
            self.assertEqual([s["reason"] for s in report["stale_reviewed"]], stale, reviewed)
            item = self.curated_item(report, "badger")
            self.assertEqual((item["ipa"], item["tier"]), (default_ipa, "candidate"), reviewed)

    def test_disk_edit_then_reload_is_not_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gold.json"
            path.write_text(json.dumps({"entries": [self.good()]}), encoding="utf-8")
            self.assertEqual(self.module.evaluate(curated_path=path)["gold_reviewed"], 1)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["entries"][0]["segments"] = ["ba", "dger"]
            path.write_text(json.dumps(data), encoding="utf-8")
            report = self.module.evaluate(curated_path=path)
        self.assertEqual(report["gold_reviewed"], 0)
        self.assertEqual(len(report["stale_reviewed"]), 1)

    def test_conflicting_reviewed_is_unresolved(self):
        other = self.bg.mark_reviewed({"id": "badger2", "word": "badger", "ipa": BADGER_IPA, "segments": ["ba", "dger"]})
        report = self.run_entries([self.good(), other])
        self.assertEqual(report["gold_conflicts"]["unresolved"], 1)
        self.assertEqual(report["by_tier"]["reviewed"]["items"], 0)

    def test_strata_and_human_ipa_are_reported(self):
        sampled = self.good(sampling_stratum="ok_global", sampling_rate=0.001)
        human = self.bg.mark_reviewed({"id": "hm", "word": "hmm", "ipa": ["h", "ə", "m"], "segments": ["hmm"], "ipa_source": "human"})
        report = self.run_entries([sampled, human])
        self.assertEqual(set(report["reviewed_rates_by_stratum"]), {"ok_global", "unstratified"})
        self.assertEqual(report["reviewed_by_stratum"]["ok_global"]["items"], 1)
        self.assertEqual([row["id"] for row in report["ipa_source_human"]], ["hm"])


def row(word, code, ipa=("ɑ",), segments=None):
    return {"word": word, "ipa": list(ipa), "code": code, "suggested_segments": segments}


class QueueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bg = load_script("batch_gold")

    def test_partitions_sort_and_batch_ids(self):
        rows = [row(f"b{i:03d}", "no_alignment") for i in range(120)]
        rows += [row("apple", "low_confidence"), row("'bout", "low_confidence"), row("cat", "not_applicable")]
        rows += [row("b050", "no_alignment", ipa=("ɑ", "b"))]  # second pronunciation sorts right after ("ɑ",)
        queue, report = self.bg.build_queue(list(reversed(rows)), batch_size=50, sample_n=0)
        shuffled = rows[:]
        random.Random(1).shuffle(shuffled)
        self.assertEqual(self.bg.build_queue(shuffled, batch_size=50, sample_n=0)[0], queue)

        self.assertNotIn("cat", {r["word"] for r in queue})
        self.assertEqual(report["counts_by_code"]["not_applicable"], 1)
        ids = {(r["word"], tuple(r["ipa"])): r["batch_id"] for r in queue}
        self.assertEqual(ids[("'bout", ("ɑ",))], "low_confidence|other|0")
        self.assertEqual(ids[("apple", ("ɑ",))], "low_confidence|A|0")
        self.assertEqual(ids[("b000", ("ɑ",))], "no_alignment|B|0")
        self.assertEqual(ids[("b049", ("ɑ",))], "no_alignment|B|0")
        self.assertEqual(ids[("b050", ("ɑ",))], "no_alignment|B|1")
        self.assertEqual(ids[("b050", ("ɑ", "b"))], "no_alignment|B|1")
        self.assertEqual(ids[("b119", ("ɑ",))], "no_alignment|B|2")
        nb = [(r["word"], r["ipa"]) for r in queue if r["code"] == "no_alignment"]
        self.assertEqual(nb, sorted(nb, key=lambda k: (k[0], tuple(k[1]))))
        self.assertEqual(report["batches"]["no_alignment|B|2"], 21)

        # Documented: inserting a row shifts later rows to the next chunk; gold identity is (word, ipa), not batch_id.
        shifted = {(r["word"], tuple(r["ipa"])): r["batch_id"] for r in self.bg.build_queue(rows + [row("b0000", "no_alignment")], batch_size=50, sample_n=0)[0]}
        self.assertEqual(shifted[("b049", ("ɑ",))], "no_alignment|B|1")

    def test_batch_size_bounds(self):
        for size in (49, 201):
            with self.assertRaises(ValueError):
                self.bg.build_queue([], batch_size=size)

    def test_sampling_is_reproducible_and_matches_the_locked_algorithm(self):
        frame = [row(f"w{i:04d}", "ok", segments=["w", f"{i:04d}"]) for i in range(500)]
        reversed_frame = list(reversed(frame))
        drawn, record = self.bg.sample_frame(reversed_frame, 30, 0)
        again, _ = self.bg.sample_frame(frame, 30, 0)
        self.assertEqual(drawn, again)
        expected = random.Random(0).sample(sorted(frame, key=lambda r: (r["word"], tuple(r["ipa"]))), 30)
        self.assertEqual({r["word"] for r in drawn}, {r["word"] for r in expected})
        self.assertEqual([r["word"] for r in drawn], sorted(r["word"] for r in drawn))
        self.assertNotEqual({r["word"] for r in self.bg.sample_frame(frame, 30, 1)[0]}, {r["word"] for r in drawn})
        self.assertEqual(record, {
            "sampling_stratum": "ok_global", "frame_size": 500, "sample_n": 30, "sample_n_actual": 30,
            "sample_seed": 0, "sampling_rate": 30 / 500, "denominator": "frame_size",
        })

    def test_sampling_edge_frames(self):
        drawn, record = self.bg.sample_frame([], 30, 0)
        self.assertEqual((drawn, record["frame_size"], record["sample_n_actual"], record["sampling_rate"]), ([], 0, 0, None))
        small = [row(f"w{i}", "ok", segments=["w", str(i)]) for i in range(5)]
        drawn, record = self.bg.sample_frame(small, 30, 0)
        self.assertEqual((len(drawn), record["sample_n_actual"], record["sampling_rate"]), (5, 5, 1.0))

    def test_queue_sampled_rows_and_population_rate(self):
        rows = [row(f"ok{i}", "ok", segments=["o", f"k{i}"]) for i in range(40)] + [row("zed", "no_alignment"), row("cat", "not_applicable")]
        queue, report = self.bg.build_queue(rows)
        sampled = [r for r in queue if r["sampling_stratum"] == "ok_global"]
        self.assertEqual(len(sampled), 30)
        self.assertTrue(all(r["batch_id"] == "ok|ok_global|0" and r["sampling_rate"] == 30 / 40 and r["suggested_segments"] for r in sampled))
        failed = [r for r in queue if r["code"] == "no_alignment"]
        self.assertEqual([(r["sampling_stratum"], r["sampling_rate"], r["suggested_segments"]) for r in failed], [(None, None, None)])
        self.assertEqual(report["population"]["suggestion_rate"], round(40 / 41, 6))
        self.assertEqual(report["population"]["denominator_value"], 41)
        self.assertEqual(set(queue[0]), {"word", "ipa", "code", "batch_id", "suggested_segments", "sampling_stratum", "sampling_rate"})

    def test_empty_ok_frame(self):
        queue, report = self.bg.build_queue([row("zed", "no_alignment")])
        self.assertEqual(report["sampling"]["frame_size"], 0)
        self.assertIsNone(report["sampling"]["sampling_rate"])
        self.assertEqual(len(queue), 1)

    def test_gold_template_is_never_reviewed(self):
        entry = self.bg.gold_template_entry(
            {"word": "bouncer", "ipa": ["b", "aʊ", "n", "s", "ɚ"], "code": "ok", "batch_id": "ok|ok_global|0",
             "suggested_segments": ["boun", "cer"], "sampling_stratum": "ok_global", "sampling_rate": 0.5}
        )
        self.assertIs(entry["reviewed"], False)
        self.assertIsNone(entry["reviewed_fingerprint"])
        self.assertEqual(entry["segments"], [])
        self.assertEqual((entry["sampling_stratum"], entry["sampling_rate"]), ("ok_global", 0.5))
        self.assertEqual(entry["audit"][0]["source"], "aligner")


class QueueBuilderTest(unittest.TestCase):
    """Real Pipeline + a slice of the checked-in align table."""

    @classmethod
    def setUpClass(cls):
        cls.qb = load_script("build_batch_gold_queue")
        cls.table = json.loads((ROOT / "data" / "syllable_align_table.json").read_text(encoding="utf-8"))

    def test_evaluate_table_uses_the_suggest_path_for_every_variant(self):
        words = ("badger", "extra", "february", "little", "cat", "every")
        table = {**self.table, "entries": {w: self.table["entries"][w] for w in words}}
        rows = self.qb.evaluate_table(self.qb.Pipeline(), table)
        codes = {(r["word"], tuple(r["ipa"])): r["code"] for r in rows}
        self.assertEqual(codes[("badger", tuple(BADGER_IPA))], "low_confidence")
        self.assertEqual(codes[("little", ("l", "ɪ", "t", "ə", "l"))], "ok")
        self.assertEqual(codes[("cat", ("k", "æ", "t"))], "not_applicable")
        self.assertEqual(codes[("every", ("ɛ", "v", "ɚ", "i"))], "ok")
        self.assertEqual(codes[("every", ("ɛ", "v", "ɹ", "i"))], "ok")
        self.assertEqual(len(codes), len(rows))  # (word, ipa) rows are distinct
        little = next(r for r in rows if r["word"] == "little")
        self.assertEqual(little["suggested_segments"], ["li", "ttle"])

    def test_cli_limit_writes_queue_report_and_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            args = ["--limit", "300", "--out", str(tmp / "q.jsonl"), "--report", str(tmp / "r.json"), "--gold-template", str(tmp / "t.json")]
            with redirect_stdout(StringIO()):
                self.assertEqual(self.qb.main(args), 0)
            first = (tmp / "q.jsonl").read_text(encoding="utf-8")
            with redirect_stdout(StringIO()):
                self.qb.main(args)
            self.assertEqual((tmp / "q.jsonl").read_text(encoding="utf-8"), first)
            report = json.loads((tmp / "r.json").read_text(encoding="utf-8"))
            template = json.loads((tmp / "t.json").read_text(encoding="utf-8"))
        self.assertEqual(report["limit"], 300)
        self.assertEqual((report["sampling"]["sample_n"], report["sampling"]["sample_seed"]), (30, 0))
        self.assertEqual(len(template["entries"]), report["sampling"]["sample_n_actual"])
        self.assertTrue(all(e["reviewed"] is False for e in template["entries"]))
        queue = [json.loads(line) for line in first.splitlines()]
        self.assertEqual(len(queue), report["queue_rows"])
        self.assertNotIn("not_applicable", {r["code"] for r in queue})


if __name__ == "__main__":
    unittest.main()
