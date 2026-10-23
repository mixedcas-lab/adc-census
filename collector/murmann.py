#!/usr/bin/env python3
"""Import B. Murmann's ADC Performance Survey (ISSCC & VLSI, BSD-3-Clause) for the site's plots.

Usage:
  python3 collector/murmann.py            # download the latest spreadsheet if the local copy is >7 days old
  python3 collector/murmann.py --force    # download now
  python3 collector/murmann.py --file X   # convert a local .xlsx

Writes data/murmann.json with bibliographic fields and performance numbers only. The
spreadsheet's ABSTRACT column is never copied. Python 3.8+, standard library only.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "murmann.json")
LOCAL = os.path.join(ROOT, "cache", "murmann", "ADCsurvey_latest.xlsx")   # git-ignored
URL = "https://raw.githubusercontent.com/bmurmann/ADC-survey/main/xls/ADCsurvey_latest.xlsx"
MAX_AGE_DAYS = 7

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# spreadsheet header -> short key in murmann.json
NUMERIC = {
    "SNDR_plot [dB]": "sndr", "SNDR_lf [dB]": "sndr_lf", "SNDR_hf [dB]": "sndr_hf", "fin_hf [Hz]": "fin",
    "SNR [dB]": "snr", "DR [dB]": "dr", "SFDR [dB]": "sfdr", "P [W]": "p", "fs [Hz]": "fs", "OSR": "osr",
    "fsnyq [Hz]": "fsnyq", "P/fsnyq [pJ]": "e_pj", "FOMW_hf [fJ/conv-step]": "fomw", "FOMS_hf [dB]": "foms",
    "FOMS_lf [dB]": "foms_lf", "AREA [mm^2]": "area", "VSUP1 [V]": "vdd",
}

ARCH_MAP = [  # (regex on the survey's ARCHITECTURE cell, census tag)
    (r"\bTI\b", "TI"),
    (r"\bSDCT\b", "CT-ΔΣ"),
    (r"\bSD(?:SC|DT)\b", "ΔΣ"),
    (r"\bIncremental\b|Ext\. Counting", "Incremental"),
    (r"\bVCO\b|Time-based|\bTDC\b", "VCO/Time-domain"),
    (r"\bFlash\b", "Flash"),
    (r"\bFolding\b", "Folding"),
    (r"Two-step|Subranging", "Subranging"),
    (r"Single-slope", "Single-slope"),
]

LICENSE = ("ADC Performance Survey, Copyright (c) 2022, Boris Murmann. BSD 3-Clause License, "
           "https://github.com/bmurmann/ADC-survey/blob/main/LICENSE")
CITATION = 'B. Murmann, "ADC Performance Survey 1997-%d," [Online]. Available: https://github.com/bmurmann/ADC-survey.'


def read_sheets(path, names):
    """Rows of the named worksheets as lists of {column letter: text}."""
    z = zipfile.ZipFile(path)
    try:
        strings = ["".join(t.itertext()) for t in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(M + "si")]
    except KeyError:
        strings = []
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = {}
    for s in ET.fromstring(z.read("xl/workbook.xml")).iter(M + "sheet"):
        if s.get("name") not in names:
            continue
        target = rels[s.get(R + "id")].lstrip("/")
        target = target if target.startswith("xl/") else "xl/" + target
        rows = []
        for r in ET.fromstring(z.read(target)).iter(M + "row"):
            row = {}
            for c in r.iter(M + "c"):
                col = re.match(r"[A-Z]+", c.get("r")).group(0)
                t, v = c.get("t"), c.find(M + "v")
                if t == "inlineStr":
                    row[col] = "".join(c.find(M + "is").itertext())
                elif v is not None and v.text is not None:
                    row[col] = strings[int(v.text)] if t == "s" else v.text
            rows.append(row)
        out[s.get("name")] = rows
    return out


def num(s):
    try:
        v = float(str(s).strip())
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def sig(v, n=5):
    return float("%.*g" % (n, v))


def arch_tags(cell):
    cell = cell or ""
    tags = [tag for rx, tag in ARCH_MAP if re.search(rx, cell, re.I)]
    pipe, sar = re.search(r"\bPipe", cell, re.I), re.search(r"\bSAR\b", cell, re.I)
    if pipe and sar:
        tags.insert(1 if "TI" in tags else 0, "Pipelined-SAR")
    elif pipe:
        tags.append("Pipelined")
    elif sar:
        tags.append("SAR")
    return tags


def node_nm(cell):
    m = re.match(r"\s*(\d*\.?\d+(?:E-?\d+)?)", cell or "", re.I)   # TECHNOLOGY is in µm ("0.18", "2.8E-2", "0.35 BiCMOS")
    if not m:
        return None
    v = float(m.group(1)) * 1000
    return int(round(v)) if 1 <= v <= 5000 else None


def convert(path):
    sheets = read_sheets(path, ("ISSCC", "VLSI"))
    rows = []
    for conf in ("ISSCC", "VLSI"):
        table = sheets.get(conf) or []
        if not table:
            continue
        head = {col: name.strip() for col, name in table[0].items()}
        for raw in table[1:]:
            r = {head.get(col, col): val for col, val in raw.items()}
            year = num(r.get("YEAR"))
            if not year:
                continue
            rec = {"c": conf, "y": int(year), "sid": (r.get("ID") or "").strip(), "type": (r.get("TYPE") or "").strip(),
                   "arch": (r.get("ARCHITECTURE") or "").strip(), "ar": arch_tags(r.get("ARCHITECTURE")),
                   "t": re.sub(r"\s+", " ", r.get("TITLE") or "").strip(),
                   "au": re.sub(r"\s+", " ", r.get("AUTHORS") or "").strip(), "doi": (r.get("DOI") or "").strip()}
            node = node_nm(r.get("TECHNOLOGY"))
            if node:
                rec["node"] = node
            for col, key in NUMERIC.items():
                v = num(r.get(col))
                if v is not None:
                    rec[key] = sig(v)
            # empty cells show up as 1 dB / 1e10 pJ placeholders; values derived from power need P
            for key in ("sndr", "sndr_lf", "sndr_hf", "snr", "dr", "sfdr", "foms", "foms_lf"):
                if rec.get(key, 99) <= 1:
                    rec.pop(key)
            if "p" not in rec:
                for key in ("e_pj", "fomw", "foms", "foms_lf"):
                    rec.pop(key, None)
            rows.append(rec)
    if not rows:
        raise ValueError("no ISSCC/VLSI rows found in " + path)
    ymax = max(r["y"] for r in rows)
    return {"source": "https://github.com/bmurmann/ADC-survey", "license": LICENSE, "citation": CITATION % ymax,
            "imported": dt.date.today().isoformat(), "years": [min(r["y"] for r in rows), ymax], "rows": rows}


def download(dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": "adc-census/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        body = r.read()
    if not body.startswith(b"PK"):
        raise RuntimeError("downloaded file is not an .xlsx")
    tmp = dest + ".tmp"
    with open(tmp, "wb") as f:
        f.write(body)
    os.replace(tmp, dest)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="download even if the local copy is recent")
    ap.add_argument("--file", help="convert this local .xlsx instead of downloading")
    args = ap.parse_args()
    path = args.file or LOCAL
    if not args.file:
        age = (time.time() - os.path.getmtime(LOCAL)) / 86400 if os.path.exists(LOCAL) else None
        if args.force or age is None or age > MAX_AGE_DAYS:
            try:
                download(LOCAL)
            except Exception as e:   # keep the previous data/murmann.json when GitHub is unreachable
                print("murmann: download failed (%s)" % e)
                if not os.path.exists(LOCAL):
                    return 1
    data = convert(path)
    old = None
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f)
    if old and old.get("rows") == data["rows"]:
        print("murmann: unchanged (%d designs)" % len(data["rows"]))
        return 0
    with open(OUT + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    os.replace(OUT + ".tmp", OUT)
    print("murmann: wrote %d designs, %d-%d" % (len(data["rows"]), data["years"][0], data["years"][1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
