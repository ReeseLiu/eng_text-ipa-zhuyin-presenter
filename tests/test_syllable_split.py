import copy
import hashlib
import importlib.util
import json
import random
import shutil
import subprocess
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import backend.pipeline as pipeline_module
from backend.phoneme_core.syllable_structure import analyze_syllable_tokens, resolve_compound_seam
from backend.pipeline import pipeline
from backend.server import PresenterHandler

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "syllable_split_cases.json"
NODE_RUNNER = ROOT / "tests" / "js" / "syllable_split_runner.js"
APP_FLOW_TEST = ROOT / "tests" / "js" / "app_flow_test.js"
VALID_CODES = {"oov", "pron_mismatch", "no_alignment", "cut_inside_chunk", "low_confidence", "reconstruct"}


def load_builder():
    spec = importlib.util.spec_from_file_location("build_align_table", ROOT / "scripts" / "build_align_table.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_cases():
    return json.loads(FIXTURES.read_text(encoding="utf-8"))["cases"]


def require_node():
    """Node is required: the Py/JS contract must not pass silently without it (no skip)."""
    node = shutil.which("node")
    if node is None:
        raise AssertionError("node not found on PATH; the browser (JS) contract tests require Node")
    return node


def run_node(items):
    node = require_node()
    proc = subprocess.run(
        [node, str(NODE_RUNNER)],
        input=json.dumps(items, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return json.loads(proc.stdout)


def parity_sample(size=1500, seed=20261031):
    """Deterministic sample of multi-syllable CMUdict pronunciations."""
    words = sorted(w for w in pipeline.g2p._dict if w.isalpha())
    rng = random.Random(seed)
    items = []
    for word in rng.sample(words, size):
        for ipa in pipeline._cmudict_ipa_pronunciations(word):
            items.append({"word": word, "ipa": ipa})
    return items


class SyllableSplitContractTest(unittest.TestCase):
    def test_fixture_codes_are_known(self):
        for case in load_cases():
            expected = case["expected"]
            self.assertIn(expected["status"], {"ok", "not_applicable", "failed"}, case["id"])
            if expected["status"] == "failed":
                self.assertIn(expected["code"], VALID_CODES, case["id"])
                self.assertEqual(expected["segments"], [], case["id"])

    def test_python_matches_fixtures(self):
        for case in load_cases():
            with self.subTest(case=case["id"]):
                self.assertEqual(pipeline.suggest_syllable_split(case["word"], case["ipa"]), case["expected"])

    def test_browser_matches_fixtures(self):
        cases = load_cases()
        results = run_node([{"word": c["word"], "ipa": c["ipa"]} for c in cases])
        for case, result in zip(cases, results):
            with self.subTest(case=case["id"]):
                self.assertEqual(result["suggestion"], case["expected"])

    def test_browser_and_python_agree_on_sample(self):
        items = parity_sample()
        results = run_node(items)
        mismatches = []
        for item, result in zip(items, results):
            py_suggestion = pipeline.suggest_syllable_split(item["word"], item["ipa"])
            py_syllables = [d["syllable_index"] for d in analyze_syllable_tokens(item["ipa"])]
            if result["suggestion"] != py_suggestion or result["syllable_indices"] != py_syllables:
                mismatches.append((item["word"], py_suggestion, result))
        self.assertEqual(mismatches[:5], [], f"{len(mismatches)} mismatches out of {len(items)}")

    def test_successful_segments_rebuild_word(self):
        for item in parity_sample(size=400, seed=7):
            result = pipeline.suggest_syllable_split(item["word"], item["ipa"])
            if result["status"] == "ok":
                self.assertEqual("".join(result["segments"]), item["word"])
                self.assertEqual(
                    len(result["segments"]),
                    len({d["syllable_index"] for d in analyze_syllable_tokens(item["ipa"])}),
                )


class AlignTableTest(unittest.TestCase):
    def test_table_header_matches_cmudict_and_browser_copy(self):
        table_text = pipeline_module.ALIGN_TABLE_PATH.read_text(encoding="utf-8")
        table = json.loads(table_text)
        sha = hashlib.sha256(pipeline_module.CMUDICT_PATH.read_bytes()).hexdigest()
        self.assertEqual(table["cmudict_sha256"], sha)
        self.assertTrue(table["aligner_version"])
        self.assertEqual(
            {tuple(v) for v in table["chunk_codes"].values()},
            {(1, 0), (1, 1), (1, 2), (2, 1), (3, 1)},
        )
        browser_js = (ROOT / "app" / "browser_align.js").read_text(encoding="utf-8")
        self.assertEqual(browser_js, "window.BROWSER_ALIGN_TABLE = " + table_text + ";\n")

    def test_build_check_passes(self):
        proc = subprocess.run(
            ["python3", str(ROOT / "scripts" / "build_align_table.py"), "--check"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


class SuggestionPriorityTest(unittest.TestCase):
    def test_suggestion_does_not_write_manual_syllables(self):
        payload = pipeline.process_text("headquarters,", "unit")
        word = payload["sentences"][0]["words"][0]
        before = copy.deepcopy(payload)
        result = pipeline.suggest_syllable_split(word["word"], word["ipa"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(payload, before)
        self.assertNotIn("manual_syllables", word)

    def test_applied_suggestion_is_manual_and_wins_over_auto(self):
        payload = pipeline.process_text("communication.", "unit")
        word = payload["sentences"][0]["words"][0]
        auto_texts = [t["text"] for t in pipeline.export_json(payload)[0]["words"][0]]
        # Auto split ignores the suggestion until it is applied.
        self.assertEqual(auto_texts, ["co", "mmu", "ni", "ca", "tion."])

        result = pipeline.suggest_syllable_split(word["word"], word["ipa"])
        # word["word"] carries no sentence punctuation, so neither do the segments.
        self.assertEqual(result["segments"], ["co", "mmu", "ni", "ca", "tion"])
        # Apply: segments + per-syllable slots written as manual_syllables (what app.js does).
        slots = {}
        for detail, zhuyin in zip(word["token_details"], word["display"]["zhuyin_plus"]):
            if zhuyin:
                slots.setdefault(detail["syllable_index"], {"C1": [], "V": [], "C2": []})[detail["syllable_slot"]].append(zhuyin)
        word["manual_syllables"] = [
            {"text": text, "slots": slots[idx]} for idx, text in enumerate(result["segments"])
        ]
        word["manual_syllables"][0]["text"] = "com"
        exported = [t["text"] for t in pipeline.export_json(payload)[0]["words"][0]]
        self.assertEqual(exported, ["com", "mmu", "ni", "ca", "tion"])


class LowConfidenceDetectionTest(unittest.TestCase):
    """_low_confidence_positions must see every competing path that moves a cut."""

    @classmethod
    def setUpClass(cls):
        cls.b = load_builder()
        cls.allowed = [(g, ph) for g, outs in cls.b.INVENTORY.items() for ph in outs]

    def _brute_force(self, letters, phones, scores, best, path):
        b = self.b
        edges = b._edges(letters, phones, scores)
        paths = []

        def walk(i, j, total, starts):
            if i == len(letters):
                if j == len(phones):
                    paths.append((total, starts))
                return
            for glen, plen, score, key in edges[i]:
                if j + plen <= len(phones) and phones[j : j + plen] == key[1]:
                    walk(i + glen, j + plen, total + score, {**starts, j: i} if plen else starts)

        walk(0, 0, 0.0, {})
        chosen = {j: i for i, j, _gl, plen, _k in path if plen}
        low = []
        for j in range(1, len(phones)):
            if j not in chosen:
                continue
            rival = max((t for t, starts in paths if starts.get(j) != chosen[j]), default=b.NEG_INF)
            if best - rival < b.LOW_CONFIDENCE_GAP:
                low.append(j)
        return low

    def test_rival_inside_one_to_two_chunk_at_chosen_letter(self):
        # Best: k|l|e->ə|l|i. Rival: e silent, l->/ə l/, so /l/ (index 3) no longer
        # opens a chunk at letter 3. The old early-skip missed index 3.
        b = self.b
        scores = {k: 0.0 for k in self.allowed}
        scores[("e", ())] = -0.5
        phones = ("k", "l", "ə", "l", "i")
        best, path, fwd, bwd, edges = b._viterbi("kleli", phones, scores)
        self.assertEqual([k for *_x, k in path][2], ("e", ("ə",)))
        self.assertEqual(b._low_confidence_positions("kleli", phones, best, path, fwd, bwd, edges), [2, 3])

    def test_matches_brute_force_on_random_inputs(self):
        b = self.b
        rng = random.Random(20261031)
        letters_pool = "klemnaeioxuthsc"
        phone_pool = ["k", "l", "m", "n", "ə", "ɛ", "i", "eɪ", "s", "j", "u", "w", "ʌ", "θ", "ʃ", "t"]
        checked = 0
        for _ in range(3000):
            scores = {k: -rng.uniform(0, 6) for k in self.allowed}
            word = "".join(rng.choice(letters_pool) for _ in range(rng.randint(3, 6)))
            phones = tuple(rng.choice(phone_pool) for _ in range(rng.randint(2, 6)))
            res = b._viterbi(word, phones, scores)
            if res is None:
                continue
            best, path, fwd, bwd, edges = res
            checked += 1
            with self.subTest(word=word, phones=phones):
                self.assertEqual(
                    b._low_confidence_positions(word, phones, best, path, fwd, bwd, edges),
                    self._brute_force(word, phones, scores, best, path),
                )
        self.assertGreater(checked, 50)


INVALID_INPUTS = [
    ("null_in_ipa_list", "communication", ["k", None, "m"]),
    ("number_in_ipa_list", "communication", ["k", 1]),
    ("zero_in_ipa_list", "communication", [0]),
    ("bool_in_ipa_list", "communication", [False]),
    ("nested_list_in_ipa", "communication", [["k"]]),
    ("object_in_ipa", "communication", [{}]),
    ("ipa_null", "communication", None),
    ("ipa_number", "communication", 5),
    ("ipa_object", "communication", {"0": "k"}),
    ("word_null", None, ["k", "ə"]),
    ("word_number", 5, ["k", "ə"]),
    ("word_list", ["communication"], ["k", "ə"]),
]

VALID_INPUTS = [
    ("ipa_string_spaced", "communication", "k ə m j u n ɪ k eɪ ʃ ə n"),
    ("ipa_empty_list", "communication", []),
    ("ipa_blank_strings", "communication", ["", "  "]),
    ("word_empty", "", ["k", "ə"]),
]


class QuietHandler(PresenterHandler):
    def log_message(self, format, *args):
        pass


class SuggestInputValidationTest(unittest.TestCase):
    """Python, browser JS and the HTTP API reject the same inputs (400 / bad_request)."""

    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _post(self, body):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.httpd.server_address[1]}/api/suggest_syllable_split",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_python_rejects_invalid_types(self):
        for case_id, word, ipa in INVALID_INPUTS:
            with self.subTest(case=case_id):
                with self.assertRaises(ValueError):
                    pipeline.suggest_syllable_split(word, ipa)

    def test_api_returns_400_for_invalid_types(self):
        for case_id, word, ipa in INVALID_INPUTS:
            with self.subTest(case=case_id):
                status, body = self._post({"word": word, "ipa": ipa})
                self.assertEqual(status, 400)
                self.assertEqual(body["error"]["code"], "bad_request")

    def test_api_rejects_empty_object(self):
        status, body = self._post({})
        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "bad_request")

    def test_api_matches_python_for_valid_inputs(self):
        for case_id, word, ipa in VALID_INPUTS:
            with self.subTest(case=case_id):
                status, body = self._post({"word": word, "ipa": ipa})
                self.assertEqual(status, 200)
                self.assertEqual(body, pipeline.suggest_syllable_split(word, ipa))

    def test_browser_agrees_with_python(self):
        cases = INVALID_INPUTS + VALID_INPUTS
        results = run_node([{"word": word, "ipa": ipa} for _id, word, ipa in cases])
        for (case_id, word, ipa), result in zip(cases, results):
            with self.subTest(case=case_id):
                try:
                    expected = {"suggestion": pipeline.suggest_syllable_split(word, ipa)}
                except ValueError:
                    expected = {"error": "bad_request"}
                self.assertEqual({k: v for k, v in result.items() if k != "syllable_indices"}, expected)


ROUTE_BODIES = [
    ("body_array", [], False),
    ("body_array_of_object", [{"word": "communication", "ipa": ["k"]}], False),
    ("body_null", None, False),
    ("body_number", 5, False),
    ("body_string", "communication", False),
    ("body_bool", True, False),
    ("body_empty_object", {}, False),
    ("word_missing", {"ipa": ["k", "ə"]}, False),
    ("ipa_missing", {"word": "communication"}, False),
    ("word_null", {"word": None, "ipa": ["k", "ə"]}, False),
    ("word_number", {"word": 5, "ipa": ["k", "ə"]}, False),
    ("word_object", {"word": {}, "ipa": ["k", "ə"]}, False),
    ("ipa_item_null", {"word": "communication", "ipa": ["k", None]}, False),
    ("ipa_item_bool", {"word": "communication", "ipa": ["k", True]}, False),
    ("ipa_item_number", {"word": "communication", "ipa": ["k", 1.5]}, False),
    ("ipa_item_object", {"word": "communication", "ipa": ["k", {"p": "ə"}]}, False),
    ("ipa_null", {"word": "communication", "ipa": None}, False),
    ("valid_list", {"word": "communication", "ipa": ["k", "ə", "m", "j", "u", "n", "ɪ", "k", "eɪ", "ʃ", "ə", "n"]}, True),
    ("valid_string", {"word": "communication", "ipa": "k ə m j u n ɪ k eɪ ʃ ə n"}, True),
    ("valid_empty_word", {"word": "", "ipa": []}, True),
    ("valid_extra_key", {"word": "cat", "ipa": ["k", "æ", "t"], "extra": 1}, True),
]


class SuggestRouteContractTest(unittest.TestCase):
    """server.py route and the browser-mode route (suggestSyllableSplitRequest) accept/reject the same bodies."""

    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    _post = SuggestInputValidationTest._post

    def test_server_route(self):
        for case_id, body, accepted in ROUTE_BODIES:
            with self.subTest(case=case_id):
                status, payload = self._post(body)
                if accepted:
                    self.assertEqual(status, 200)
                    self.assertEqual(payload, pipeline.suggest_syllable_split(body["word"], body["ipa"]))
                else:
                    self.assertEqual(status, 400)
                    self.assertEqual(payload["error"]["code"], "bad_request")

    def test_browser_route_matches_server(self):
        results = run_node([{"body": body} for _id, body, _ok in ROUTE_BODIES])
        for (case_id, body, _ok), result in zip(ROUTE_BODIES, results):
            with self.subTest(case=case_id):
                status, payload = self._post(body)
                if status == 200:
                    self.assertEqual(result, {"suggestion": payload})
                else:
                    self.assertEqual(status, 400)
                    self.assertEqual(result, {"error": "bad_request"})


class CompoundSeamTest(unittest.TestCase):
    """Rule 12: a listed compound is cut at its seam instead of at the maximal onset."""

    @staticmethod
    def seam_items():
        payload = json.loads((ROOT / "data" / "compound_seams.json").read_text(encoding="utf-8"))
        return [{"word": e["word_norm"], "ipa": e["ipa"].split()} for e in payload["entries"]]

    def test_listed_compounds_are_cut_at_the_seam(self):
        for word, expected in {
            "artwork": ["art", "work"],
            "backyard": ["back", "yard"],
            "blackwell": ["black", "well"],
            "bookworm": ["book", "worm"],
        }.items():
            with self.subTest(word=word):
                suggestion = pipeline.suggest_syllable_split(word, pipeline._cmudict_ipa_pronunciations(word)[0])
                self.assertEqual(suggestion["status"], "ok", suggestion)
                self.assertEqual(suggestion["segments"], expected)

    def test_seam_is_the_only_difference(self):
        word = "artwork"
        ipa = pipeline._cmudict_ipa_pronunciations(word)[0]
        with_seam = pipeline.suggest_syllable_split(word, ipa)
        saved, pipeline.compound_seams = pipeline.compound_seams, {}
        try:
            without_seam = pipeline.suggest_syllable_split(word, ipa)
        finally:
            pipeline.compound_seams = saved
        self.assertEqual(with_seam["segments"], ["art", "work"])
        self.assertNotEqual(without_seam["segments"], with_seam["segments"])

    def test_unlisted_words_and_other_ipa_are_unaffected(self):
        seams = pipeline.compound_seams
        ipa = pipeline._cmudict_ipa_pronunciations("artwork")[0]
        self.assertEqual(resolve_compound_seam(seams, "artwork", ipa), 3)
        self.assertIsNone(resolve_compound_seam(seams, "artwork", ipa[:-1] + ["g"]))
        self.assertIsNone(resolve_compound_seam(seams, "table", ["t", "eɪ", "b", "ə", "l"]))
        self.assertEqual(
            pipeline.suggest_syllable_split("table", pipeline._cmudict_ipa_pronunciations("table")[0])["segments"],
            ["ta", "ble"],
        )

    def test_browser_agrees_with_python_on_every_listed_compound(self):
        items = self.seam_items()
        self.assertGreater(len(items), 400)
        browser = run_node(items)
        for item, result in zip(items, browser):
            expected = pipeline.suggest_syllable_split(item["word"], item["ipa"])
            self.assertEqual(result["suggestion"], expected, item["word"])


class AppFlowTest(unittest.TestCase):
    """Loads the real app/app.js in a fake DOM: postJson dispatch, preview -> apply, stale preview."""

    def test_app_flow(self):
        proc = subprocess.run(
            [require_node(), str(APP_FLOW_TEST)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
