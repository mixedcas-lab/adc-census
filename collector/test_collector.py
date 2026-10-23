"""Offline tests: python3 -m unittest discover -s collector -v"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import classify as C  # noqa: E402
import collect  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


class TestRelevance(unittest.TestCase):
    def rel(self, title, abstract="", terms=()):
        return C.relevance(title, abstract, list(terms))

    def test_adc_title(self):
        self.assertEqual(self.rel("A 12-b 1-GS/s Pipelined-SAR ADC in 28-nm CMOS"), ("ADC", "core"))

    def test_sar_adc_with_dac_in_title_is_adc(self):
        t = "A Compact Low-Power 16 b SAR ADC Using Reservoir-Charge-Redistributed DAC and Configurable FIA-Based Comparator"
        self.assertEqual(self.rel(t)[0], "ADC")

    def test_dac(self):
        self.assertEqual(self.rel("A 12-bit 10-GS/s Current-Steering DAC With Dynamic Element Matching"), ("DAC", "core"))

    def test_pll_with_dsm_is_not_adc(self):
        self.assertEqual(self.rel("A 28-GHz Fractional-N PLL With a ΔΣ Modulator Noise Cancellation"), (None, None))

    def test_radar_sar_is_not_adc(self):
        self.assertEqual(self.rel("A Compact SAR Imaging Radar Front-End at 77 GHz"), (None, None))

    def test_buck_is_not_adc(self):
        self.assertEqual(self.rel("A Dual-Mode DC-DC Buck Converter With Adaptive Dead Time"), (None, None))

    def test_related_from_abstract(self):
        t = "A 112-Gb/s PAM-4 Receiver With Feed-Forward Equalization"
        a = "The receiver employs an 8-bit 56-GS/s time-interleaved ADC followed by a DSP."
        self.assertEqual(self.rel(t, a), ("ADC", "related"))

    def test_ieee_term(self):
        self.assertEqual(self.rel("A Reconfigurable Readout Front-End", "", ["Analog-digital conversion"]), ("ADC", "core"))

    def test_noise_shaping_without_converter_context(self):
        self.assertEqual(self.rel("Noise-Shaping Techniques for Class-D Amplifiers"), (None, None))

    def test_dsm_spellings_in_title(self):
        for t in ("A 14-b Energy-Efficient BW/Power Scalable CTDSM With a Frequency-Controlled Current Source",
                  "An ELDC-Free 4th-Order CT SDM Facilitated by 2nd-Order NS CT-SAR",
                  "An Energy-Efficient Discrete-Time Delta–Sigma Modulator With Dynamic-Range Enhancement",
                  "An 18-MS/s 76-dB SNDR Continuous-Time Δ Σ Modulator With a GmC Loop Filter"):
            self.assertEqual(self.rel(t), ("ADC", "core"), t)

    def test_sar_with_sample_rate(self):
        t = "A 7 GHz ERBW 1.1 GS/s 6-bit PVT Tolerant Asynchronous Charge-Injection SAR"
        self.assertEqual(self.rel(t), ("ADC", "core"))

    def test_ctdsm_with_resistor_dac_is_adc(self):
        t = "A 119-dBA Dynamic Range, 3.3-mW Audio CTDSM With a Class-B Resistor DAC and Continuous-Time Quantizer"
        self.assertEqual(self.rel(t), ("ADC", "core"))

    def test_adc_free_is_not_converter(self):
        self.assertEqual(self.rel("ADC/DAC-Free Analog Acceleration of Deep Neural Networks With Frequency Transformation"),
                         (None, None))
        t = ("34.1 A 128mW 2×4 Radar-on-Chip with Forward-ΔΣ DPLL-Locked Multi-Injection RTWO in 22nm CMOS "
             "Enabling ADC-Free Digitization")
        self.assertEqual(self.rel(t), (None, None))

    def test_other_meanings_of_adc(self):
        for t in ("Attitude Determination and Control System (ADCS) Testbeds for CubeSats: A Review",
                  "TRACE: Trustworthy Reasoning for Agentic Chemical Evidence in Antibody-Drug Conjugate Design"):
            self.assertEqual(self.rel(t), (None, None), t)
        a = "Apparent diffusion coefficient (ADC) maps from MRI are segmented by a CNN."
        self.assertEqual(self.rel("Predicting Acute Brain Infarct From Magnetic Resonance Images", a), (None, None))

    def test_pll_with_dac_is_not_dac(self):
        t = "A DTC-Based Snapshot ADPLL With Feedforward Fractional Spur Cancellation and a Calibrated DAC"
        self.assertEqual(self.rel(t), (None, None))
        self.assertEqual(self.rel("A Snapshot ADPLL With Fractional Spur Cancellation", "", ["digital-to-analog converter"]),
                         (None, None))
        t = "A 2.5-GHz Dynamic Performance-Enhanced Nonlinear DAC-Based Direct-Digital Frequency Synthesizer in 65-nm CMOS"
        self.assertEqual(self.rel(t), ("DAC", "core"))

    def test_incremental_dsm(self):
        t = "A 103.9dB-SFDR 83.8dB-SNDR 3MHz-BW Multi-Bit Quadratic-Exponential Noise-Coupled IDSM with DAC"
        self.assertEqual(self.rel(t), ("ADC", "core"))

    def test_tutorials_are_not_papers(self):
        for t in ("Tutorial: Digital Equalization and Timing Recovery Techniques for ADC-DSP Based High-Speed Links",
                  "Short Course: Principles of Quantum Computing", "Tutorials", "Evening Event: Student Research Preview"):
            self.assertTrue(C.NON_PAPER.search(t), t)
        self.assertFalse(C.NON_PAPER.search("Tutorial and Perspectives on MAGICAL: An Open-Source Layout System"))

    def test_cim_adc_is_related(self):
        t = "Scaling-CIM: eDRAM In-Memory-Computing Accelerator With Dynamic-Scaling ADC and Adaptive Analog Operation"
        self.assertEqual(self.rel(t), ("ADC", "related"))

    def test_terms_of_ignores_ieee_automatic_terms(self):
        a = {"index_terms": {"ieee_terms": {"terms": ["Analog-digital conversion"]},
                             "dynamic_index_terms": {"terms": ["Analog-to-digital Converter"]},
                             "author_terms": {"terms": ["PLL"]}}}
        self.assertEqual(collect.terms_of(a), ["PLL"])
        t = "A Fast Back-to-Lock DPLL-Based 192-210-GHz Chirp Generator"
        self.assertEqual(self.rel(t, "", collect.terms_of(a)), (None, None))


class TestArch(unittest.TestCase):
    def test_pipelined_sar(self):
        self.assertEqual(C.architectures("A 12-b 1-GS/s Pipelined-SAR ADC", ""), ["Pipelined-SAR"])

    def test_ti_sar(self):
        self.assertEqual(C.architectures("A 64-GS/s 8-b Time-Interleaved SAR ADC", ""), ["TI", "SAR"])

    def test_ns_sar(self):
        self.assertEqual(C.architectures("A 93.5 dB-SNDR Noise-Shaping SAR ADC", ""), ["NS-SAR"])

    def test_ct_dsm(self):
        self.assertEqual(C.architectures("A Continuous-Time ΔΣ Modulator With 100-MHz Bandwidth", ""), ["CT-ΔΣ"])
        self.assertEqual(C.architectures("A 14-b Scalable CTDSM With a Frequency-Controlled Current Source", ""), ["CT-ΔΣ"])
        self.assertEqual(C.architectures("A Discrete-Time Delta–Sigma Modulator With Tri-Level CDAC", ""), ["ΔΣ"])
        self.assertEqual(C.architectures("Reducing the Impact of Non-Idealities on Incremental Δ∑ ADCs", ""),
                         ["ΔΣ", "Incremental"])

    def test_abstract_fallback_uses_first_sentences_only(self):
        a = "This article presents a VCO-based ADC. Unlike SAR ADCs, it needs no comparator."
        self.assertEqual(C.architectures("An Energy-Efficient Converter for Sensors", a), ["VCO/Time-domain"])

    def test_flash_memory_is_not_flash_adc(self):
        self.assertNotIn("Flash", C.architectures("A Readout ADC for 3D NAND Flash Memory", ""))


class TestSpecs(unittest.TestCase):
    def test_more_spellings(self):
        s = C.parse_specs(collect.clean("A 2.5-V 12-b 54-Msample/s 0.25-/spl mu/m CMOS ADC in 1-mm/sup 2/"), "")
        self.assertEqual((s["fs"], s["node"]), (54e6, 250))
        a = ("It operates with a sampling rate of 5 MSamples/sec and consumes only 870 muW. The prototype in a 40-nm CMOS "
             "achieves 63.8-dB signal-to-noise-and-distortion ratio.")
        s = C.parse_specs("A 20 Msample/s pipeline A/D converter", a)
        self.assertEqual((s["fs"], s["p"], s["sndr"]), (20e6, 870e-6, 63.8))
        self.assertEqual(C.parse_specs("X", "The prototype is sampled at 630 MHz.")["fs"], 630e6)
        self.assertEqual(C.parse_specs("X", "consumes 4. 15mW and achieves 58. 5dB SNDR")["sndr"], 58.5)
        self.assertEqual(C.parse_specs("X", "with 270-mW power dissipation")["p"], 0.27)

    def test_neighbouring_metrics(self):
        s = C.parse_specs("X", "achieves 74.1-dB SNDR, 83.4-dB SFDR and 20-kHz bandwidth. 92 dB DR, 91 dB SNR and 89 dB SNDR "
                               "in a 24 kHz audio signal bandwidth")
        self.assertEqual((s["sndr"], s["snr"], s["dr"], s["bw"]), (74.1, 91.0, 92.0, 2e4))
        s = C.parse_specs("X", "achieves 75.4-dB dynamic range (DR) and 73.3-dB peak signal-to-noise-and-distortion ratio (SNDR)")
        self.assertEqual((s["sndr"], s["dr"]), (73.3, 75.4))
        self.assertNotIn("dr", C.parse_specs("X", "with 90-dB spurious-free dynamic range (SFDR)"))
        self.assertEqual(C.parse_specs("X", "achieves a low-frequency SFDR/SNDR of 75.2/62.4 dB")["sndr"], 62.4)
        self.assertEqual(C.parse_specs("X", "the Nyquist SNDR and SFDR are 55 dB and 69 dB respectively")["sndr"], 55.0)
        self.assertEqual(C.parse_specs("X", "The prototype achieves an SNDR and an SFDR of 63.4 dB and 81.0 dBc")["sndr"], 63.4)

    def test_node_spellings(self):
        self.assertEqual(C.parse_specs("X", "simulations in 0.13 µ m CMOS technology")["node"], 130)
        self.assertEqual(C.parse_specs("X", "fabricated in a 0.8 mum Indium-Phosphide HBT process")["node"], 800)
        self.assertEqual(C.parse_specs("X", "The DAC is fabricated in a 2-µm CMOS process")["node"], 2000)
        self.assertNotIn("node", C.parse_specs("X", "a pixel pitch of 2 µm"))

    def test_title_specs(self):
        s = C.parse_specs("A 64-GS/s 8-b Time-Interleaved SAR ADC for 224-Gb/s PAM-4 Wireline Receivers in 5-nm FinFET", "")
        self.assertEqual(s["fs"], 64e9)
        self.assertEqual(s["res"], 8)
        self.assertEqual(s["node"], 5)

    def test_abstract_specs(self):
        a = ("The prototype is fabricated in 28-nm CMOS. It achieves an SNDR of 62.3 dB at Nyquist input "
             "while consuming 8.4 mW from a 0.9-V supply, resulting in a Schreier FoM of 170.1 dB "
             "and a Walden FoM of 7.9 fJ/conv.-step.")
        s = C.parse_specs("A 12-b 1-GS/s Pipelined-SAR ADC", a)
        self.assertEqual(s["fs"], 1e9)
        self.assertEqual(s["res"], 12)
        self.assertEqual(s["node"], 28)
        self.assertAlmostEqual(s["sndr"], 62.3)
        self.assertAlmostEqual(s["p"], 8.4e-3)
        self.assertAlmostEqual(s["foms"], 170.1)
        self.assertAlmostEqual(s["fomw"], 7.9)

    def test_power_and_sndr_in_title(self):
        s = C.parse_specs("A 3.7 μW 93.5 dB-SNDR PPD-Based Noise-Shaping SAR ADC", "")
        self.assertAlmostEqual(s["p"], 3.7e-6)
        self.assertAlmostEqual(s["sndr"], 93.5)

    def test_um_node_and_bandwidth(self):
        s = C.parse_specs("A 0.18-µm CMOS Continuous-Time Delta-Sigma Modulator With 100-MHz Bandwidth", "")
        self.assertEqual(s["node"], 180)
        self.assertEqual(s["bw"], 100e6)

    def test_gbps_is_not_resolution(self):
        s = C.parse_specs("A 112-Gb/s PAM-4 ADC-Based Receiver", "")
        self.assertNotIn("res", s)

    def test_derived_nyquist(self):
        d = C.derived({"fs": 1e9, "p": 8.4e-3, "sndr": 62.3}, ["Pipelined-SAR"])
        self.assertAlmostEqual(d["e_nyq"], 8.4e-12)
        self.assertAlmostEqual(d["foms_calc"], 62.3 + 10 * __import__("math").log10(0.5e9 / 8.4e-3), places=1)

    def test_derived_oversampled_needs_bw(self):
        self.assertEqual(C.derived({"fs": 1e9, "p": 1e-3, "sndr": 80}, ["CT-ΔΣ"]), {})


class TestMisc(unittest.TestCase):
    def test_affiliation(self):
        org, cn = C.org_and_country("School of Electrical Engineering, KAIST, Daejeon 34141, Republic of Korea")
        self.assertEqual(org, "KAIST")
        self.assertEqual(cn, "South Korea")

    def test_affiliation_univ(self):
        org, cn = C.org_and_country("Department of Electrical and Computer Engineering, University of Seoul, Seoul, South Korea")
        self.assertEqual(org, "University of Seoul")
        self.assertEqual(cn, "South Korea")

    def test_month(self):
        self.assertEqual(C.parse_month("19-23 Feb. 2025", 2025), "2025-02")
        self.assertEqual(C.parse_month("June 2024", None), "2024-06")
        self.assertEqual(C.parse_month("2025", 2025), "2025")

    def test_clean_tex(self):
        self.assertEqual(collect.clean("A <inline-formula><tex-math notation=\"LaTeX\">$\\Delta\\Sigma$</tex-math></inline-formula> ADC"),
                         "A ΔΣ ADC")
        self.assertEqual(collect.clean("LNA-Embedded CT $\\mathbf{\\Delta\\Sigma}$ ADC"), "LNA-Embedded CT ΔΣ ADC")


class FakeClient:
    """Serves fixture articles for any query; filters by venue keyword like the real API roughly would."""
    def __init__(self, articles):
        self.articles = articles
        self.calls = 0

    def search(self, params, start):
        self.calls += 1
        want = params.get("issn") or params.get("publication_title") or ""
        hits = [a for a in self.articles
                if want and (a.get("issn") == want or want.lower() in a.get("publication_title", "").lower())]
        if "start_year" in params:
            hits = [a for a in hits if int(a["publication_year"]) == params["start_year"]]
        return {"total_records": len(hits), "articles": hits[start - 1:start - 1 + collect.PAGE]}


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = {k: getattr(collect, k) for k in ("DATA", "CACHE", "STATE", "PAPERS", "META", "SURVEY")}
        collect.DATA = os.path.join(self.tmp, "data")
        collect.CACHE = os.path.join(self.tmp, "cache", "raw")
        collect.STATE = os.path.join(collect.DATA, "state.json")
        collect.PAPERS = os.path.join(collect.DATA, "papers.json")
        collect.META = os.path.join(collect.DATA, "meta.json")
        collect.SURVEY = os.path.join(collect.DATA, "murmann.json")   # absent unless a test writes it
        os.makedirs(collect.DATA)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(collect, k, v)
        shutil.rmtree(self.tmp)

    def test_sweep_then_reclassify(self):
        with open(os.path.join(HERE, "fixtures", "sample_articles.json"), encoding="utf-8") as f:
            arts = json.load(f)
        config = collect.load_json(collect.CONFIG, None)
        state = {}
        collect.init_sweep(state, config, 2025)
        client = FakeClient(arts)
        collect.run_sweep(client, state, config, "2026-10-22")
        self.assertTrue(state["sweep"]["done"])
        meta = collect.rebuild(config, "2026-10-22")
        papers = collect.load_json(collect.PAPERS, [])
        ids = {p["id"]: p for p in papers}
        # non-ADC items (PLL, buck, overview) are dropped, venues are assigned
        self.assertNotIn("9000003", ids)
        self.assertNotIn("9000006", ids)
        self.assertEqual(ids["9000001"]["v"], "JSSC")
        self.assertEqual(ids["9000002"]["v"], "ISSCC")
        self.assertEqual(ids["9000004"]["k"], "DAC")
        self.assertEqual(ids["9000005"]["lv"], "related")
        self.assertEqual(ids["9000001"]["cn"], ["South Korea"])
        self.assertNotIn("abstract", json.dumps(papers))
        self.assertEqual(meta["total"], len(papers))
        # reclassify keeps the same result and preserves first-seen dates
        collect.rebuild(config, "2026-11-01")
        again = collect.load_json(collect.PAPERS, [])
        self.assertEqual([p["id"] for p in again], [p["id"] for p in papers])
        self.assertTrue(all(p["first"] == "2026-10-22" for p in again))
        # the diagnostic report runs on the cache without the API
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            collect.report(config)
        out = buf.getvalue()
        self.assertIn("IEEE Journal of Solid-State Circuits", out)
        self.assertIn("core papers by venue and year", out)

    def test_new_venue_is_backfilled(self):
        config = collect.load_json(collect.CONFIG, None)
        old = {"queries": [q for q in config["queries"] if q["key"] != "Access"], "venues": config["venues"]}
        state = {}
        collect.init_sweep(state, old, 2025)
        for t in state["sweep"]["tasks"]:
            t["done"] = True
        state["sweep"]["done"] = True
        state["last_delta_end"] = "20261023"
        added = collect.add_missing_tasks(state, config)
        self.assertEqual({k for k, _ in added}, {"Access"})
        self.assertFalse(state["sweep"]["done"])
        self.assertEqual(min(y for _, y in added), 2025)
        collect.run_sweep(FakeClient([]), state, config, "2026-11-01")
        self.assertTrue(state["sweep"]["done"])
        self.assertEqual(state["last_delta_end"], "20261023")   # delta position is kept
        self.assertEqual(collect.add_missing_tasks(state, config), [])

    def test_earlier_since_year_backfills_with_venue_limits(self):
        config = collect.load_json(collect.CONFIG, None)
        state = {}
        collect.init_sweep(state, config, 2023)
        state["since_year"] = 2000
        added = set(collect.add_missing_tasks(state, config))
        self.assertIn(("JSSC", 2000), added)
        self.assertIn(("TCAS-I-1992", 2003), added)
        self.assertNotIn(("TCAS-I-1992", 2004), added)   # old ISSN ends in 2003
        self.assertNotIn(("TCAS-I", 2003), added)
        self.assertNotIn(("SSC-L", 2017), added)         # launched 2018
        self.assertIn(("VLSI-C", 2021), added)
        self.assertNotIn(("VLSI", 2021), added)

    def test_since_year_hides_older_papers(self):
        with open(os.path.join(HERE, "fixtures", "sample_articles.json"), encoding="utf-8") as f:
            arts = json.load(f)
        config = collect.load_json(collect.CONFIG, None)
        state = {}
        collect.init_sweep(state, config, 2025)
        collect.run_sweep(FakeClient(arts), state, config, "2026-10-22")
        n = len(collect.rebuild(config, "2026-10-22") and collect.load_json(collect.PAPERS, []))
        state["since_year"] = 2026
        collect.save_json(collect.STATE, state)
        collect.rebuild(config, "2026-10-22")
        papers = collect.load_json(collect.PAPERS, [])
        self.assertLess(len(papers), n)
        self.assertTrue(all(p["y"] >= 2026 for p in papers))

    def test_survey_is_absorbed(self):
        with open(os.path.join(HERE, "fixtures", "sample_articles.json"), encoding="utf-8") as f:
            arts = json.load(f)
        for a in arts:
            a["doi"] = "10.1109/X.%s" % a["article_number"]
        config = collect.load_json(collect.CONFIG, None)
        state = {}
        collect.init_sweep(state, config, 2025)
        collect.run_sweep(FakeClient(arts), state, config, "2026-10-22")
        rows = [
            {"c": "ISSCC", "y": 2025, "doi": "10.1109/X.9000002", "ar": ["TI", "SAR"], "t": "x",
             "sndr": 37.0, "fs": 6.4e10, "fsnyq": 6.4e10, "p": 0.3, "foms": 147.0, "fin": 3e10, "sndr_hf": 36.0},
            {"c": "ISSCC", "y": 2025, "doi": "10.1109/X.9000002", "sndr": 30.0, "p": 0.3, "foms": 140.0},   # second mode
            {"c": "ISSCC", "y": 2025, "doi": "10.1109/x.9000005", "ar": ["TI"], "t": "receiver", "sndr": 33.0, "p": 0.5},
            {"c": "VLSI", "y": 2025, "doi": "10.1109/VLSIC.1997.623781", "ar": ["CT-ΔΣ"], "t": "1.2-V Audio A/D Converter",
             "au": "Y. Matsuya, J. Terada", "sndr": 91.5, "fs": 6.14e6, "fsnyq": 4e4, "p": 6.5e-3},
        ]
        collect.save_json(collect.SURVEY, {"rows": rows})
        collect.rebuild(config, "2026-10-22")
        collect.rebuild(config, "2026-10-23")          # survey-only records are rebuilt, not duplicated
        ids = {p["id"]: p for p in collect.load_json(collect.PAPERS, [])}
        p = ids["9000002"]
        self.assertEqual((p["s"]["sndr"], p["s"]["fs"], p["s"]["bw"], p["s"]["fin"]), (37.0, 6.4e10, 3.2e10, 3e10))
        self.assertIn("sndr", p["sv"])
        self.assertEqual(ids["9000005"]["lv"], "core")       # abstract-only receiver becomes core via the survey (DOI case ignored)
        m = ids["m:10.1109/VLSIC.1997.623781"]
        self.assertEqual((m["v"], m["y"], m["k"], m["ar"], m["au"]), ("VLSI", 2025, "ADC", ["CT-ΔΣ"], ["Y. Matsuya", "J. Terada"]))
        self.assertEqual(sum(1 for k in ids if k.startswith("m:")), 1)

    def test_access_venue_match(self):
        venues = collect.load_json(collect.CONFIG, None)["venues"]
        self.assertEqual(collect.venue_of("IEEE Access", venues), "Access")
        self.assertIsNone(collect.venue_of("IEEE Access Magazine", venues))



def _xlsx(path, sheets):
    """Minimal .xlsx with inline strings, enough for murmann.read_sheets()."""
    import zipfile
    from xml.sax.saxutils import escape

    def col(i):
        return chr(ord("A") + i) if i < 26 else "A" + chr(ord("A") + i - 26)

    with zipfile.ZipFile(path, "w") as z:
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        rns = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        z.writestr("xl/workbook.xml", "<workbook %s %s><sheets>%s</sheets></workbook>" % (ns, rns, "".join(
            '<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (n, i + 1, i + 1) for i, n in enumerate(sheets))))
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">%s</Relationships>' % "".join(
            '<Relationship Id="rId%d" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1) for i in range(len(sheets))))
        for i, rows in enumerate(sheets.values()):
            xml = "".join("<row>%s</row>" % "".join(
                '<c r="%s%d" t="inlineStr"><is><t>%s</t></is></c>' % (col(j), k + 1, escape(str(v)))
                if isinstance(v, str) else '<c r="%s%d"><v>%s</v></c>' % (col(j), k + 1, v)
                for j, v in enumerate(row) if v is not None) for k, row in enumerate(rows))
            z.writestr("xl/worksheets/sheet%d.xml" % (i + 1), "<worksheet %s><sheetData>%s</sheetData></worksheet>" % (ns, xml))


class TestMurmann(unittest.TestCase):
    HEAD = ["YEAR", "ID", "TYPE", "ARCHITECTURE", "TECHNOLOGY", "TITLE", "ABSTRACT", "AUTHORS", "DOI",
            "SNDR_plot [dB]", "P [W]", "fsnyq [Hz]", "P/fsnyq [pJ]", "FOMS_hf [dB]", "fin_hf [Hz]", "SNDR_hf [dB]"]

    def test_convert(self):
        import murmann
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "s.xlsx")
            _xlsx(path, {"Readme": [["x"]], "ISSCC": [self.HEAD,
                [2024, "10.1", "NQ", "Pipe, SAR, TI", "2.8E-2", "A 12b ADC", "secret abstract text", "A. B", "10.1109/x",
                 62.5, 0.01, 1e9, 10.0, 169.5, 4.9e8, 61.0],
                [2022, "25.5", "OS", "SDCT", "0.028", "Placeholder row", "", "C. D", "", 1, None, 2.4e8, 1e10, 1, None, None]],
                "VLSI": [self.HEAD, [2005, "C3.2", "OS", "Incremental, SDSC", "0.18 BiCMOS", "A ΔΣ", "", "E. F", "", 90, 1e-3, 2e4, 5e4, 160, None, None]]})
            d = murmann.convert(path)
        finally:
            shutil.rmtree(tmp)
        rows = d["rows"]
        self.assertEqual(len(rows), 3)
        self.assertNotIn("secret", json.dumps(d))                  # abstracts are never copied
        a = rows[0]
        self.assertEqual((a["c"], a["y"], a["node"], a["ar"]), ("ISSCC", 2024, 28, ["TI", "Pipelined-SAR"]))
        self.assertEqual((a["sndr"], a["fsnyq"], a["e_pj"], a["foms"], a["fin"]), (62.5, 1e9, 10.0, 169.5, 4.9e8))
        self.assertNotIn("sndr", rows[1])                           # 1 dB placeholder
        self.assertNotIn("e_pj", rows[1])                           # no power, so no energy or FoM
        self.assertNotIn("foms", rows[1])
        self.assertEqual((rows[2]["c"], rows[2]["node"], rows[2]["ar"]), ("VLSI", 180, ["ΔΣ", "Incremental"]))
        self.assertEqual(d["years"], [2005, 2024])


if __name__ == "__main__":
    unittest.main()
