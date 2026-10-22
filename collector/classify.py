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
    r"\bADCs?\b|analog(?:ue)?[- ]to[- ]digital|\bA/D\b|"
    r"\b(?:delta|sigma)\s*[-–—]?\s*(?:sigma|delta)\b|[ΔΣ]\s?[ΔΣ]|\b(?:CT|DT)?(?:DSM|SDM)s?\b|"
    r"successive[- ]approximation|\bSAR\b|"
    r"noise[- ]shaping|time[- ]interleav|"
    r"(?:capacitance|resistance|inductance|impedance|light)[- ]to[- ]digital", I)
DAC_PAT = re.compile(r"\bDACs?\b|digital[- ]to[- ]analog", I)

# Strong context words that confirm a weak hit (e.g. "SAR", "noise-shaping")
CONVERTER_CTX = re.compile(r"\bADC|conver[st]|modulator|quantiz|\bSNDR\b|\bENOB\b|\bCT\b|[GMk]S/s", I)

# Converter used inside a compute-in-memory / AI macro: keep as "related", not "core"
CIM_CTX = re.compile(r"in[- ]memory|\bCIM\b|\bIMC\b|compute[- ]in|computing[- ]in|neuromorphic", I)

NEGATIVE_CTX = re.compile(
    r"synthetic[- ]aperture|specific absorption rate|"
    r"fractional[- ]N|frequency synthes|\bPLL\b|"
    r"DC[- ]DC|buck|boost converter|power converter", I)

# IEEE controlled terms that are a reliable "this is an ADC paper" signal
ADC_TERMS = re.compile(r"^analog[- ]digital conversion$|^analog-to-digital", I)
DAC_TERMS = re.compile(r"^digital[- ]analog conversion$|^digital-to-analog", I)

NON_PAPER = re.compile(
    r"^(front cover|back cover|table of contents|contents|author index|index|"
    r"call for papers|editorial|guest editorial|reviewers|session \d+ overview|"
    r"(ieee )?(transactions|journal) .*information|blank page|copyright)\b", I)


def _adc_hit(text):
    if not text:
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
    t_dac = bool(DAC_PAT.search(title or ""))
    term_adc = any(ADC_TERMS.search(x) for x in terms)
    term_dac = any(DAC_TERMS.search(x) for x in terms)
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
    ("ΔΣ",      r"\b(?:delta|sigma)\s*[-–—]?\s*(?:sigma|delta)\b|[ΔΣ]\s?[ΔΣ]|\b(?:DT)?(?:DSM|SDM)\b|oversampl"),
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

FS_RX = re.compile(NUM + r"\s*-?\s*([kKMGT])\s*(?:S|Sa|samples)\s*/\s*s|" + NUM + r"\s*-?\s*([kKMGT])sps\b")
RES_RX = re.compile(r"(?<![\w.\-/])(\d{1,2})(?:\.\d+)?\s*-?\s*(?:b|bit|bits)(?![\w/])", I)
NODE_NM_RX = re.compile(r"(?<![\w.])(\d{1,3})\s*-?\s*nm\b", I)
NODE_UM_RX = re.compile(r"(?<![\w.])(0\.\d{2,3})\s*-?\s*[µμu]m\b", I)
SNDR_RX = [
    re.compile(r"SNDR[^.;\d]{0,25}?" + NUM + r"\s*-?\s*dB", I),
    re.compile(NUM + r"\s*-?\s*dB[- ](?:peak[- ])?SNDR", I),
    re.compile(NUM + r"\s*-?\s*dB\s+(?:of\s+)?(?:peak\s+)?SNDR", I),
]
ENOB_RX = re.compile(r"ENOB[^.;\d]{0,20}?" + NUM + r"\s*-?\s*(?:b|bit)", I)
POWER_VAL = NUM + r"\s*-?\s*([nuµμm]?)W\b"
POWER_CTX_RX = re.compile(r"(?:consum\w*|dissipat\w*|power(?:\s+consumption)?|draws|burns)[^.;]{0,40}?" + POWER_VAL, I)
POWER_ANY_RX = re.compile(POWER_VAL)
BW_RX = re.compile(r"(?:bandwidth|\bBW\b)[^.;\d]{0,20}?" + NUM + r"\s*-?\s*([kKMG]?)Hz|" + NUM + r"\s*-?\s*([kKMG]?)Hz\s+(?:signal\s+|input\s+)?(?:bandwidth|BW)", I)
FOMS_RX = re.compile(r"(?:FoM|figure[- ]of[- ]merit)\s*[_ ]?(?:S|SNDR|DR|Schreier)?[^.;\d]{0,30}?(1[4-9]\d(?:\.\d+)?)\s*-?\s*dB", I)
FOMW_RX = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*([afp])J\s*/\s*conv", I)


def _first(rx, text):
    m = rx.search(text or "")
    return m


def parse_specs(title, abstract):
    t = title or ""
    a = abstract or ""
    both = t + " . " + a
    out = {}

    m = FS_RX.search(t) or FS_RX.search(a)
    if m:
        val, pre = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
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
            out["node"] = int(round(float(m.group(1)) * 1000))

    for rx in SNDR_RX:
        m = rx.search(both)
        if m:
            v = float(m.group(1))
            if 10 <= v <= 130:
                out["sndr"] = v
                break
    if "sndr" not in out:
        m = ENOB_RX.search(both)
        if m:
            out["enob"] = float(m.group(1))

    m = POWER_CTX_RX.search(a) or POWER_CTX_RX.search(t) or POWER_ANY_RX.search(t)
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
