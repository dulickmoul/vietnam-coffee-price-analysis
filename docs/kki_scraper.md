# KKI physician registry scraper

`scripts/kki_scraper.py` enumerates the Indonesian medical registry
(Konsil Kesehatan Indonesia, [kki.go.id](https://kki.go.id)) — doctors,
dentists, and ~40 medical specialities (`jenis=1`, *Tenaga Medis*). Plain
`requests`, no proxy, no browser, no captcha solver.

> **Note on this repo:** this scraper is unrelated to the coffee-price
> analysis; it lives here only because it shares the branch. It is a
> standalone tool with its own tests (`tests/test_kki_scraper.py`).

## The API (already reverse-engineered)

| Step | Endpoint | Body | Returns |
|------|----------|------|---------|
| Warm | `GET /cekdokter/form` | — | sets `ci_session` cookie |
| Codes | `POST /ceknamednakes/get_profesi` | `jenis=1` | `[{kode, profesi}]` |
| Search | `POST /cek_dokter/search` | `draw=1&start=0&length=5000&nama=<kw>&jenis=1&tipe=nama&profesi=<kode>` | DataTables `{recordsTotal, data:[[#, name, button]]}` |
| Detail | `POST /cek_dokter/detail_dokter` | `id=<token>` | profile HTML |

All AJAX calls send `X-Requested-With: XMLHttpRequest`. The form's captcha is
client-side only — the three AJAX endpoints ignore it server-side, so we never
touch it.

Confirmed behaviour: name match is a substring `LIKE %kw%`; `length=5000` works
(no page-size cap); offsets page cleanly; `profesi` is **required** (blank == 0);
the detail token is stable and **not** session-bound.

## Two passes, both resumable

Every pass persists progress to JSON/JSONL under `--out` and is safe to
`Ctrl-C` and rerun with zero repeated work. Retries (exponential backoff with
full jitter, capped at 5 attempts) are wired in before the run, and any
`429`/`5xx` is retried with backoff.

```bash
# 0. (optional) inspect profession codes — fetched live, never hardcoded
python scripts/kki_scraper.py professions

# 1. LIST pass — every (token, name) per code. Minutes.
python scripts/kki_scraper.py list   --out output/kki --workers 16

# 2. DETAIL pass — STR number + qualification per unique token. 1–3 h.
python scripts/kki_scraper.py detail --out output/kki --workers 16

# 3. EXPORT — dedupe + write the final table
python scripts/kki_scraper.py export --out output/kki --format parquet
```

Run only steps 1 + 3 if you just want names and tokens (no STR numbers).

### List pass

For each profession code it pages the keyword `a` (offset steps of 5000 up to
`recordsTotal`), then unions the keyword `i` to catch names with no `a`
(override with `--keywords`). Rows are deduped by token and streamed to
`list_rows.jsonl`; completed `(code, keyword, offset)` tuples and per-code
counts live in `list_state.json`. Progress logs show per-code new counts, the
running unique total, and an ETA.

### Detail pass

One `detail_dokter` call per unique token, across 10–20 workers with a small
jitter delay. Results stream to `detail_rows.jsonl`, keyed by token, so a
rerun only fetches what's missing. Progress logs show throughput and ETA.

### Export

Reads `detail_rows.jsonl` if present (else `list_rows.jsonl`), dedupes by
`nomor_str` (the same person can appear under several profession codes),
falling back to token when the STR is blank, and writes columns:

```
profesi, nama, nomor_str, kualifikasi, masa_berlaku, status_str, token, profil_sdmk_url
```

Output is Parquet (`--format parquet`, needs `pandas`+`pyarrow`) or CSV — **not
xlsx**, since the full set is 300k+ rows. Parquet transparently falls back to
CSV if `pyarrow` isn't installed.

## Scale & politeness

Dokter ~190k, Dokter Gigi ~50k, plus ~40 specialist codes → **300k+ rows**.
List-only pass runs in minutes; a full detail pass is ~1–3 h at 10–20 workers,
$0. No rate limiting has been observed, but the client backs off on any
`429`/`5xx`. If the government box ever starts throttling, route through a
residential proxy as a fallback (set `HTTPS_PROXY`); it is not needed for a
normal run.

Out of scope: *Tenaga Kesehatan* (`jenis=2`) — that search is exact-match and
sparse, not enumerable.

## Options

| Flag | Default | Meaning |
|------|---------|---------|
| `--out` | `output/kki` | state + output directory |
| `--workers` | `16` | concurrent workers (10–20 recommended) |
| `--delay` | `0.05` | max per-request jitter delay (seconds) |
| `--keywords` | `a,i` | seed keywords for the list pass |
| `--limit-codes` | — | process only the first N codes (testing) |
| `--format` | `csv` | `csv` or `parquet` (export only) |

## Tests

```bash
python -m pytest tests/test_kki_scraper.py -q
```

Offline: exercises the search/detail parsers, the resumable JSONL sink, the
export dedupe, and the bounded backoff — no network required.
