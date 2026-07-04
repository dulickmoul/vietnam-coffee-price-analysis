#!/usr/bin/env python3
"""KKI (Konsil Kesehatan Indonesia) physician registry scraper.

Enumerates the Indonesian medical registry at https://kki.go.id via its three
public DataTables/AJAX endpoints. Two independent, resumable passes:

  list   -- enumerate every (token, name) per profession code. Minutes.
  detail -- fetch STR number + qualification per unique token. 1-3 hours.
  export -- dedupe and write the final CSV/Parquet.

Design notes / confirmed API behaviour (see docs/kki_scraper.md):
  * GET  /cekdokter/form               -> warms the ci_session cookie.
  * POST /ceknamednakes/get_profesi    body: jenis=1  -> profession codes.
  * POST /cek_dokter/search            DataTables server-side search.
      name match is a substring LIKE %kw%; length=5000 works (no page cap);
      profesi is REQUIRED (blank == 0). Offsets page cleanly.
  * POST /cek_dokter/detail_dokter     body: id=<token> -> HTML profile.
      token is stable and NOT session-bound.

The captcha on the form page is client-side theatre; all three AJAX endpoints
ignore it server-side. We do not touch it.

Everything is plain requests: no proxy, no captcha solver, no browser (swap in
httpx if you prefer — the API surface used here is identical). Retries +
exponential backoff are wired in
up front. State lives in JSON so any pass is safe to Ctrl-C and rerun with
zero repeated work.

Usage:
    python scripts/kki_scraper.py list    --out output/kki
    python scripts/kki_scraper.py detail  --out output/kki --workers 16
    python scripts/kki_scraper.py export  --out output/kki --format csv

Run `python scripts/kki_scraper.py --help` (or `<cmd> --help`) for options.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from html import unescape

import requests

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
BASE = "https://kki.go.id"
URL_FORM = f"{BASE}/cekdokter/form"
URL_PROFESI = f"{BASE}/ceknamednakes/get_profesi"
URL_SEARCH = f"{BASE}/cek_dokter/search"
URL_DETAIL = f"{BASE}/cek_dokter/detail_dokter"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Origin": BASE,
    "Referer": URL_FORM,
}

PAGE_SIZE = 5000            # confirmed: no server-side page-size cap.
KEYWORDS = ["a", "i"]       # union of "a" then "i" captures ~99%+ of names.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 5             # exponential backoff, capped.
BACKOFF_CAP = 30.0          # seconds.

# Extract the opaque detail token out of onclick="detail_dokter('TOKEN')".
_TOKEN_RE = re.compile(r"detail_dokter\(\s*['\"]([^'\"]+)['\"]\s*\)")
_TAG_RE = re.compile(r"<[^>]+>")

# Column order for the final export.
EXPORT_COLUMNS = [
    "profesi", "nama", "nomor_str", "kualifikasi",
    "masa_berlaku", "status_str", "token", "profil_sdmk_url",
]

log_lock = threading.Lock()


def log(msg: str) -> None:
    with log_lock:
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# HTTP with retry / backoff (wired up before the run, not bolted on after)
# --------------------------------------------------------------------------- #
class TransientError(Exception):
    """Retryable HTTP condition (429 / 5xx)."""


def _fmt_backoff(attempt: int, base: float) -> float:
    delay = min(base * (2 ** attempt), BACKOFF_CAP)
    # full jitter keeps a 16-worker fleet from retrying in lockstep.
    return random.uniform(0, delay)


def request_with_retry(session: requests.Session, method: str, url: str,
                       *, max_retries: int = MAX_RETRIES, base: float = 1.0,
                       **kwargs):
    """Issue a request, retrying on 429/5xx and network errors with backoff."""
    kwargs.setdefault("timeout", 30)
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = session.request(method, url, **kwargs)
            if resp.status_code in RETRYABLE_STATUS:
                raise TransientError(f"HTTP {resp.status_code} from {url}")
            resp.raise_for_status()
            return resp
        except (requests.RequestException, TransientError) as exc:
            last_exc = exc
            if attempt >= max_retries:
                break
            time.sleep(_fmt_backoff(attempt, base))
    raise last_exc  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
class KKIClient:
    def __init__(self, delay: float = 0.05):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._warmed = False

    def _jitter(self) -> None:
        if self.delay > 0:
            time.sleep(random.uniform(0, self.delay))

    def warm(self) -> None:
        """Fetch the form once to obtain the ci_session cookie."""
        if self._warmed:
            return
        request_with_retry(self.session, "GET", URL_FORM)
        self._warmed = True

    def get_professions(self, jenis: int = 1) -> list[dict]:
        """Return [{kode, profesi}, ...] for the given jenis (1 = Tenaga Medis)."""
        self.warm()
        resp = request_with_retry(
            self.session, "POST", URL_PROFESI,
            data={"jenis": str(jenis)}, headers=AJAX_HEADERS,
        )
        data = resp.json()
        # Endpoint may return a bare list or {data: [...]}.
        rows = data.get("data", data) if isinstance(data, dict) else data
        out = []
        for r in rows:
            kode = str(r.get("kode", r.get("id", ""))).strip()
            nama = str(r.get("profesi", r.get("nama", ""))).strip()
            if kode:
                out.append({"kode": kode, "profesi": nama})
        return out

    def search(self, profesi: str, nama: str, start: int,
               length: int = PAGE_SIZE) -> tuple[int, list[tuple[str, str]]]:
        """One DataTables page. Returns (records_total, [(token, name), ...])."""
        self.warm()
        self._jitter()
        body = {
            "draw": "1",
            "start": str(start),
            "length": str(length),
            "nama": nama,
            "jenis": "1",
            "tipe": "nama",
            "profesi": profesi,
            # DataTables sends a search[value]; harmless to include.
            "search[value]": nama,
        }
        resp = request_with_retry(
            self.session, "POST", URL_SEARCH, data=body, headers=AJAX_HEADERS,
        )
        return parse_search(resp.json())

    def detail(self, token: str) -> dict:
        """Fetch and parse one physician's profile HTML."""
        self.warm()
        self._jitter()
        resp = request_with_retry(
            self.session, "POST", URL_DETAIL,
            data={"id": token}, headers=AJAX_HEADERS,
        )
        return parse_detail(resp.text, token)


# --------------------------------------------------------------------------- #
# Parsing (pure functions -> unit-testable without network)
# --------------------------------------------------------------------------- #
def _clean(text: str) -> str:
    return unescape(_TAG_RE.sub(" ", text)).replace("\xa0", " ").strip()


def parse_search(payload: dict) -> tuple[int, list[tuple[str, str]]]:
    """Parse a DataTables search response into (records_total, rows)."""
    records_total = int(payload.get("recordsTotal", 0) or 0)
    rows: list[tuple[str, str]] = []
    for row in payload.get("data", []):
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            continue
        name = _clean(str(row[1]))
        m = _TOKEN_RE.search(str(row[2]))
        if not m:
            continue
        rows.append((m.group(1), name))
    return records_total, rows


# Field label -> keys used in the emitted record. Labels are matched
# case-insensitively against the profile HTML.
_DETAIL_FIELDS = {
    "nama": ["nama"],
    "kualifikasi": ["kualifikasi"],
    "nomor_str": ["nomor str", "no str", "nomor surat tanda registrasi"],
    "masa_berlaku": ["masa berlaku"],
    "status_str": ["status str", "status"],
}


def _find_field(html: str, labels: list[str]) -> str:
    """Find a labelled value in the profile HTML.

    Handles the common CodeIgniter table shapes:
        <td>Label</td><td>:</td><td>VALUE</td>
        <th>Label</th><td>VALUE</td>
        Label : VALUE
    """
    for label in labels:
        lab = re.escape(label)
        # table row: label cell then (optional ":" cell) then value cell.
        m = re.search(
            rf"{lab}\s*</[^>]+>\s*(?:<[^>]+>\s*:?\s*</[^>]+>\s*)?"
            rf"<t[dh][^>]*>(.*?)</t[dh]>",
            html, re.IGNORECASE | re.DOTALL,
        )
        if m:
            val = _clean(m.group(1))
            if val and val != ":":
                return val
        # plain "Label : value" up to end of line / tag.
        m = re.search(rf"{lab}\s*:\s*([^<\n\r]+)", html, re.IGNORECASE)
        if m:
            val = _clean(m.group(1))
            if val:
                return val
    return ""


def _find_profil_url(html: str) -> str:
    m = re.search(r'href=["\']([^"\']*sdmk[^"\']*)["\']', html, re.IGNORECASE)
    return unescape(m.group(1)) if m else ""


def parse_detail(html: str, token: str) -> dict:
    rec = {"token": token}
    for key, labels in _DETAIL_FIELDS.items():
        rec[key] = _find_field(html, labels)
    rec["profil_sdmk_url"] = _find_profil_url(html)
    return rec


# --------------------------------------------------------------------------- #
# Resumable state + JSONL sinks
# --------------------------------------------------------------------------- #
def _atomic_write_json(path: str, obj) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


@dataclass
class JsonlSink:
    """Append-only JSONL writer + on-startup key reload for dedupe/resume."""
    path: str
    key: str
    _seen: set = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _fh: object = None

    def load(self) -> set:
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self._seen.add(json.loads(line)[self.key])
                    except (json.JSONDecodeError, KeyError):
                        continue
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._fh = open(self.path, "a", encoding="utf-8")
        return self._seen

    def add(self, record: dict) -> bool:
        """Write record if its key is new. Returns True if written."""
        k = record[self.key]
        with self._lock:
            if k in self._seen:
                return False
            self._seen.add(k)
            self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._fh.flush()
            return True

    def __contains__(self, k) -> bool:
        return k in self._seen

    def __len__(self) -> int:
        return len(self._seen)

    def close(self) -> None:
        if self._fh:
            self._fh.close()


# --------------------------------------------------------------------------- #
# Pass 1: list enumeration
# --------------------------------------------------------------------------- #
def list_pass(out_dir: str, *, delay: float, workers: int,
              keywords: list[str], limit_codes: int | None) -> None:
    os.makedirs(out_dir, exist_ok=True)
    state_path = os.path.join(out_dir, "list_state.json")
    rows_path = os.path.join(out_dir, "list_rows.jsonl")

    client = KKIClient(delay=delay)
    professions = client.get_professions(jenis=1)
    if limit_codes:
        professions = professions[:limit_codes]
    log(f"Fetched {len(professions)} profession codes (jenis=1).")

    state = {"records_total": {}, "completed": [], "counts": {}}
    if os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as f:
            state.update(json.load(f))
    completed: set = set(tuple(x) for x in state["completed"])
    records_total: dict = state["records_total"]
    counts: dict = state["counts"]
    state_lock = threading.Lock()

    sink = JsonlSink(rows_path, key="token")
    sink.load()
    log(f"Resuming: {len(sink)} tokens already seen, "
        f"{len(completed)} (code,kw,offset) tuples done.")

    def flush_state() -> None:
        with state_lock:
            _atomic_write_json(state_path, {
                "records_total": records_total,
                "completed": [list(t) for t in completed],
                "counts": counts,
            })

    def do_page(kode: str, profesi: str, kw: str, start: int) -> int:
        rt, rows = client.search(kode, kw, start)
        with state_lock:
            records_total[f"{kode}\t{kw}"] = rt
        added = 0
        for token, name in rows:
            if sink.add({"token": token, "nama": name,
                         "profesi_kode": kode, "profesi": profesi}):
                added += 1
        with state_lock:
            completed.add((kode, kw, start))
            counts[kode] = counts.get(kode, 0) + added
        return added

    grand_total = len(sink)
    t0 = time.time()

    for ci, prof in enumerate(professions, 1):
        kode, profesi = prof["kode"], prof["profesi"]
        code_added = 0
        for kw in keywords:
            key = f"{kode}\t{kw}"
            # Offset 0 first (sequential) to learn recordsTotal for this (code,kw).
            if (kode, kw, 0) not in completed:
                code_added += do_page(kode, profesi, kw, 0)
            rt = records_total.get(key, 0)
            offsets = [s for s in range(PAGE_SIZE, rt, PAGE_SIZE)
                       if (kode, kw, s) not in completed]
            if offsets:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futs = {pool.submit(do_page, kode, profesi, kw, s): s
                            for s in offsets}
                    for fut in as_completed(futs):
                        try:
                            code_added += fut.result()
                        except Exception as exc:  # noqa: BLE001
                            log(f"  ! page {kode}/{kw}/{futs[fut]} failed: {exc}")
            flush_state()

        grand_total = len(sink)
        elapsed = time.time() - t0
        eta = (elapsed / ci) * (len(professions) - ci)
        log(f"[{ci}/{len(professions)}] {profesi} ({kode}): "
            f"+{code_added} new | total unique {grand_total:,} | "
            f"ETA {eta/60:.1f} min")

    flush_state()
    sink.close()
    log(f"List pass complete. {grand_total:,} unique tokens -> {rows_path}")


# --------------------------------------------------------------------------- #
# Pass 2: detail enumeration
# --------------------------------------------------------------------------- #
def detail_pass(out_dir: str, *, delay: float, workers: int) -> None:
    rows_path = os.path.join(out_dir, "list_rows.jsonl")
    detail_path = os.path.join(out_dir, "detail_rows.jsonl")
    if not os.path.exists(rows_path):
        sys.exit(f"No list output at {rows_path}. Run the list pass first.")

    # Load list rows (token -> profesi/nama context to carry into detail rows).
    context: dict[str, dict] = {}
    with open(rows_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            context.setdefault(r["token"], r)

    done = JsonlSink(detail_path, key="token")
    done.load()
    pending = [t for t in context if t not in done]
    log(f"Detail pass: {len(context):,} unique tokens, "
        f"{len(done):,} done, {len(pending):,} pending.")
    if not pending:
        log("Nothing to do.")
        return

    client = KKIClient(delay=delay)
    client.warm()
    t0 = time.time()
    processed = 0
    total = len(pending)
    prog_lock = threading.Lock()

    def work(token: str) -> None:
        nonlocal processed
        rec = client.detail(token)
        ctx = context.get(token, {})
        rec["profesi"] = ctx.get("profesi", "")
        rec["profesi_kode"] = ctx.get("profesi_kode", "")
        # Prefer the list-pass name if the detail HTML lacked one.
        if not rec.get("nama"):
            rec["nama"] = ctx.get("nama", "")
        done.add(rec)
        with prog_lock:
            processed += 1
            if processed % 500 == 0 or processed == total:
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed else 0
                eta = (total - processed) / rate if rate else 0
                log(f"  {processed:,}/{total:,} details "
                    f"({rate:.1f}/s, ETA {eta/60:.1f} min)")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(work, t): t for t in pending}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as exc:  # noqa: BLE001
                log(f"  ! detail {futs[fut]} failed: {exc}")

    done.close()
    log(f"Detail pass complete -> {detail_path}")


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def _read_jsonl(path: str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def export(out_dir: str, *, fmt: str) -> None:
    detail_path = os.path.join(out_dir, "detail_rows.jsonl")
    rows_path = os.path.join(out_dir, "list_rows.jsonl")

    if os.path.exists(detail_path):
        records = _read_jsonl(detail_path)
        source = "detail"
    elif os.path.exists(rows_path):
        records = _read_jsonl(rows_path)
        source = "list"
    else:
        sys.exit(f"Nothing to export in {out_dir}.")

    # Normalize to the export schema.
    norm = []
    for r in records:
        norm.append({c: r.get(c, "") for c in EXPORT_COLUMNS})

    # Dedupe: by nomor_str when present (same person appears under multiple
    # profession codes), else by token.
    seen_str: set = set()
    seen_tok: set = set()
    deduped = []
    for r in norm:
        nstr = (r.get("nomor_str") or "").strip()
        tok = r.get("token") or ""
        if nstr:
            if nstr in seen_str:
                continue
            seen_str.add(nstr)
        else:
            if tok in seen_tok:
                continue
        seen_tok.add(tok)
        deduped.append(r)

    log(f"Export ({source}): {len(records):,} rows -> {len(deduped):,} after dedupe.")
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, "kki_physicians")

    if fmt == "parquet":
        try:
            import pandas as pd  # noqa: WPS433
            path = f"{stem}.parquet"
            pd.DataFrame(deduped, columns=EXPORT_COLUMNS).to_parquet(path, index=False)
            log(f"Wrote {path}")
            return
        except ImportError:
            log("pandas/pyarrow unavailable; falling back to CSV.")

    import csv
    path = f"{stem}.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS)
        w.writeheader()
        w.writerows(deduped)
    log(f"Wrote {path}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--out", default="output/kki", help="Output directory.")
        sp.add_argument("--delay", type=float, default=0.05,
                        help="Max per-request jitter delay in seconds.")
        sp.add_argument("--workers", type=int, default=16,
                        help="Concurrent workers (10-20 recommended).")

    sp = sub.add_parser("professions", help="Print profession codes and exit.")
    sp.add_argument("--out", default="output/kki")

    sp = sub.add_parser("list", help="Pass 1: enumerate tokens per profession.")
    common(sp)
    sp.add_argument("--keywords", default=",".join(KEYWORDS),
                    help="Comma-separated seed keywords (default: a,i).")
    sp.add_argument("--limit-codes", type=int, default=None,
                    help="Only process the first N codes (for testing).")

    sp = sub.add_parser("detail", help="Pass 2: fetch STR/qualification per token.")
    common(sp)

    sp = sub.add_parser("export", help="Dedupe and write CSV/Parquet.")
    sp.add_argument("--out", default="output/kki")
    sp.add_argument("--format", choices=["csv", "parquet"], default="csv")

    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)

    if args.cmd == "professions":
        client = KKIClient()
        for prof in client.get_professions(jenis=1):
            print(f"{prof['kode']}\t{prof['profesi']}")
    elif args.cmd == "list":
        kws = [k.strip() for k in args.keywords.split(",") if k.strip()]
        list_pass(args.out, delay=args.delay, workers=args.workers,
                  keywords=kws, limit_codes=args.limit_codes)
    elif args.cmd == "detail":
        detail_pass(args.out, delay=args.delay, workers=args.workers)
    elif args.cmd == "export":
        export(args.out, fmt=args.format)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Interrupted. State is saved — rerun the same command to resume.")
        sys.exit(130)
    except requests.RequestException as exc:
        sys.exit(f"Network error after retries: {exc}\n"
                 "The endpoint may be unreachable or throttling. If it is "
                 "429-ing, retry later or route through a residential proxy "
                 "(set HTTPS_PROXY).")
