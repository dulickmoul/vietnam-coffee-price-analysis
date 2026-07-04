"""Offline tests for the KKI scraper parsers and resumable state.

No network: these exercise the pure parsing functions and the JSONL
dedupe/resume sink against synthetic fixtures shaped like the real API.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import kki_scraper as kki  # noqa: E402


# --------------------------------------------------------------------------- #
# search response parsing
# --------------------------------------------------------------------------- #
def test_parse_search_extracts_token_and_name():
    payload = {
        "draw": 1,
        "recordsTotal": 2,
        "recordsFiltered": 2,
        "data": [
            [1, "BUDI SANTOSO",
             "<button onclick=\"detail_dokter('AbC123==')\">Detail</button>"],
            [2, "SITI &amp; AISYAH",
             "<button onclick='detail_dokter(\"xYz789\")'>Detail</button>"],
        ],
    }
    total, rows = kki.parse_search(payload)
    assert total == 2
    assert rows[0] == ("AbC123==", "BUDI SANTOSO")
    # HTML entity in the name is unescaped.
    assert rows[1] == ("xYz789", "SITI & AISYAH")


def test_parse_search_skips_rows_without_token():
    payload = {"recordsTotal": 1, "data": [[1, "NO BUTTON", "<span>-</span>"]]}
    total, rows = kki.parse_search(payload)
    assert total == 1
    assert rows == []


def test_parse_search_empty():
    total, rows = kki.parse_search({"recordsTotal": 0, "data": []})
    assert total == 0 and rows == []


# --------------------------------------------------------------------------- #
# detail HTML parsing
# --------------------------------------------------------------------------- #
DETAIL_HTML = """
<div class="profile">
  <table class="table">
    <tr><td>Nama</td><td>:</td><td>dr. BUDI SANTOSO, Sp.PD</td></tr>
    <tr><td>Kualifikasi</td><td>:</td><td>Dokter Spesialis Penyakit Dalam</td></tr>
    <tr><td>Nomor STR</td><td>:</td><td>3311100123456789</td></tr>
    <tr><td>Masa Berlaku</td><td>:</td><td>31 Desember 2028</td></tr>
    <tr><td>Status STR</td><td>:</td><td>Aktif</td></tr>
  </table>
  <a href="https://sdmk.kemkes.go.id/profil/12345">Profil SDMK</a>
</div>
"""


def test_parse_detail_all_fields():
    rec = kki.parse_detail(DETAIL_HTML, "TOKEN==")
    assert rec["token"] == "TOKEN=="
    assert rec["nama"] == "dr. BUDI SANTOSO, Sp.PD"
    assert rec["kualifikasi"] == "Dokter Spesialis Penyakit Dalam"
    assert rec["nomor_str"] == "3311100123456789"
    assert rec["masa_berlaku"] == "31 Desember 2028"
    assert rec["status_str"] == "Aktif"
    assert rec["profil_sdmk_url"] == "https://sdmk.kemkes.go.id/profil/12345"


def test_parse_detail_th_td_shape():
    html = ("<table><tr><th>Nomor STR</th><td>999888777</td></tr>"
            "<tr><th>Status</th><td>Tidak Aktif</td></tr></table>")
    rec = kki.parse_detail(html, "t")
    assert rec["nomor_str"] == "999888777"
    assert rec["status_str"] == "Tidak Aktif"


def test_parse_detail_missing_fields_are_blank():
    rec = kki.parse_detail("<html>nothing useful</html>", "t")
    assert rec["nomor_str"] == ""
    assert rec["profil_sdmk_url"] == ""
    assert rec["token"] == "t"


# --------------------------------------------------------------------------- #
# JsonlSink: dedupe + resume
# --------------------------------------------------------------------------- #
def test_jsonl_sink_dedupes_and_resumes(tmp_path):
    path = str(tmp_path / "rows.jsonl")

    sink = kki.JsonlSink(path, key="token")
    sink.load()
    assert sink.add({"token": "a", "nama": "X"}) is True
    assert sink.add({"token": "a", "nama": "X"}) is False  # dedupe within run
    assert sink.add({"token": "b", "nama": "Y"}) is True
    sink.close()

    # Reopen: previously written keys are reloaded and treated as seen.
    sink2 = kki.JsonlSink(path, key="token")
    sink2.load()
    assert len(sink2) == 2
    assert "a" in sink2
    assert sink2.add({"token": "a", "nama": "X"}) is False
    assert sink2.add({"token": "c", "nama": "Z"}) is True
    sink2.close()

    lines = [json.loads(l) for l in open(path) if l.strip()]
    tokens = [r["token"] for r in lines]
    assert tokens == ["a", "b", "c"]  # no duplicates on disk


# --------------------------------------------------------------------------- #
# export dedupe logic
# --------------------------------------------------------------------------- #
def test_export_dedupes_by_str_then_token(tmp_path):
    out = str(tmp_path)
    detail = os.path.join(out, "detail_rows.jsonl")
    with open(detail, "w") as f:
        # Same STR under two profession codes -> collapses to one row.
        f.write(json.dumps({"token": "t1", "nama": "A", "nomor_str": "STR1",
                            "profesi": "Dokter"}) + "\n")
        f.write(json.dumps({"token": "t2", "nama": "A", "nomor_str": "STR1",
                            "profesi": "Dokter Spesialis"}) + "\n")
        # Blank STR rows dedupe by token instead.
        f.write(json.dumps({"token": "t3", "nama": "B", "nomor_str": ""}) + "\n")
        f.write(json.dumps({"token": "t3", "nama": "B", "nomor_str": ""}) + "\n")

    kki.export(out, fmt="csv")

    import csv
    with open(os.path.join(out, "kki_physicians.csv")) as f:
        rows = list(csv.DictReader(f))
    tokens = sorted(r["token"] for r in rows)
    assert tokens == ["t1", "t3"]
    assert set(rows[0].keys()) == set(kki.EXPORT_COLUMNS)


def test_backoff_is_bounded_and_nonnegative():
    for attempt in range(10):
        d = kki._fmt_backoff(attempt, base=1.0)
        assert 0 <= d <= kki.BACKOFF_CAP
