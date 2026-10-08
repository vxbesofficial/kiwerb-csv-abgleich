# KIWERB CSV comparison — English quickstart

Compare two small local CSV exports using a chosen key and produce a report for
review. This is an AI-assisted work example for KIWERB, represented by the AI
project assistant for Ramin Adrian Fenchel. Its fixtures are synthetic; it is
not a client reference or an accepted production deliverable.

## Run the supplied example

Use an existing Python 3.9+ installation and a local terminal. Only the Python
standard library is used; the program makes no network or AI-service calls and
requires no API keys or server.

From the repository directory, run:

```sh
python3 reconcile.py --a examples/quelle-a-synthetisch.csv --b examples/quelle-b-synthetisch.csv --key Referenz --fields Betrag_EUR --out lauf-example-01
```

`lauf-example-01` must not already exist, and its parent directory must exist.
Success means exit code **0**, the message `Abgleich abgeschlossen`, and both
`report.json` and `result.html` in the new directory. Open `result.html` in a
browser; the report needs no JavaScript or external resources. A directory
containing `UNVOLLSTAENDIG.txt` is incomplete and must not be treated as a result.

The supplied example has 16 records per input and 17 key groups:

| Report label | Meaning | Example groups |
| --- | --- | ---: |
| Treffer | One record on each side; selected fields match exactly | 9 |
| Feldabweichung | One record on each side; at least one selected field differs | 2 |
| Nur A / Nur B | A single record exists only on that side | 2 / 2 |
| Dublette | A repeated key; all raw fields agree within each repeated side | 1 |
| Mehrdeutig | A repeated key; raw fields differ within a repeated side | 1 |

Repeated-key classification takes precedence over matching or one-sided status.
`Dublette` does **not** establish equality between A and B or permission to
delete anything. Repeated records are never automatically paired or discarded.

## Use two permitted exports

Choose `--key` and 1–10 `--fields` explicitly; replace `--a`, `--b` and `--out`.
Quote column names containing spaces. Both sources need the selected columns;
additional columns are retained. The same row or column ordering is unnecessary.

- Exactly two distinct regular UTF-8 CSV files, optionally with a BOM; no symlink
  inputs. Limit: 1,000 data records and 10 MiB per source.
- Headers must be present, nonempty and unique. Blank or whitespace-only keys,
  blank records and inconsistent field counts are rejected.
- The default delimiter is `;`. For actual comma-separated input, add
  `--delimiter ,`. Quoted multiline fields are supported.
- Comparison is exact text: `001` differs from `1`, `0.00` from `0.0`, and `0`
  from an empty value. Case and whitespace matter. There is no trimming, numeric
  calculation, totals check, fuzzy matching, XLSX support or automatic correction.

`report.json` retains every parsed field value and record, physical source-line
ranges and source-file SHA-256 hashes. Counts of key groups and input records are
separate. Original files are not changed. Reports can contain confidential data;
keep them out of public repositories or issues. Validate any later export into
spreadsheets separately: raw values can contain formula-like text.

## Resolve common problems

- **Missing column:** check exact spelling, case, spaces and the chosen delimiter.
- **Invalid CSV or encoding:** inspect the indicated source lines; correct an
  authorized working copy or re-export it as UTF-8 without silent replacement.
- **Empty key:** resolve the identifier from a reliable source; do not invent one.
- **Existing output directory:** choose a new name. Existing results are preserved.
- **Interrupted or failed write:** do not use an incomplete directory; fix the
  cause and rerun with a new output name. A validation/output error exits with 2.
- **Too many records:** agree a smaller coherent input; arbitrary splitting can
  hide repeated keys or relationships.

## Evidence and limits

`python3 test_acceptance.py` reproduces 31 automated acceptance tests. The recorded
run used synthetic data on macOS. A separate visual check on 8 October 2026
covered representative synthetic reports in Chrome at 1440 × 900 and 390 × 844,
including multiline fields, long text and horizontal scrolling of source tables.
These checks do not establish Windows compatibility or independent customer
operation. The full German manual is [ANLEITUNG.txt](ANLEITUNG.txt); messages and
status labels remain German.

No business correctness, savings, ongoing hosting, monitoring or unlimited support
is promised. Before a customer handover, agree data rights, the actual environment,
acceptance cases, independent operation, correction scope and use/transfer rights.
This repository currently contains no software license; this translation grants
no additional license rights.
