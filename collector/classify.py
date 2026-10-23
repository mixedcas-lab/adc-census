"""Classification and spec extraction for ADC/DAC papers.

Everything here is pure (no network) so it can be unit-tested and re-run
over the local cache (`collect.py --reclassify`) whenever the rules change.
Abstracts are used only as input; they are never written to the output.
"""
import math
import re

I = re.IGNORECASE

# ---------------------------------------------------------------- relevance
ADC_PAT = re.compile(
    r"(?-i:\bADCs?\b)|analog(?:ue)?[- ]to[- ]digital|\bA/D\b|"   # case-sensitive: "ADCS" is attitude control
    r"\b(?:delta|sigma)\s*[-–—]?\s*(?:sigma|delta)\b|[ΔΣ∑]\s?[ΔΣ∑]|\b(?:CT|DT|I)?(?:DSM|SDM)s?\b|"
    r"successive[- ]approximation|\bSAR\b|"
    r"noise[- ]shaping|time[- ]interleav|"
    r"(?:capacitance|resistance|inductance|impedance|light)[- ]to[- ]digital", I)
DAC_PAT = re.compile(r"\bDACs?\b|digital[- ]to[- ]analog", I)

# Strong context words that confirm a weak hit (e.g. "SAR", "noise-shaping")
CONVERTER_CTX = re.compile(r"\bADC|conver[st]|modulator|quantiz|\bSNDR\b|\bENOB\b|\bCT\b|[GMk]S/s", I)

# Converter used inside a compute-in-memory / AI macro: keep as "related", not "core"
# PLL / power papers often name their internal DAC or ADC; not converter papers by themselves
PLL_OR_POWER = re.compile(r"\b(?:AD|D)?PLLs?\b|fractional[- ]N|DC[- ]DC|buck|boost converter|power converter", I)

# Other meanings of "ADC" (antibody-drug conjugate, MRI apparent diffusion coefficient, satellite ADCS)
OTHER_ADC = re.compile(r"antibody|drug conjugate|diffusion coefficient|diffusion[- ]weighted|attitude determination", I)

# "ADC-less" / "ADC/DAC-free" designs are not converter papers
NO_CONVERTER = re.compile(r"\b(?:ADC|DAC)(?:/(?:ADC|DAC))?s?[- ](?:free|less)\b", I)

CIM_CTX = re.compile(r"in[- ]memory|\bCIM\b|\bIMC\b|compute[- ]in|computing[- ]in|neuromorphic", I)

NEGATIVE_CTX = re.compile(
    r"synthetic[- ]aperture|specific absorption rate|"
    r"fractional[- ]N|frequency synthes|\b(?:AD|D)?PLLs?\b|"
    r"DC[- ]DC|buck|boost converter|power converter", I)

# IEEE controlled terms that are a reliable "this is an ADC paper" signal
ADC_TERMS = re.compile(r"^analog[- ]digital conversion$|^analog-to-digital", I)
DAC_TERMS = re.compile(r"^digital[- ]analog conversion$|^digital-to-analog", I)

NON_PAPER = re.compile(
    r"^(front cover|back cover|table of contents|contents|author index|index|"
    r"call for papers|editorial|guest editorial|reviewers|session \d+ overview|"
    r"(?:tutorials?|short course|evening (?:event|session)|forum|panel)(?=\s*:|\s*$)|"
    r"(ieee )?(transactions|journal) .*information|blank page|copyright)\b", I)


def _adc_hit(text):
    if not text:
        return False
    text = NO_CONVERTER.sub(" ", text)
    if OTHER_ADC.search(text):
        return False
    if NEGATIVE_CTX.search(text) and not re.search(r"\bADC|analog(?:ue)?[- ]to[- ]digital", text, I):
        return False
    m = ADC_PAT.search(text)
    if not m:
        return False
    tok = m.group(0).lower()
    weak = tok in ("sar", "sdm", "sdms") or tok.startswith("noise") or tok.startswith("time") or tok == "dsm" or tok == "dsms"
    if weak:
        return bool(CONVERTER_CTX.search(text))
    return True


def relevance(title, abstract, terms):
    """Return (kind, level): kind in {ADC, DAC, None}, level in {core, related}.
    `terms` should be author keywords; IEEE's automatic index terms tag many CIM/PLL/DC-DC papers."""
    t_adc = _adc_hit(title)
    t_dac = bool(DAC_PAT.search(NO_CONVERTER.sub(" ", title or "")))
    term_adc = any(ADC_TERMS.search(x) for x in terms)
    term_dac = any(DAC_TERMS.search(x) for x in terms)
    if PLL_OR_POWER.search(title or "") and not re.search(r"\bADC|analog[- ]to[- ]digital|digital[- ]to[- ]analog", title or "", I):
        t_dac = term_adc = term_dac = False   # a PLL/DC-DC paper that mentions its internal DAC or ADC
    if (t_adc or t_dac or term_adc or term_dac) and CIM_CTX.search(title or ""):
        return ("ADC" if t_adc or term_adc else "DAC"), "related"
    if t_adc:
        return "ADC", "core"
    if t_dac:
        return "DAC", "core"
    if term_adc:
        return "ADC", "core"
    if term_dac:
        return "DAC", "core"
    if _adc_hit(abstract):
        return "ADC", "related"
    return None, None


# ------------------------------------------------------------- architecture
ARCH_RULES = [
    ("TI",            r"time[- ]interleav|\bTI[- ]?(?:ADC|SAR|DAC)s?\b|\b\d+[- ]?(?:channel|way|x)\b.*interleav|interleaved"),
    ("Pipelined-SAR", r"pipelined?[- ]SAR|pipeline[- ]SAR|pipe[- ]SAR|SAR[- ]assisted pipeline"),
    ("Pipelined",     r"pipelin(?:e|ed)\b"),
    ("NS-SAR",        r"noise[- ]shaping\s+SAR|\bNS[- ]?SAR\b|noise[- ]shaped\s+SAR"),
    ("SAR",           r"\bSAR\b|successive[- ]approximation"),
    ("CT-ΔΣ",   r"continuous[- ]time.*(?:delta|sigma|[ΔΣ]|modulator|\bDSM)|\bCT[- ]?(?:Δ\s?Σ|Σ\s?Δ|DSM|SDM|DSADC|delta|sigma)"),
    ("ΔΣ",      r"\b(?:delta|sigma)\s*[-–—]?\s*(?:sigma|delta)\b|[ΔΣ∑]\s?[ΔΣ∑]|\b(?:DT)?(?:DSM|SDM)\b|oversampl"),
    ("Incremental",   r"incremental"),
    ("Zoom",          r"\bzoom"),
    ("VCO/Time-domain", r"VCO[- ]based|ring[- ]oscillator|time[- ]domain|\bTD[- ]?ADC|voltage[- ]to[- ]time|\bVTC\b|time[- ]based|\bTDC[- ]based|\bVCO\b"),
    ("Flash",         r"\bflash\b(?![- ]memory)"),
    ("Subranging",    r"sub[- ]?rang|two[- ]step|multi[- ]step"),
    ("Single-slope",  r"single[- ]slope|\bramp\b|column[- ]parallel"),
    ("Folding",       r"folding|interpolat"),
    ("Current-steering", r"current[- ]steering"),
    ("RF-DAC",        r"\bRF[- ]?DAC|direct[- ]digital[- ]RF|digital[- ]to[- ]RF"),
]
ARCH_RX = [(n, re.compile(p, I)) for n, p in ARCH_RULES]


def architectures(title, abstract):
    def scan(text):
        found = []
        for name, rx in ARCH_RX:
            if rx.search(text or ""):
                found.append(name)
        # collapse redundant tags
        if "Pipelined-SAR" in found:
            found = [f for f in found if f not in ("Pipelined", "SAR")]
        if "NS-SAR" in found and "SAR" in found:
            found.remove("SAR")
        if "CT-ΔΣ" in found and "ΔΣ" in found:
            found.remove("ΔΣ")
        return found
    tags = scan(title)
    if not tags and abstract:
        # only the first sentence ("This article presents a ... ADC"); later ones compare with other architectures
        first = re.split(r"(?<=[.!?])\s+", abstract)[0]
        tags = scan(first)
    return tags


# ------------------------------------------------------------- application
APP_RULES = [
    ("Wireline/SerDes", r"wireline|serdes|\bPAM[- ]?\d|Gb/s|optical|coherent|transceiver|\bDSP[- ]based receiver|ADC[- ]based (?:receiver|RX)"),
    ("Wireless/RF",     r"\b[56]G\b|wireless|RF[- ]sampling|direct[- ]RF|mm-?wave|radar|software[- ]defined|baseband|cellular|\bLTE\b|Wi-?Fi|satellite"),
    ("Biomedical",      r"\bbio|neural (?:record|interface|implant|signal)|\bECG\b|\bEEG\b|\bExG\b|implant|brain|wearable|health|neuro"),
    ("Image sensor",    r"image sensor|\bCIS\b|pixel|imager|\bSPAD\b|lidar"),
    ("Sensor interface",r"sensor (?:interface|readout)|readout|bridge|capacitance[- ]to[- ]digital|resistance[- ]to[- ]digital|temperature sens|thermistor|\bMEMS\b|strain|gyro|accelerom"),
    ("Audio",           r"audio|microphone|hearing"),
    ("Memory/Storage",  r"\bNAND\b|flash memory|\bDRAM\b|\bSSD\b|storage|\bHBM\b"),
    ("CIM/AI",          r"in[- ]memory|\bCIM\b|neural network|\bDNN\b|\bCNN\b|accelerator|machine learning|inference|\bAI\b"),
    ("Automotive",      r"automotive|vehicle|in-vehicle|ethernet"),
]
APP_RX = [(n, re.compile(p, I)) for n, p in APP_RULES]
CAL_RX = re.compile(r"calibrat|\bLMS\b|\bRLS\b|mismatch[- ]shaping|\bDEM\b|dither|background (?:correction|estimation)", I)


def applications(title, abstract):
    text = (title or "") + " " + (abstract or "")
    return [n for n, rx in APP_RX if rx.search(text)]


def has_calibration(title, abstract):
    return bool(CAL_RX.search((title or "") + " " + (abstract or "")))


# ------------------------------------------------------------- spec parsing
NUM = r"(\d+(?:\.\d+)?)"
_SI = {"a": 1e-18, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6,
       "m": 1e-3, "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}

FS_RX = re.compile(NUM + r"\s*-?\s*([kKMGT])\s*(?:S|Sa|[Ss]amples?)\s*/\s*(?:s|sec)\b|" + NUM + r"\s*-?\s*([kKMGT])(?:sps|SPS)\b")
# sample/clock rate given in Hz: "sampled at 630 MHz", "a 48-MHz sample rate", "clocked at 576 MHz"
FS_HZ_RX = re.compile(r"(?:sampled|sampling(?:\s+rate|\s+frequency)?|sample[- ]rate|clocked|clock(?:ing)?\s+(?:rate|frequency))\s*(?:of|at|=|is)?\s*"
                      r"(?:up to\s+)?" + NUM + r"\s*-?\s*([kKMG])Hz|" + NUM + r"\s*-?\s*([kKMG])Hz\s+(?:sampl(?:e|ing)[- ]rate|clock)", I)
RES_RX = re.compile(r"(?<![\w.\-/])(\d{1,2})(?:\.\d+)?\s*-?\s*(?:b|bit|bits)(?![\w/])", I)
NODE_NM_RX = re.compile(r"(?<![\w.])(\d{1,3})\s*-?\s*nm\b", I)
NODE_UM_RX = re.compile(r"(?<![\w.])(0\.\d{1,3})\s*-?\s*[µμu]m\b|(?<![\w.])([1-3](?:\.\d)?)\s*-?\s*[µμu]m\s+(?:\w+\s+){0,2}"
                        r"(?:CMOS|BiCMOS|process|technology|SOI|bipolar|InP|SiGe|GaAs)", I)
_GAP = r"(?:(?!SFDR|SNDR|\bSNR\b|\bDR\b|THD|dynamic range|signal-to)[^.;\d]){0,25}?"
_SNDR_WORDS = r"(?:SNDR|S/\(?N\s*\+\s*D\)?|SINAD|signal[- ]to[- ]noise[- ]?(?:and|plus|\+)?[- ]?distortion(?:[- ]ratio)?)"
SNDR_RX = [
    re.compile(_SNDR_WORDS + r"(?:\s*\((?:SNDR|SINAD)\))?" + _GAP + NUM + r"\s*-?\s*dB", I),
    re.compile(NUM + r"\s*-?\s*dB[- ](?:peak[- ])?" + _SNDR_WORDS, I),
    re.compile(NUM + r"\s*-?\s*dB\s+(?:of\s+)?(?:peak\s+)?" + _SNDR_WORDS, I),
]
_SNR_WORDS = r"(?:\bSNR\b|signal[- ]to[- ]noise[- ]ratio(?![- ]?(?:and|plus|\+)))"
SNR_RX = [
    re.compile(_SNR_WORDS + r"(?:\s*\(SNR\))?" + _GAP + NUM + r"\s*-?\s*dB", I),
    re.compile(NUM + r"\s*-?\s*dB[- ](?:peak[- ])?" + _SNR_WORDS, I),
    re.compile(NUM + r"\s*-?\s*dB\s+(?:of\s+)?(?:peak\s+)?" + _SNR_WORDS, I),
]
_DR_WORDS = r"(?:\bDR\b|dynamic[- ]range)"
DR_RX = [
    re.compile(_DR_WORDS + r"(?:\s*\(DR\))?" + _GAP + NUM + r"\s*-?\s*dB", I),
    re.compile(NUM + r"\s*-?\s*dB[- ]?(?:A[- ])?" + _DR_WORDS, I),
]
ENOB_RX = re.compile(r"ENOB[^.;\d]{0,20}?" + NUM + r"\s*-?\s*(?:b|bit)", I)
POWER_VAL = NUM + r"\s*-?\s*([nuµμm]?)W\b"
POWER_CTX_RX = re.compile(r"(?:consum\w*|dissipat\w*|power(?:\s+consumption)?|draw(?:s|ing)|burns?)[^.;]{0,40}?" + POWER_VAL, I)
# value first: "270-mW power dissipation", "1.0 W of power", "79.3-μW power"
POWER_AFTER_RX = re.compile(POWER_VAL + r"\s*(?:of\s+)?(?:total\s+|overall\s+|analog\s+)?(?:power|consumption|dissipation)", I)
POWER_ANY_RX = re.compile(POWER_VAL)
BW_RX = re.compile(r"(?<!resolution )(?:signal[- ]band(?:width)?|bandwidth|\bBW\b)(?!\s+mismatch)[^.;\d]{0,20}?" + NUM + r"\s*-?\s*([kKMG]?)Hz|"
                   + NUM + r"\s*-?\s*([kKMG]?)Hz\s+(?:(?:audio|signal|input|LTE|channel|conversion|baseband|RF|IF)\s+){0,2}(?:bandwidth|BW|signal[- ]band)\b", I)
# OCR leftovers in older records: "58. 5dB", "4. 15mW"; "0.18 mum", "870 muW"
_FIXES = [(re.compile(r"(\d)\.\s(\d)"), r"\1.\2"), (re.compile(r"(\d)\s*-?\s*mu(m|W|A|V|s)\b"), r"\1 µ\2"),
          (re.compile(r"([µμ])\s+m\b"), r"\1m")]
# several metrics with their values in one breath: "SFDR/SNDR of 75.2/62.4 dB",
# "the SNDR and SFDR are 55 dB and 69 dB, respectively"
_METRIC = r"(SNDR|SNR|SFDR|DR|THD|SINAD)"
LIST_SLASH_RX = re.compile(r"\b" + _METRIC + r"((?:\s*/\s*" + _METRIC + r")+)\s*(?:of|=|:|are|is|were|reach\w*)?\s*"
                           r"(-?\d+(?:\.\d+)?(?:\s*/\s*-?\d+(?:\.\d+)?)+)\s*-?\s*dB", I)
LIST_AND_RX = re.compile(r"\b" + _METRIC + r"\s+and\s+(?:an?\s+|the\s+)?" + _METRIC + r"\s*(?:of|are|were|is|=)\s*"
                         r"(-?\d+(?:\.\d+)?)\s*-?\s*dBc?\s*(?:and|,)\s*(-?\d+(?:\.\d+)?)\s*-?\s*dB", I)


def _metric_lists(text):
    found = {}
    for m in LIST_SLASH_RX.finditer(text):
        names = [m.group(1)] + re.findall(_METRIC, m.group(2), I)
        vals = re.findall(r"-?\d+(?:\.\d+)?", m.group(4))
        if len(names) == len(vals):
            for n, v in zip(names, vals):
                found.setdefault(n.upper().replace("SINAD", "SNDR"), float(v))
    for m in LIST_AND_RX.finditer(text):
        found.setdefault(m.group(1).upper().replace("SINAD", "SNDR"), float(m.group(3)))
        found.setdefault(m.group(2).upper().replace("SINAD", "SNDR"), float(m.group(4)))
    return found


def _norm(text):
    for rx, rep in _FIXES:
        text = rx.sub(rep, text)
    return text
FOMS_RX = re.compile(r"(?:FoM|figure[- ]of[- ]merit)\s*[_ ]?(?:S|SNDR|DR|Schreier)?[^.;\d]{0,30}?(1[4-9]\d(?:\.\d+)?)\s*-?\s*dB", I)
FOMW_RX = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*([afp])J\s*/\s*conv", I)


def _earliest(rxs, text, lo, hi):
    """The in-range value whose match starts first in the text, over all patterns ("74.1-dB SNDR, 83.4-dB SFDR")."""
    best = None
    for rx in rxs:
        for m in rx.finditer(text):
            if lo <= float(m.group(1)) <= hi:
                if best is None or m.start() < best.start():
                    best = m
                break
    return float(best.group(1)) if best else None


def parse_specs(title, abstract):
    t = _norm(title or "")
    a = _norm(abstract or "")
    both = t + " . " + a
    out = {}

    m = FS_RX.search(t) or FS_RX.search(a) or FS_HZ_RX.search(t) or FS_HZ_RX.search(a)
    if m:
        val, pre = next((m.group(i), m.group(i + 1)) for i in range(1, m.re.groups, 2) if m.group(i))
        out["fs"] = float(val) * _SI[pre if pre != "K" else "k"]

    m = RES_RX.search(t) or RES_RX.search(a)
    if m:
        r = int(m.group(1))
        if 3 <= r <= 24:
            out["res"] = r

    m = NODE_NM_RX.search(t) or NODE_NM_RX.search(a)
    if m and 2 <= int(m.group(1)) <= 500:
        out["node"] = int(m.group(1))
    else:
        m = NODE_UM_RX.search(t) or NODE_UM_RX.search(a)
        if m:
            out["node"] = int(round(float(m.group(1) or m.group(2)) * 1000))

    v = _earliest(SNDR_RX, both, 10, 130)
    if v is not None:
        out["sndr"] = v
    if "sndr" not in out:
        m = ENOB_RX.search(both)
        if m:
            out["enob"] = float(m.group(1))
    for key, rxs in (("snr", SNR_RX), ("dr", DR_RX)):
        v = _earliest(rxs, both, 10, 150)
        if v is not None:
            out[key] = v
    for name, v in _metric_lists(both).items():
        key = {"SNDR": "sndr", "SNR": "snr", "DR": "dr"}.get(name)
        if key and key not in out and 10 <= v <= 150:
            out[key] = v

    m = POWER_CTX_RX.search(a) or POWER_AFTER_RX.search(a) or POWER_CTX_RX.search(t) or POWER_ANY_RX.search(t)
    if m:
        out["p"] = float(m.group(1)) * _SI[m.group(2) or ""]

    m = BW_RX.search(both)
    if m:
        val, pre = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        out["bw"] = float(val) * _SI[pre if pre != "K" else "k"]

    m = FOMS_RX.search(both)
    if m:
        out["foms"] = float(m.group(1))
    m = FOMW_RX.search(both)
    if m:
        out["fomw"] = float(m.group(1)) * _SI[m.group(2).lower()] / 1e-15  # in fJ/conv
    return out


def derived(specs, arch):
    """Nyquist-equivalent energy and Schreier FoM when not reported."""
    oversampled = any(a in ("ΔΣ", "CT-ΔΣ", "NS-SAR", "Incremental", "Zoom") for a in arch)
    bw = specs.get("bw")
    if not bw and not oversampled and specs.get("fs"):
        bw = specs["fs"] / 2.0
    d = {}
    if bw and specs.get("p"):
        d["e_nyq"] = specs["p"] / (2.0 * bw)          # J per Nyquist sample
        if specs.get("sndr") and "foms" not in specs:
            d["foms_calc"] = round(specs["sndr"] + 10 * math.log10(bw / specs["p"]), 1)
    return d


# ------------------------------------------------------------- affiliations
ORG_HINT = re.compile(r"universit|institut|college|school|KAIST|POSTECH|UNIST|DGIST|GIST|\bETH\b|EPFL|\bMIT\b|"
                      r"laborator|\blabs?\b|inc\b|ltd|corp|company|co\.|electronics|semiconductor|technolog|"
                      r"research|centre|center|academy|imec|tsmc|samsung|sk hynix|intel|mediatek|qualcomm|"
                      r"apple|google|huawei|broadcom|analog devices|texas instruments", I)


def org_and_country(aff):
    if not aff:
        return None, None
    parts = [p.strip() for p in aff.split(",") if p.strip()]
    if not parts:
        return None, None
    country = parts[-1]
    country = re.sub(r"\s+\d[\d\- ]*$", "", country)  # strip trailing postal codes
    if re.fullmatch(r"(korea|south korea|republic of korea|korea \(south\))", country, I):
        country = "South Korea"
    elif re.fullmatch(r"(usa|u\.s\.a\.|united states|united states of america|us)", country, I):
        country = "USA"
    elif re.fullmatch(r"(prc|p\.r\. china|people's republic of china)", country, I):
        country = "China"
    org = None
    for p in parts:
        if ORG_HINT.search(p) and not re.match(r"(department|dept|school of|faculty|division)\b", p, I):
            org = p
            break
    if org is None:
        org = parts[1] if len(parts) > 2 else parts[0]
    if len(country) > 30 or re.search(r"\d", country):
        country = None
    return org, country


# ------------------------------------------------------------- dates
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_month(pubdate, year):
    """'19-23 Feb. 2025' -> '2025-02'; falls back to 'YYYY'."""
    s = (pubdate or "").lower()
    y = None
    years = re.findall(r"(?:19|20)\d{2}", s)
    if years:
        y = years[-1]
    elif year:
        y = str(year)
    mon = None
    for tok in re.findall(r"[a-z]{3,}", s):
        if tok[:3] in MONTHS:
            mon = MONTHS[tok[:3]]
            break
    if y and mon:
        return "%s-%02d" % (y, mon)
    return y or ""
