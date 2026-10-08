#!/usr/bin/env python3
"""Begrenzte lokale Lieferfähigkeitsprüfung, kein abgenommenes Kundenprodukt."""
import argparse
import csv
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import stat
import sys

VERSION = "1.0"
MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 1000
STATUSES = ("Treffer", "Feldabweichung", "Nur A", "Nur B", "Dublette", "Mehrdeutig")


class InputError(Exception):
    pass


def fail(label, start, message, end=None):
    position = str(start) if end in (None, start) else "{}–{}".format(start, end)
    raise InputError("Quelle {} · Zeile {}: {}".format(label, position, message))


def read_source(path, label, key, fields, delimiter):
    try:
        if path.is_symlink():
            fail(label, 1, "Symbolische Eingabeverknüpfung nicht erlaubt; Originaldatei wählen.")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(str(path), flags), "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                fail(label, 1, "Eingabe muss eine reguläre Datei sein.")
            if info.st_size > MAX_BYTES:
                fail(label, 1, "Datei überschreitet 10 MiB; Umfang vorher reduzieren.")
            raw = stream.read(MAX_BYTES + 1)
    except OSError as exc:
        fail(label, 1, "Datei nicht lesbar: {}".format(exc.strerror or str(exc)))
    if len(raw) > MAX_BYTES:
        fail(label, 1, "Datei überschreitet 10 MiB; Umfang vorher reduzieren.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        line = len(re.findall(br"\r\n|\r|\n", exc.object[:exc.start])) + 1
        fail(label, line, "Ungültiges UTF-8; eine separate UTF-8-CSV exportieren.")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    records, headers = [], None
    while True:
        start = reader.line_num + 1
        try:
            values = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            fail(label, start, "CSV nicht lesbar: {}".format(exc), max(start, reader.line_num))
        end = reader.line_num
        if headers is None:
            headers = values
            if not headers or any(not value.strip() for value in headers):
                fail(label, start, "Kopfzeile fehlt oder enthält leere Spaltennamen.", end)
            if len(set(headers)) != len(headers):
                fail(label, start, "Doppelte Spaltennamen in der Kopfzeile.", end)
            missing = [name for name in dict.fromkeys([key] + fields) if name not in headers]
            if missing:
                fail(label, start, "Pflichtspalten fehlen: {}. Namen exakt prüfen.".format(
                    ", ".join(repr(name) for name in missing)), end)
            continue
        if len(values) != len(headers):
            fail(label, start, "{} Felder statt {}; Trennzeichen/CSV-Export prüfen.".format(
                len(values), len(headers)), end)
        if len(records) >= MAX_ROWS:
            fail(label, start, "Mehr als 1.000 Datenzeilen; Umfang vorher reduzieren.", end)
        row = dict(zip(headers, values))
        if not row[key].strip():
            fail(label, start, "Schlüssel {!r} ist leer oder besteht nur aus Leerraum.".format(key), end)
        records.append({"values": row, "line_start": start, "line_end": end})
    if headers is None:
        fail(label, 1, "Datei ist leer; Kopfzeile und mindestens einen Datensatz bereitstellen.")
    if not records:
        fail(label, max(1, reader.line_num), "Keine Datenzeilen nach der Kopfzeile.")
    meta = {"filename": path.name, "sha256": hashlib.sha256(raw).hexdigest(),
            "headers": headers, "row_count": len(records)}
    return meta, records, (info.st_dev, info.st_ino)


def reconcile(a_rows, b_rows, key, fields):
    groups = {}
    for side, rows in (("a_rows", a_rows), ("b_rows", b_rows)):
        for row in rows:
            value = row["values"][key]
            group = groups.setdefault(value, {"key": value, "status": "", "a_rows": [],
                                              "b_rows": [], "differences": []})
            group[side].append(row)
    for group in groups.values():
        a, b = group["a_rows"], group["b_rows"]
        if len(a) > 1 or len(b) > 1:
            identical = all(all(row["values"] == rows[0]["values"] for row in rows)
                            for rows in (a, b) if len(rows) > 1)
            group["status"] = "Dublette" if identical else "Mehrdeutig"
        elif not a or not b:
            group["status"] = "Nur A" if a else "Nur B"
        else:
            group["differences"] = [
                {"field": field, "a": a[0]["values"][field], "b": b[0]["values"][field]}
                for field in fields if a[0]["values"][field] != b[0]["values"][field]]
            group["status"] = "Feldabweichung" if group["differences"] else "Treffer"
    return list(groups.values())


def render(report):
    def esc(value):
        return html.escape(str(value), quote=True)

    def raw_cell(value):
        # JSON notation makes empty text and control characters visible, without altering JSON data.
        return "<td><pre>{}</pre></td>".format(esc(json.dumps(value, ensure_ascii=False)))

    parts = ["<!doctype html><html lang='de'><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width,initial-scale=1'>",
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
             "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">",
             "<title>Lokaler CSV-Abgleich</title><style>body{font:16px system-ui;margin:2rem;"
             "color:#18212b;background:#fff}table{border-collapse:collapse;margin:1rem 0}"
             "td,th{border:1px solid #aaa;padding:.5rem;vertical-align:top;text-align:left}"
             "pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;max-width:38rem}"
             ".scroll{overflow-x:auto}.source-rows table{min-width:40rem}section{border-top:2px solid #555;margin-top:2rem}"
             "code{overflow-wrap:anywhere}</style><h1>Lokaler CSV-Abgleich</h1>",
             "<p>Interne Lieferfähigkeitsprüfung. Keine Kundenreferenz, keine fachliche Freigabe. "
             "Alle Werte werden als unveränderter Text verglichen. Zahlen werden nicht berechnet.</p>",
             "<p>Werte erscheinen in JSON-Schreibweise: <code>\"\"</code> ist leer, "
             "<code>\"0\"</code> ist Text 0; <code>\\n</code> bezeichnet einen Zeilenumbruch. "
             "report.json enthält die exakten Werte.</p>",
             "<h2>Regeln und Quellen</h2><pre>{}</pre>".format(esc(json.dumps(
                 report["rules"], ensure_ascii=False, indent=2)))]
    for label, source in report["sources"].items():
        parts.append("<p>Quelle {}: {} · {} Datensätze<br>SHA-256: <code>{}</code></p>".format(
            label, esc(source["filename"]), source["row_count"], source["sha256"]))
    parts.append("<h2>Statusübersicht</h2><table><tr><th>Status</th><th>Gruppen</th></tr>")
    for status, count in report["summary"]["counts"].items():
        parts.append("<tr><td>{}</td><td>{}</td></tr>".format(status, count))
    parts.append("</table><p>Mehrfachschlüssel werden niemals automatisch gepaart oder entfernt. "
                 "Dublette bedeutet identische Rohfelder innerhalb jeder mehrfachen Seite; "
                 "unterschiedliche Rohfelder innerhalb einer Seite bedeuten Mehrdeutig.</p>")
    for group in report["groups"]:
        parts.append("<section><h2>{}</h2><p>Schlüssel:</p><pre>{}</pre>".format(
            group["status"], esc(json.dumps(group["key"], ensure_ascii=False))))
        if group["differences"]:
            parts.append("<h3>Feldabweichungen (nur 1:1)</h3><div class='scroll'><table>"
                         "<tr><th>Feld</th><th>A</th><th>B</th></tr>")
            for diff in group["differences"]:
                parts.append("<tr><th>{}</th>{}{}</tr>".format(
                    esc(diff["field"]), raw_cell(diff["a"]), raw_cell(diff["b"])))
            parts.append("</table></div>")
        for label, member in (("A", "a_rows"), ("B", "b_rows")):
            parts.append("<h3>Quelle {} · {} Datensätze</h3>".format(label, len(group[member])))
            if not group[member]:
                parts.append("<p>Kein Datensatz in dieser Quelle.</p>")
                continue
            headers = report["sources"][label]["headers"]
            parts.append("<div class='scroll source-rows'><table><tr><th>Physische Zeile(n)</th>" +
                         "".join("<th>{}</th>".format(esc(h)) for h in headers) + "</tr>")
            for row in group[member]:
                parts.append("<tr><td>{}–{}</td>{}</tr>".format(row["line_start"], row["line_end"],
                             "".join(raw_cell(row["values"][h]) for h in headers)))
            parts.append("</table></div>")
        parts.append("</section>")
    return "\n".join(parts) + "\n</html>\n"


def write_new_output(out, report):
    # Construct both outputs completely before exclusively reserving the destination.
    outputs = {"report.json": json.dumps(report, ensure_ascii=False, indent=2) + "\n",
               "result.html": render(report)}
    out.mkdir(mode=0o700)  # Never rename onto or reuse an existing destination, including symlinks.
    made = []
    try:
        for name, content in [("UNVOLLSTAENDIG.txt", "Lauf noch nicht abgeschlossen.\n")] + list(outputs.items()):
            target = out / name
            with target.open("xb") as stream:
                made.append(target)
                stream.write(content.encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
        (out / "UNVOLLSTAENDIG.txt").unlink()
    except BaseException:
        for target in reversed(made):
            try:
                target.unlink()
            except OSError:
                pass
        try:
            out.rmdir()
        except OSError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(description="Zwei CSV-Dateien exakt als Text vergleichen.")
    for name in ("a", "b", "key", "out"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--fields", nargs="+", required=True, help="1 bis 10 exakte Spaltennamen")
    parser.add_argument("--delimiter", default=";", help="Ein Trennzeichen; Standard ;")
    args = parser.parse_args()
    if not 1 <= len(args.fields) <= 10 or len(set(args.fields)) != len(args.fields):
        parser.error("--fields benötigt 1 bis 10 unterschiedliche Spaltennamen.")
    if not args.key.strip() or any(not field.strip() for field in args.fields):
        parser.error("--key und --fields dürfen keine leeren Spaltennamen enthalten.")
    if len(args.delimiter) != 1 or args.delimiter in ('"', "\r", "\n", "\0"):
        parser.error("--delimiter benötigt genau ein Zeichen außer Anführungszeichen, CR, LF oder NUL.")
    a_path, b_path, out = Path(args.a), Path(args.b), Path(args.out)
    try:
        if os.path.lexists(str(out)):
            raise InputError("Ausgabeziel existiert bereits (ggf. Verknüpfung); neuen Ordnernamen wählen.")
        if not out.parent.is_dir():
            raise InputError("Elternordner des Ausgabeziels fehlt oder ist kein Ordner.")
        csv.field_size_limit(MAX_BYTES)
        a_meta, a_rows, a_id = read_source(a_path, "A", args.key, args.fields, args.delimiter)
        b_meta, b_rows, b_id = read_source(b_path, "B", args.key, args.fields, args.delimiter)
        if a_id == b_id:
            raise InputError("Quelle B · Zeile 1: identisch mit Quelle A (auch Hardlink); zwei Dateien wählen.")
        groups = reconcile(a_rows, b_rows, args.key, args.fields)
        report = {
            "report_version": VERSION,
            "rules": {"version": VERSION, "key": args.key, "fields": args.fields,
                      "delimiter": args.delimiter, "comparison": "exact Unicode text",
                      "normalization": "none", "numeric_calculation": False,
                      "max_rows_per_source": MAX_ROWS, "max_bytes_per_source": MAX_BYTES,
                      "group_order": "first occurrence in A, then previously unseen keys in B",
                      "duplicate_rule": "all raw fields identical within each multiple side",
                      "multiple_keys": "never paired or discarded",
                      "line_references": "physical lines, 1-based, inclusive, header included"},
            "sources": {"A": a_meta, "B": b_meta},
            "summary": {"groups": len(groups), "source_rows": {"A": len(a_rows), "B": len(b_rows)},
                        "counts": {status: sum(g["status"] == status for g in groups) for status in STATUSES}},
            "groups": groups}
        write_new_output(out, report)
    except (InputError, OSError, ValueError) as exc:
        print("FEHLER: {} Kein neuer erfolgreicher Abgleich erstellt.".format(exc), file=sys.stderr)
        return 2
    print("Abgleich abgeschlossen: {} Gruppen; Ausgabe: {}".format(len(groups), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
