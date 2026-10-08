#!/usr/bin/env python3
"""Independent, black-box acceptance checks for the bounded CSV handover.

Uses only the documented command line and generated JSON/HTML; never imports
reconcile.py. Fixtures below are synthetic. The older demo CSVs are read only.
Run: python3 test_acceptance.py --evidence acceptance-results.json
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import html
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
PROGRAM = HERE / "reconcile.py"
DEMO = HERE / "examples"
STATUS_COUNTS = {
    "Treffer": 9,
    "Feldabweichung": 2,
    "Nur A": 2,
    "Nur B": 2,
    "Dublette": 1,
    "Mehrdeutig": 1,
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RenderedText(HTMLParser):
    """Inspect inert text independently of an HTML escape serialization choice."""

    def __init__(self, page):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.values = []
        self.pre = None
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "pre":
            self.pre = []

    def handle_data(self, data):
        if self.pre is not None:
            self.pre.append(data)

    def handle_endtag(self, tag):
        if tag == "pre" and self.pre is not None:
            text = "".join(self.pre)
            self.values.append(text)
            try:
                value = json.loads(text)
            except (ValueError, TypeError):
                pass
            else:
                if isinstance(value, str):
                    self.values.append(value)
            self.pre = None


class CsvAcceptance(unittest.TestCase):
    """Business expectations fixed independently of the implementation."""

    @classmethod
    def setUpClass(cls):
        if not PROGRAM.is_file():
            raise RuntimeError(f"Implementation not yet available: {PROGRAM}")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kiwerb-acceptance-")
        self.root = Path(self.tmp.name)
        self.a = self.root / "a.csv"
        self.b = self.root / "b.csv"
        self.out = self.root / "new-result"
        self.make_csv(self.a, [["x", "1"]])
        self.make_csv(self.b, [["x", "1"]])

    def tearDown(self):
        self.tmp.cleanup()

    def make_csv(self, path, rows, headers=("Referenz", "Betrag_EUR"),
                 delimiter=";", bom=False):
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter=delimiter, lineterminator="\r\n")
        writer.writerow(headers)
        writer.writerows(rows)
        path.write_bytes(stream.getvalue().encode("utf-8-sig" if bom else "utf-8"))

    def invoke(self, *, a=None, b=None, out=None, fields=("Betrag_EUR",),
               delimiter=None, key="Referenz", timeout=30):
        a, b, out = a or self.a, b or self.b, out or self.out
        originals = {p: p.read_bytes() for p in (a, b) if p.is_file()}
        args = [sys.executable, str(PROGRAM), "--a", str(a), "--b", str(b),
                "--key", key, "--fields", *fields, "--out", str(out)]
        if delimiter is not None:
            args.extend(["--delimiter", delimiter])
        result = subprocess.run(args, capture_output=True, text=True,
                                encoding="utf-8", timeout=timeout)
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original, f"Input changed: {path}")
        return result

    def success(self, **kwargs):
        out = kwargs.get("out", self.out)
        result = self.invoke(**kwargs)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((out / "report.json").is_file())
        self.assertTrue((out / "result.html").is_file())
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        page = (out / "result.html").read_text(encoding="utf-8")
        self.assertEqual(report["report_version"], "1.0")
        self.assertEqual(report["summary"]["groups"], len(report["groups"]))
        self.assertEqual(
            Counter(g["status"] for g in report["groups"]),
            Counter({k: v for k, v in report["summary"]["counts"].items() if v}),
        )
        return report, page

    def failure(self, **kwargs):
        out = kwargs.get("out", self.out)
        existed = out.exists() or out.is_symlink()
        result = self.invoke(**kwargs)
        self.assertNotEqual(result.returncode, 0, "Invalid request succeeded")
        message = (result.stdout + result.stderr).strip()
        self.assertTrue(message, "Failure lacks an explanatory message")
        self.assertNotIn("Traceback (most recent call last)", message)
        if not existed:
            self.assertFalse(out.exists() or out.is_symlink(),
                             "Failed run left a result directory/path")
        return message

    @staticmethod
    def groups_by_key(report):
        groups = {group["key"]: group for group in report["groups"]}
        if len(groups) != len(report["groups"]):
            raise AssertionError("One comparison group per key is required")
        return groups

    def test_existing_demo_retains_all_rows_and_expected_17_groups(self):
        a = DEMO / "quelle-a-synthetisch.csv"
        b = DEMO / "quelle-b-synthetisch.csv"
        report, _ = self.success(a=a, b=b, delimiter=";")
        self.assertEqual(report["summary"]["groups"], 17)
        self.assertEqual(report["summary"]["counts"], STATUS_COUNTS)
        self.assertEqual(report["summary"]["source_rows"], {"A": 16, "B": 16})
        for side, source in (("A", a), ("B", b)):
            self.assertEqual(report["sources"][side]["sha256"], sha256(source))
            with source.open(encoding="utf-8-sig", newline="") as handle:
                expected = list(csv.DictReader(handle, delimiter=";"))
            rows = [r for g in report["groups"] for r in g[side.lower() + "_rows"]]
            rows.sort(key=lambda row: row["line_start"])
            self.assertEqual([r["values"] for r in rows], expected)
            self.assertEqual([r["line_start"] for r in rows], list(range(2, 18)))
            self.assertEqual([r["line_end"] for r in rows], list(range(2, 18)))
        groups = self.groups_by_key(report)
        self.assertEqual(groups["DEMO-011"]["status"], "Dublette")
        self.assertEqual(len(groups["DEMO-011"]["a_rows"]), 2)
        self.assertEqual(groups["DEMO-012"]["status"], "Mehrdeutig")
        self.assertEqual(len(groups["DEMO-012"]["b_rows"]), 2)
        self.assertEqual(groups["DEMO-012"]["differences"], [])

    def test_exact_keys_keep_leading_zeroes_and_do_not_fuzzy_match(self):
        self.make_csv(self.a, [["001", "0"], ["SKU001", "7"], ["trim ", "8"]])
        self.make_csv(self.b, [["1", "0"], ["SKU1", "7"], ["trim", "8"]])
        groups = self.groups_by_key(self.success()[0])
        self.assertEqual(set(groups), {"001", "1", "SKU001", "SKU1", "trim ", "trim"})
        self.assertEqual(Counter(g["status"] for g in groups.values()),
                         {"Nur A": 3, "Nur B": 3})

    def test_zero_empty_numeric_spellings_and_unicode_are_exact_text(self):
        self.make_csv(self.a, [["zero-empty", "0"], ["format", "0.00"],
                               ["same-zero", "0"], ["empty", ""],
                               ["unicode", "é"], ["null-word", "Null"]])
        self.make_csv(self.b, [["zero-empty", ""], ["format", "0.0"],
                               ["same-zero", "0"], ["empty", ""],
                               ["unicode", "e\u0301"], ["null-word", "Null"]])
        groups = self.groups_by_key(self.success()[0])
        for key in ("zero-empty", "format", "unicode"):
            self.assertEqual(groups[key]["status"], "Feldabweichung")
        for key in ("same-zero", "empty", "null-word"):
            self.assertEqual(groups[key]["status"], "Treffer")
        self.assertEqual(groups["zero-empty"]["differences"],
                         [{"field": "Betrag_EUR", "a": "0", "b": ""}])

    def test_selected_fields_only_and_raw_unselected_columns_remain(self):
        headers = ["Referenz", "Betrag_EUR", "Notiz", "Kategorie"]
        self.make_csv(self.a, [["x", "1", "A", "red"]], headers)
        self.make_csv(self.b, [["x", "1", "B", "blue"]], headers)
        group = self.success()[0]["groups"][0]
        self.assertEqual(group["status"], "Treffer")
        self.assertEqual(group["a_rows"][0]["values"]["Notiz"], "A")
        group = self.success(out=self.root / "two-fields",
                             fields=("Betrag_EUR", "Kategorie"))[0]["groups"][0]
        self.assertEqual(group["status"], "Feldabweichung")
        self.assertEqual(group["differences"],
                         [{"field": "Kategorie", "a": "red", "b": "blue"}])

    def test_bom_and_quoted_multiline_preserve_values_and_physical_lines(self):
        data = '\ufeffReferenz;Betrag_EUR;Notiz\r\nx;1;"erste\r\nzweite;Zeile"\r\ny;2;"a""b"\r\n'
        self.a.write_bytes(data.encode("utf-8"))
        self.b.write_bytes(data.encode("utf-8"))
        groups = self.groups_by_key(self.success()[0])
        for side in ("a_rows", "b_rows"):
            row = groups["x"][side][0]
            self.assertEqual((row["line_start"], row["line_end"]), (2, 3))
            self.assertEqual(row["values"]["Notiz"], "erste\r\nzweite;Zeile")
            self.assertEqual(groups["y"][side][0]["values"]["Notiz"], 'a"b')
            self.assertEqual((groups["y"][side][0]["line_start"],
                              groups["y"][side][0]["line_end"]), (4, 4))

    def test_csv_content_is_inert_html_and_json_preserves_formula_text(self):
        payload = '<script>alert("csv")</script><img src=x onerror=alert(1)>'
        formula = '=HYPERLINK("https://example.invalid/","x")'
        rows = [[payload, formula], ["ampersand", "A & B < C"]]
        self.make_csv(self.a, rows)
        self.make_csv(self.b, rows)
        report, page = self.success()
        groups = self.groups_by_key(report)
        self.assertEqual(groups[payload]["a_rows"][0]["values"]["Betrag_EUR"], formula)
        self.assertNotIn(payload, page)
        self.assertNotIn('<img src=x onerror=', page)
        rendered = RenderedText(page)
        self.assertIn(payload, rendered.values)
        self.assertIn(formula, rendered.values)
        self.assertNotIn("script", rendered.tags)
        self.assertNotIn("img", rendered.tags)
        self.assertIn("A &amp; B &lt; C", page)

    def test_header_names_are_also_inert_html(self):
        field = '<svg onload=alert("header")>'
        self.make_csv(self.a, [["x", "1"]], ["Referenz", field])
        self.make_csv(self.b, [["x", "2"]], ["Referenz", field])
        report, page = self.success(fields=(field,))
        self.assertEqual(report["groups"][0]["differences"],
                         [{"field": field, "a": "1", "b": "2"}])
        self.assertNotIn(field, page)
        self.assertIn(html.escape(field), page)

    def test_duplicates_on_both_sides_are_never_paired(self):
        self.make_csv(self.a, [["dup", "1"], ["dup", "1"],
                               ["amb", "1"], ["amb", "2"]])
        self.make_csv(self.b, [["dup", "1"], ["dup", "1"],
                               ["amb", "1"], ["amb", "2"]])
        groups = self.groups_by_key(self.success()[0])
        self.assertEqual(groups["dup"]["status"], "Dublette")
        self.assertEqual(groups["amb"]["status"], "Mehrdeutig")
        for group in groups.values():
            self.assertEqual(len(group["a_rows"]), 2)
            self.assertEqual(len(group["b_rows"]), 2)
            self.assertEqual(group["differences"], [])

    def test_duplicate_definition_checks_full_raw_rows_not_selected_subset(self):
        headers = ["Referenz", "Betrag_EUR", "Notiz"]
        self.make_csv(self.a, [["x", "1", "first"], ["x", "1", "second"]], headers)
        self.make_csv(self.b, [["x", "1", "first"]], headers)
        group = self.success()[0]["groups"][0]
        self.assertEqual(group["status"], "Mehrdeutig")
        self.assertEqual(group["differences"], [])

    def test_reordering_does_not_change_group_classification_or_raw_multisets(self):
        rows_a = [["same", "1"], ["different", "2"], ["only-a", "3"],
                  ["dup", "4"], ["dup", "4"]]
        rows_b = [["same", "1"], ["different", "5"], ["only-b", "6"], ["dup", "4"]]
        self.make_csv(self.a, rows_a)
        self.make_csv(self.b, rows_b)
        first = self.success()[0]
        self.make_csv(self.a, list(reversed(rows_a)))
        self.make_csv(self.b, list(reversed(rows_b)))
        second = self.success(out=self.root / "reordered")[0]

        def semantic_groups(report):
            return {g["key"]: {"status": g["status"], "differences": g["differences"],
                                "a": sorted(json.dumps(r["values"], sort_keys=True)
                                            for r in g["a_rows"]),
                                "b": sorted(json.dumps(r["values"], sort_keys=True)
                                            for r in g["b_rows"])}
                    for g in report["groups"]}
        self.assertEqual(semantic_groups(first), semantic_groups(second))

    def test_custom_delimiter(self):
        self.make_csv(self.a, [["x", "1"]], delimiter=",")
        self.make_csv(self.b, [["x", "1"]], delimiter=",")
        self.assertEqual(self.success(delimiter=",")[0]["groups"][0]["status"], "Treffer")

    def test_maximum_1000_rows_and_10_comparison_fields_are_accepted(self):
        headers = ["Referenz"] + [f"F{i}" for i in range(10)]
        rows = [[f"K{i:04}"] + [str(i)] * 10 for i in range(1000)]
        self.make_csv(self.a, rows, headers)
        self.make_csv(self.b, rows, headers)
        report, _ = self.success(fields=tuple(headers[1:]))
        self.assertEqual(report["summary"]["counts"]["Treffer"], 1000)

    def test_valid_large_field_has_no_hidden_128_kib_parser_limit(self):
        large_text = "x" * (256 * 1024)
        self.make_csv(self.a, [["x", large_text]])
        self.make_csv(self.b, [["x", large_text]])
        group = self.success()[0]["groups"][0]
        self.assertEqual(group["status"], "Treffer")
        self.assertEqual(group["a_rows"][0]["values"]["Betrag_EUR"], large_text)

    def test_duplicate_headers_are_rejected(self):
        self.a.write_text("Referenz;Betrag_EUR;Betrag_EUR\nx;1;1\n", encoding="utf-8")
        self.failure()

    def test_missing_key_or_comparison_column_is_rejected(self):
        for missing in ("key", "field"):
            with self.subTest(missing=missing):
                headers = ["Other", "Betrag_EUR"] if missing == "key" else ["Referenz", "Other"]
                self.make_csv(self.a, [["x", "1"]], headers)
                self.failure()

    def test_empty_keys_on_either_source_are_rejected(self):
        for side in (self.a, self.b):
            with self.subTest(side=side.name):
                self.make_csv(self.a, [["x", "1"]])
                self.make_csv(self.b, [["x", "1"]])
                self.make_csv(side, [["", "1"]])
                self.failure()

    def test_short_extra_and_broken_quoted_rows_are_rejected(self):
        for bad in ("x\n", "x;1;extra\n", 'x;"unterminated\n', 'x;"1"trailing\n'):
            with self.subTest(row=bad):
                self.a.write_text("Referenz;Betrag_EUR\n" + bad, encoding="utf-8")
                self.failure()

    def test_invalid_utf8_is_rejected(self):
        self.a.write_bytes(b"Referenz;Betrag_EUR\nx;\xff\n")
        self.failure()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "Host has no FIFO support")
    def test_fifo_input_is_rejected_promptly_instead_of_waiting_for_a_writer(self):
        self.a.unlink()
        os.mkfifo(self.a)
        self.failure(timeout=3)

    def test_1001_rows_on_either_source_are_rejected(self):
        for side in (self.a, self.b):
            with self.subTest(side=side.name):
                self.make_csv(self.a, [["x", "1"]])
                self.make_csv(self.b, [["x", "1"]])
                self.make_csv(side, [[f"K{i}", "1"] for i in range(1001)])
                self.failure()

    def test_larger_than_10_mib_is_rejected_without_result(self):
        self.a.write_bytes(b"Referenz;Betrag_EUR\nx;" + b"a" * (10 * 1024 * 1024))
        self.failure()

    def test_more_than_10_fields_is_rejected(self):
        headers = ["Referenz"] + [f"F{i}" for i in range(11)]
        self.make_csv(self.a, [["x"] + ["1"] * 11], headers)
        self.make_csv(self.b, [["x"] + ["1"] * 11], headers)
        self.failure(fields=tuple(headers[1:]))

    def test_existing_output_directory_and_files_stay_unchanged(self):
        self.out.mkdir()
        old_report = self.out / "report.json"
        old_report.write_bytes(b'{"old":"keep"}\n')
        sentinel = self.out / "result.html"
        sentinel.write_bytes(b"old result must survive\n")
        before = {p.name: p.read_bytes() for p in self.out.iterdir()}
        self.failure()
        self.assertEqual({p.name: p.read_bytes() for p in self.out.iterdir()}, before)

    def test_existing_empty_output_directory_is_preserved(self):
        self.out.mkdir()
        original_inode = self.out.stat().st_ino
        self.failure()
        self.assertTrue(self.out.is_dir())
        self.assertEqual(self.out.stat().st_ino, original_inode)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_existing_output_file_stays_unchanged(self):
        self.out.write_bytes(b"not-a-directory-but-still-preserve")
        original = self.out.read_bytes()
        self.failure()
        self.assertEqual(self.out.read_bytes(), original)

    def test_input_path_cannot_be_used_as_output(self):
        self.failure(out=self.a)

    def test_same_input_file_cannot_pass_as_two_sources(self):
        self.failure(b=self.a)

    def test_hardlinked_inputs_cannot_pass_as_two_sources(self):
        self.b.unlink()
        os.link(self.a, self.b)
        self.assertEqual(self.a.stat().st_ino, self.b.stat().st_ino)
        self.failure()

    def test_output_symlink_is_rejected_without_touching_target(self):
        target = self.root / "old-result"
        target.mkdir()
        sentinel = target / "report.json"
        sentinel.write_bytes(b"keep target")
        self.out.symlink_to(target, target_is_directory=True)
        self.failure()
        self.assertTrue(self.out.is_symlink())
        self.assertEqual(sentinel.read_bytes(), b"keep target")
        self.assertEqual([p.name for p in target.iterdir()], ["report.json"])

    def test_dangling_output_symlink_is_also_preserved(self):
        target = self.root / "does-not-exist"
        self.out.symlink_to(target, target_is_directory=True)
        self.failure()
        self.assertTrue(self.out.is_symlink())
        self.assertFalse(target.exists())

    def test_failed_new_run_does_not_modify_an_older_success(self):
        old = self.root / "old-success"
        self.success(out=old)
        before = {p.name: p.read_bytes() for p in old.iterdir() if p.is_file()}
        self.a.write_text("Referenz;Betrag_EUR\n;1\n", encoding="utf-8")
        self.failure()
        self.assertEqual({p.name: p.read_bytes() for p in old.iterdir() if p.is_file()}, before)


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed.append(test.id())


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--evidence", type=Path)
    known, remaining = parser.parse_known_args()
    runner = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult)
    execution = unittest.main(argv=[sys.argv[0], *remaining], testRunner=runner, exit=False)
    result = execution.result
    if known.evidence:
        files = [Path(__file__), PROGRAM, DEMO / "quelle-a-synthetisch.csv",
                 DEMO / "quelle-b-synthetisch.csv"]
        record = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "method": "Independent standard-library subprocess black-box tests; synthetic input only",
            "command": "python3 test_acceptance.py --evidence acceptance-results.json",
            "successful": result.wasSuccessful(),
            "tests_run": result.testsRun,
            "accepted_checks": result.passed,
            "failures": [{"test": test.id(), "detail": detail} for test, detail in result.failures],
            "errors": [{"test": test.id(), "detail": detail} for test, detail in result.errors],
            "files_sha256": {str(p.relative_to(HERE)): sha256(p)
                             for p in files if p.is_file()},
            "scope_and_risks": [
                "CLI results verified on this host; no Windows or native Excel application verification.",
                "Input text is deliberately compared exactly; numeric/currency/date normalization is not supported.",
                "No customer data, API, network service, hosting or paid dependency used by these tests.",
                "Static HTML escaping checks do not replace a separate browser rendering/accessibility review.",
                "Filesystem refusal cases cover existing paths and symlinks; hostile concurrent filesystem races are not exhaustively tested.",
                "Passing tests demonstrates the bounded local contract, not customer acceptance, current delivery capacity or revenue.",
            ],
        }
        known.evidence.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
