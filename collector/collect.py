#!/usr/bin/env python3
"""ADC Census collector (IEEE Xplore API).

Usage (run from anywhere; paths are relative to the repo):
  python3 collector/collect.py              # resume initial sweep, or monthly delta when the sweep is done
  python3 collector/collect.py --reclassify # rebuild data/papers.json from the local cache, no API calls
  python3 collector/collect.py --status     # show sweep progress and quota-related state

The API key is read from the IEEE_API_KEY environment variable (or from
~/.config/adc-census/env, a file containing IEEE_API_KEY=...). It is never
written to disk by this script and is masked in all log output.

Python 3.8+, standard library only.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import classify as C  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, "cache", "raw")          # git-ignored: raw API records incl. abstracts
STATE = os.path.join(DATA, "state.json")
PAPERS = os.path.join(DATA, "papers.json")
META = os.path.join(DATA, "meta.json")
CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venues.json")

API = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
PAGE = 200
SLEEP = 0.25          # standard keys allow 10 calls/s
DEFAULT_MAX_CALLS = 190   # standard keys allow 200 calls/day


class QuotaError(Exception):
    pass


# ------------------------------------------------------------------ utils
def log(*a):
    print("[%s]" % dt.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def today():
    return dt.date.today()


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, obj, compact=False):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def api_key():
    k = os.environ.get("IEEE_API_KEY", "").strip()
    if k:
        return k
    p = os.path.expanduser("~/.config/adc-census/env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.strip().startswith("IEEE_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def mask(s, key):
    return s.replace(key, "***") if key else s


# ------------------------------------------------------------------ API
class Client:
    def __init__(self, key, max_calls):
        self.key = key
        self.max_calls = max_calls
        self.calls = 0

    def search(self, params, start_record, max_records=PAGE):
        if self.calls >= self.max_calls:
            raise QuotaError("max calls for this run reached (%d)" % self.max_calls)
        q = dict(params)
        q.update({"apikey": self.key, "format": "json", "max_records": max_records,
                  "start_record": start_record, "sort_field": "article_number", "sort_order": "asc"})
        url = API + "?" + urllib.parse.urlencode(q)
        last = None
        for attempt in range(4):
            self.calls += 1
            try:
                req = urllib.request.Request(url, headers={"Accept": "application/json",
                                                           "User-Agent": "adc-census/1.0"})
                with urllib.request.urlopen(req, timeout=90) as r:
                    body = r.read().decode("utf-8", "replace")
                time.sleep(SLEEP)
                try:
                    return json.loads(body)
                except ValueError:
                    raise RuntimeError("non-JSON response: " + body[:200])
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", "replace")[:300]
                if e.code in (403, 429) or "over rate" in msg.lower() or "over qps" in msg.lower():
                    if "qps" in msg.lower() or e.code == 429:
                        time.sleep(2 + attempt * 3)
                        last = e
                        continue
                    raise QuotaError("HTTP %d: %s" % (e.code, mask(msg, self.key)))
                if 500 <= e.code < 600:
                    last = e
                    time.sleep(5 * (attempt + 1))
                    continue
                raise RuntimeError("HTTP %d: %s" % (e.code, mask(msg, self.key)))
            except (urllib.error.URLError, TimeoutError) as e:
                last = e
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("request failed after retries: %s" % mask(str(last), self.key))


# ------------------------------------------------------------------ cache
def cache_put(article, run_date):
    an = str(article.get("article_number") or "")
    if not an:
        return False
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, an + ".json")
    old = load_json(path, None)
    article = dict(article)
    article["_first_seen"] = (old or {}).get("_first_seen", run_date)
    save_json(path, article, compact=True)
    return old is None


def iter_cache():
    if not os.path.isdir(CACHE):
        return
    for fn in os.listdir(CACHE):
        if fn.endswith(".json"):
            a = load_json(os.path.join(CACHE, fn), None)
            if a:
                yield a


def fetch_all_pages(client, params, run_date, label, start=1, on_page=None):
    """Page through one query from `start`. Returns (total_records, new_count).
    `on_page(next_start, total)` is called after every page so callers can save progress."""
    total, new = 0, 0
    while True:
        res = client.search(params, start)
        total = int(res.get("total_records") or 0)
        arts = res.get("articles") or []
        for a in arts:
            new += cache_put(a, run_date)
        log("  %-8s records %d-%d / %d" % (label, start, start + len(arts) - 1, total))
        start += PAGE
        if on_page:
            on_page(start, total)
        if not arts or start > total:
            return total, new


# ------------------------------------------------------------------ record building
TEX = [(r"\\Delta", "\u0394"), (r"\\Sigma", "\u03a3"), (r"\\mu", "\u00b5"), (r"\\times", "\u00d7"),
       (r"\\pm", "\u00b1"), (r"\\sim", "~"), (r"\\geq?", "\u2265"), (r"\\leq?", "\u2264"),
       (r"\\Omega", "\u03a9"), (r"\\text\{([^}]*)\}", r"\1"), (r"\\mathrm\{([^}]*)\}", r"\1")]


def clean(s):
    if not s:
        return ""
    s = re.sub(r"<tex-math[^>]*>", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    for a, b in TEX:
        s = re.sub(a, b, s)
    s = s.replace("$", "").replace("{", "").replace("}", "")
    s = s.replace("\\", "")
    return re.sub(r"\s+", " ", s).strip()


def terms_of(a):
    it = a.get("index_terms") or {}
    out = []
    for k in ("ieee_terms", "author_terms", "dynamic_index_terms"):
        v = it.get(k) or {}
        out += v.get("terms") or []
    return [clean(x) for x in out]


def venue_of(pub_title, venues):
    for v in venues:
        if re.search(v["match"], pub_title or "", re.I):
            return v["name"]
    return None


def build_record(a, venues):
    title = clean(a.get("title"))
    if not title or C.NON_PAPER.search(title):
        return None
    pub = clean(a.get("publication_title"))
    venue = venue_of(pub, venues)
    if not venue:
        return None
    abstract = clean(a.get("abstract"))
    terms = terms_of(a)
    kind, level = C.relevance(title, abstract, terms)
    if not kind:
        return None
    arch = C.architectures(title, abstract)
    specs = C.parse_specs(title, abstract)
    authors = sorted((a.get("authors") or {}).get("authors") or [], key=lambda x: x.get("author_order") or 0)
    names, orgs, countries = [], [], []
    for au in authors:
        if au.get("full_name"):
            names.append(clean(au["full_name"]))
        affs = au.get("affiliation")
        if isinstance(affs, str):
            affs = [affs]
        for aff in affs or []:
            org, cn = C.org_and_country(clean(aff))
            if org and org not in orgs:
                orgs.append(org)
            if cn and cn not in countries:
                countries.append(cn)
    year = a.get("publication_year")
    try:
        year = int(year)
    except (TypeError, ValueError):
        year = None
    date = C.parse_month(a.get("publication_date"), year)
    if not year and date[:4].isdigit():
        year = int(date[:4])
    ctype = a.get("content_type") or ""
    rec = {
        "id": str(a.get("article_number")),
        "doi": a.get("doi") or "",
        "t": title,
        "v": venue,
        "vt": pub,
        "y": year,
        "d": date,
        "au": names[:12] + (["et al."] if len(names) > 12 else []),
        "org": orgs[:5],
        "cn": countries,
        "k": kind,
        "lv": level,
        "ar": arch,
        "ap": C.applications(title, abstract),
        "cal": C.has_calibration(title, abstract),
        "s": specs,
        "x": C.derived(specs, arch),
        "ct": "EA" if "early" in ctype.lower() else ("C" if "conf" in ctype.lower() else "J"),
        "url": a.get("html_url") or ("https://doi.org/" + a["doi"] if a.get("doi") else ""),
        "first": a.get("_first_seen", ""),
        "ins": str(a.get("insert_date") or ""),
    }
    return rec


def rebuild(config, run_date, last_run_new_ids=None):
    venues = config["venues"]
    existing = {r["id"]: r for r in load_json(PAPERS, [])}
    from_cache, cached_ids = {}, set()
    for a in iter_cache():
        an = str(a.get("article_number"))
        cached_ids.add(an)
        r = build_record(a, venues)
        if r:
            from_cache[an] = r
    merged = {k: v for k, v in existing.items() if k not in cached_ids}   # keep records we have no cache for
    merged.update(from_cache)
    papers = sorted(merged.values(), key=lambda r: (r.get("d") or "", r["id"]), reverse=True)
    save_json(PAPERS, papers, compact=True)

    state = load_json(STATE, {})
    by_venue, by_kind = {}, {}
    for p in papers:
        by_venue[p["v"]] = by_venue.get(p["v"], 0) + 1
        by_kind[p["k"]] = by_kind.get(p["k"], 0) + 1
    dates = [p["d"] for p in papers if p.get("d")]
    meta = {
        "title": "ADC Census",
        "source": "IEEE Xplore API",
        "updated": run_date,
        "coverage_from": "%d-01" % state.get("since_year", 2023),
        "coverage_to": max(dates) if dates else "",
        "total": len(papers),
        "by_kind": by_kind,
        "by_venue": by_venue,
        "sweep_done": bool((state.get("sweep") or {}).get("done")),
        "last_run_new": sum(1 for p in papers if p.get("first") == run_date),
    }
    save_json(META, meta)
    log("wrote %d papers (%s)" % (len(papers), ", ".join("%s %d" % kv for kv in sorted(by_kind.items()))))
    return meta


# ------------------------------------------------------------------ sweep / delta
def init_sweep(state, config, since_year):
    years = list(range(since_year, today().year + 1))
    state["since_year"] = since_year
    state["sweep"] = {
        "done": False,
        "started": today().isoformat(),
        "tasks": [{"key": q["key"], "year": y, "done": False} for q in config["queries"] for y in years],
    }


def query_params(q, state):
    variant = (state.get("variant") or {}).get(q["key"], "params")
    if variant == "fallback" and q.get("fallback"):
        return dict(q["fallback"]), variant
    return dict(q["params"]), "params"


def run_sweep(client, state, config, run_date):
    qmap = {q["key"]: q for q in config["queries"]}
    for task in state["sweep"]["tasks"]:
        if task["done"]:
            continue
        q = qmap.get(task["key"])
        if not q:
            task["done"] = True
            continue
        params, variant = query_params(q, state)
        params.update({"start_year": task["year"], "end_year": task["year"]})

        def progress(nxt, tot, task=task):
            task["next"] = nxt
            save_json(STATE, state)

        log("sweep %s %d (%s)" % (task["key"], task["year"], variant))
        total, new = fetch_all_pages(client, params, run_date, task["key"], task.get("next", 1), progress)
        verified = (state.get("verified") or {}).get(task["key"])
        if total == 0 and variant == "params" and q.get("fallback") and not verified:
            log("  no records via %s; switching %s to fallback query" % (json.dumps(q["params"]), task["key"]))
            state.setdefault("variant", {})[task["key"]] = "fallback"
            task["next"] = 1
            save_json(STATE, state)
            params, _ = query_params(q, state)
            params.update({"start_year": task["year"], "end_year": task["year"]})
            total, new = fetch_all_pages(client, params, run_date, task["key"], 1, progress)
        if total > 0:
            state.setdefault("verified", {})[task["key"]] = True   # this query form works; never switch it later
        else:
            log("  WARNING: %s %d returned no records - check collector/venues.json" % (task["key"], task["year"]))
        task["done"] = True
        task["total"] = total
        save_json(STATE, state)
    state["sweep"]["done"] = True
    # deltas continue from the day the sweep started (covers insertions during a multi-day sweep)
    state["last_delta_end"] = state["sweep"]["started"].replace("-", "")
    save_json(STATE, state)
    log("initial sweep complete")


def run_delta(client, state, config, run_date, overlap_days):
    end = today()
    if state.get("last_delta_end"):
        start = dt.datetime.strptime(state["last_delta_end"], "%Y%m%d").date() - dt.timedelta(days=overlap_days)
    else:
        start = end - dt.timedelta(days=45)
    s, e = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    log("delta: IEEE insert date %s .. %s" % (s, e))
    for q in config["queries"]:
        params, _ = query_params(q, state)
        params.update({"start_date": s, "end_date": e})
        fetch_all_pages(client, params, run_date, q["key"])
    state["last_delta_end"] = e
    save_json(STATE, state)


# ------------------------------------------------------------------ diagnostics
def probe(client, config):
    """One API call: checks key, network and which fields the API returns."""
    q = config["queries"][0]
    params, _ = query_params(q, load_json(STATE, {}))
    y = today().year - 1
    params.update({"start_year": y, "end_year": y})
    res = client.search(params, 1, max_records=2)
    print("query:", json.dumps(params, ensure_ascii=False))
    print("total_records:", res.get("total_records"))
    arts = res.get("articles") or []
    if not arts:
        print("no articles returned")
        return 1
    a = arts[0]
    print("title:", clean(a.get("title")))
    print("publication_title:", clean(a.get("publication_title")))
    for f in ("article_number", "doi", "publication_date", "publication_year", "insert_date",
              "content_type", "abstract", "index_terms", "authors", "html_url"):
        print("  %-18s %s" % (f, "present" if a.get(f) else "MISSING"))
    au = ((a.get("authors") or {}).get("authors") or [{}])[0]
    print("  %-18s %s" % ("affiliation", "present" if au.get("affiliation") else "MISSING"))
    return 0


def report(config, sample=15):
    """Human-readable check of venue matching, classification and spec coverage (no API calls)."""
    import random
    venues = config["venues"]
    pubs, n, suspects = {}, 0, []
    for a in iter_cache():
        n += 1
        pub = clean(a.get("publication_title"))
        pubs[pub] = pubs.get(pub, 0) + 1
        title = clean(a.get("title"))
        if venue_of(pub, venues) and title and not C.NON_PAPER.search(title):
            kind, _ = C.relevance(title, clean(a.get("abstract")), terms_of(a))
            if not kind and re.search(r"convert|quantiz|digitiz|modulator|sampl", title, re.I):
                suspects.append(title)
    print("cached IEEE records: %d" % n)
    print("\npublication titles in cache (count, venue it maps to):")
    for pub, c in sorted(pubs.items(), key=lambda kv: -kv[1])[:80]:
        print("  %6d  %-8s  %s" % (c, venue_of(pub, venues) or "DROPPED", pub[:110]))

    papers = load_json(PAPERS, [])
    years = sorted({p["y"] for p in papers if p.get("y")})
    table = {}
    for p in papers:
        if p.get("lv") != "core" or not p.get("y"):
            continue
        cell = table.setdefault(p["v"], {}).setdefault(p["y"], [0, 0])
        cell[0 if p["k"] == "ADC" else 1] += 1
    print("\ncore papers by venue and year (ADC/DAC):")
    print("  %-8s" % "" + "".join("%10s" % y for y in years))
    for v in sorted(table):
        print("  %-8s" % v + "".join("%10s" % ("%d/%d" % tuple(table[v].get(y, [0, 0]))) for y in years))

    core = [p for p in papers if p.get("lv") == "core" and p["k"] == "ADC"]
    if core:
        def pct(f):
            return "%d%%" % round(100.0 * sum(1 for p in core if f(p)) / len(core))
        print("\nspec coverage over %d core ADC papers: fs %s, SNDR %s, power %s, node %s, "
              "on energy plot %s, architecture tagged %s" % (
                  len(core), pct(lambda p: "fs" in p["s"]), pct(lambda p: "sndr" in p["s"]),
                  pct(lambda p: "p" in p["s"]), pct(lambda p: "node" in p["s"]),
                  pct(lambda p: p.get("x", {}).get("e_nyq") and p["s"].get("sndr")), pct(lambda p: p["ar"])))
        print("\nrandom core ADC papers (check that they really are ADC papers and the tags fit):")
        for p in random.Random(0).sample(core, min(sample, len(core))):
            print("  - [%s %s] %s  {%s}" % (p["v"], p["y"], p["t"][:120], ", ".join(p["ar"]) or "no arch"))
    print("\nnot classified as ADC/DAC although the title mentions conversion, modulator or sampling "
          "(%d, first 25) - check for misses:" % len(suspects))
    for t in suspects[:25]:
        print("  - " + t[:140])
    sw = load_json(STATE, {}).get("sweep") or {}
    zero = ["%s %s" % (t["key"], t["year"]) for t in sw.get("tasks", []) if t.get("done") and not t.get("total")]
    if zero:
        print("\nsweep tasks that returned 0 records (query in venues.json may be wrong):", ", ".join(zero))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since-year", type=int, default=2023, help="first publication year of the initial sweep")
    ap.add_argument("--restart-sweep", action="store_true", help="start the initial sweep over")
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS, help="API call budget for this run")
    ap.add_argument("--overlap-days", type=int, default=7, help="delta window overlap with the previous run")
    ap.add_argument("--min-interval-days", type=int, default=0,
                    help="skip the delta update if the previous one is more recent than this (lets cron run daily)")
    ap.add_argument("--reclassify", action="store_true", help="rebuild papers.json from cache only (no API)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--probe", action="store_true", help="one API call to check key, network and returned fields")
    ap.add_argument("--report", action="store_true", help="check venue matching and classification (no API)")
    args = ap.parse_args()

    os.makedirs(DATA, exist_ok=True)
    config = load_json(CONFIG, None)
    state = load_json(STATE, {})
    run_date = today().isoformat()

    if args.status:
        sw = state.get("sweep") or {}
        tasks = sw.get("tasks") or []
        print("sweep: %s, %d/%d tasks done" % ("done" if sw.get("done") else "in progress",
                                                sum(t["done"] for t in tasks), len(tasks)))
        print("last delta end:", state.get("last_delta_end"))
        print("query variants:", state.get("variant") or {})
        return 0

    if args.reclassify:
        rebuild(config, run_date)
        return 0
    if args.report:
        return report(config)

    key = api_key()
    if not key:
        log("ERROR: IEEE_API_KEY is not set (env var or ~/.config/adc-census/env)")
        return 2

    if args.probe:
        try:
            return probe(Client(key, 3), config)
        except (QuotaError, RuntimeError) as e:
            log("probe failed: %s" % e)
            return 1

    if args.restart_sweep or "sweep" not in state or state.get("since_year") != args.since_year and not state["sweep"]["done"]:
        init_sweep(state, config, args.since_year)
        save_json(STATE, state)

    if state["sweep"]["done"] and args.min_interval_days and state.get("last_delta_end"):
        last = dt.datetime.strptime(state["last_delta_end"], "%Y%m%d").date()
        if (today() - last).days < args.min_interval_days:
            log("last update %s is less than %d days ago; nothing to do" % (last, args.min_interval_days))
            return 0

    client = Client(key, args.max_calls)
    status = 0
    try:
        if not state["sweep"]["done"]:
            run_sweep(client, state, config, run_date)
        else:
            run_delta(client, state, config, run_date, args.overlap_days)
    except QuotaError as e:
        log("stopped: %s - progress saved; the next run resumes from here" % e)
        status = 3
    finally:
        log("API calls used: %d" % client.calls)
        rebuild(config, run_date)
    return status


if __name__ == "__main__":
    sys.exit(main())
