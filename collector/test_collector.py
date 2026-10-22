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
        self.saved = {k: getattr(collect, k) for k in ("DATA", "CACHE", "STATE", "PAPERS", "META")}
        collect.DATA = os.path.join(self.tmp, "data")
        collect.CACHE = os.path.join(self.tmp, "cache", "raw")
        collect.STATE = os.path.join(collect.DATA, "state.json")
        collect.PAPERS = os.path.join(collect.DATA, "papers.json")
        collect.META = os.path.join(collect.DATA, "meta.json")
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


if __name__ == "__main__":
    unittest.main()
