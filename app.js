/* ADC Census front end. Plain JS, no build step.
   Data: data/meta.json, data/papers.json (written by collector/collect.py),
         data/annotations.csv (hand-checked values and corrections, optional). */
(function () {
  "use strict";

  var ARCH_COLORS = {
    "SAR": "#1f55c4", "NS-SAR": "#7a9be8", "Pipelined-SAR": "#0d8a7d", "Pipelined": "#5fb8a8",
    "TI": "#b0228c", "ΔΣ": "#d69a00", "CT-ΔΣ": "#8d5a00", "Incremental": "#7d8a1f",
    "Zoom": "#a3a03a", "VCO/Time-domain": "#6a2fd0", "Flash": "#d0365a", "Subranging": "#3b9ad9",
    "Single-slope": "#5a6b80", "Folding": "#a07a5a", "Current-steering": "#1f55c4", "RF-DAC": "#b0228c",
    "Other": "#9aa4b1"
  };
  // the colour of a dot follows the most specific architecture tag
  var PRIMARY = ["TI", "Pipelined-SAR", "NS-SAR", "CT-ΔΣ", "ΔΣ", "Incremental", "Zoom",
    "VCO/Time-domain", "Pipelined", "Subranging", "Flash", "Single-slope", "Folding", "SAR",
    "RF-DAC", "Current-steering"];
  var OVERSAMPLED = ["ΔΣ", "CT-ΔΣ", "NS-SAR", "Incremental", "Zoom"];
  var VENUE_ORDER = ["ISSCC", "VLSI", "JSSC", "CICC", "ESSCIRC", "A-SSCC", "SSC-L", "TCAS-I", "TCAS-II", "TVLSI"];
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var PAGE = 150;

  var $ = function (id) { return document.getElementById(id); };
  var META = {}, ALL = [], VIEW = [], LIMIT = PAGE, BYID = {};
  var F = defaults();

  function defaults() {
    return { q: "", kind: "ADC", y0: "", y1: "", venues: [], apps: [], arch: [], country: "",
      related: false, cal: false, fresh: false, sort: "date" };
  }

  /* ------------------------------------------------------------ helpers */
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  var SI = [[1e12, "T"], [1e9, "G"], [1e6, "M"], [1e3, "k"], [1, ""], [1e-3, "m"], [1e-6, "µ"], [1e-9, "n"], [1e-12, "p"], [1e-15, "f"], [1e-18, "a"]];
  function fmtSI(v, unit) {
    if (v == null || !isFinite(v) || v <= 0) return "";
    for (var i = 0; i < SI.length; i++) {
      if (v >= SI[i][0] * 0.9995) {
        var x = v / SI[i][0];
        var s = x >= 100 ? x.toFixed(0) : x >= 10 ? (+x.toFixed(1)).toString() : (+x.toFixed(2)).toString();
        return s + " " + SI[i][1] + unit;
      }
    }
    return v.toExponential(1) + unit;
  }
  function parseSI(s) {
    if (s == null) return null;
    s = String(s).trim().replace(/[μu]/, "µ");
    if (!s) return null;
    var m = s.match(/^([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*([TGMkKµmunpfa]?)/);
    if (!m) return null;
    var mult = { T: 1e12, G: 1e9, M: 1e6, k: 1e3, K: 1e3, "": 1, m: 1e-3, "µ": 1e-6, n: 1e-9, p: 1e-12, f: 1e-15, a: 1e-18 }[m[2]];
    return parseFloat(m[1]) * mult;
  }
  function parseCSV(text) {
    var rows = [], row = [], cell = "", q = false;
    for (var i = 0; i < text.length; i++) {
      var c = text[i];
      if (q) {
        if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
        else if (c === '"') q = false;
        else cell += c;
      } else if (c === '"') q = true;
      else if (c === ",") { row.push(cell); cell = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        row.push(cell); rows.push(row); row = []; cell = "";
      } else cell += c;
    }
    if (cell || row.length) { row.push(cell); rows.push(row); }
    var head = (rows.shift() || []).map(function (h) { return h.trim().toLowerCase(); });
    return rows.filter(function (r) { return r.some(function (x) { return x.trim(); }) && !/^#/.test(r[0]); })
      .map(function (r) { var o = {}; head.forEach(function (h, i) { o[h] = (r[i] || "").trim(); }); return o; });
  }
  function fmtDate(d) {
    if (!d) return "";
    var m = d.match(/^(\d{4})-(\d{2})/);
    return m ? MONTHS[+m[2] - 1] + " " + m[1] : d;
  }
  function list(s) { return s ? s.split(/\s*;\s*/).filter(Boolean) : []; }

  /* ------------------------------------------------------------ data model */
  function primaryArch(p) {
    for (var i = 0; i < PRIMARY.length; i++) if (p.ar.indexOf(PRIMARY[i]) >= 0) return PRIMARY[i];
    return "Other";
  }
  function derive(p) {
    var s = p.s, bw = s.bw;
    var over = p.ar.some(function (a) { return OVERSAMPLED.indexOf(a) >= 0; });
    if (!bw && !over && s.fs) bw = s.fs / 2;
    p.e = null; p.fomsCalc = null;
    if (bw && s.p) {
      p.e = s.p / (2 * bw);
      if (s.sndr) p.fomsCalc = Math.round((s.sndr + 10 * Math.log10(bw / s.p)) * 10) / 10;
    }
    p.foms = s.foms != null ? s.foms : p.fomsCalc;
    p.prim = primaryArch(p);
  }
  function applyAnnotations(papers, rows) {
    var ann = {};
    rows.forEach(function (r) { if (r.id) ann[r.id] = r; });
    var out = [];
    papers.forEach(function (p) {
      p.s = p.s || {}; p.ar = p.ar || []; p.ap = p.ap || []; p.ver = {};
      var a = ann[p.id];
      if (a) {
        if (/^(1|y|yes|true|x)$/i.test(a.exclude || "")) return;
        if (a.kind) p.k = a.kind.toUpperCase();
        if (a.arch) p.ar = list(a.arch);
        if (a.app) p.ap = list(a.app);
        if (a.kind || a.arch) p.lv = "core";
        ["res", "fs", "bw", "sndr", "p", "node", "foms", "fomw"].forEach(function (k) {
          var v = parseSI(a[k]);
          if (v != null && !isNaN(v)) { p.s[k] = v; p.ver[k] = true; }
        });
        p.note = a.note || "";
      }
      derive(p);
      out.push(p);
    });
    return out;
  }

  /* ------------------------------------------------------------ filtering */
  function match(p, skip) {
    if (p.k !== F.kind) return false;
    if (!F.related && p.lv !== "core") return false;
    if (skip !== "year") {
      if (F.y0 && (p.y || 0) < +F.y0) return false;
      if (F.y1 && (p.y || 9999) > +F.y1) return false;
    }
    if (skip !== "venue" && F.venues.length && F.venues.indexOf(p.v) < 0) return false;
    if (skip !== "app" && F.apps.length && !F.apps.some(function (a) { return p.ap.indexOf(a) >= 0; })) return false;
    if (skip !== "arch" && F.arch.length && !F.arch.some(function (a) { return a === "Other" ? p.prim === "Other" : p.ar.indexOf(a) >= 0; })) return false;
    if (skip !== "country" && F.country && (p.cn || []).indexOf(F.country) < 0) return false;
    if (F.cal && !p.cal) return false;
    if (F.fresh && p.first !== META.updated) return false;
    if (F.q) {
      var hay = p._hay || (p._hay = [p.t, (p.au || []).join(" "), (p.org || []).join(" "), p.v, p.vt, p.ar.join(" ")].join(" ").toLowerCase());
      var terms = F.q.toLowerCase().split(/\s+/).filter(Boolean);
      for (var i = 0; i < terms.length; i++) if (hay.indexOf(terms[i]) < 0) return false;
    }
    return true;
  }
  function counts(skip, key) {
    var c = {};
    ALL.forEach(function (p) {
      if (!match(p, skip)) return;
      var vals = key(p);
      vals.forEach(function (v) { if (v) c[v] = (c[v] || 0) + 1; });
    });
    return c;
  }
  var SORTS = {
    date: function (a, b) { return (b.d || "").localeCompare(a.d || "") || (b.id > a.id ? 1 : -1); },
    fs: function (a, b) { return (b.s.fs || 0) - (a.s.fs || 0); },
    sndr: function (a, b) { return (b.s.sndr || 0) - (a.s.sndr || 0); },
    foms: function (a, b) { return (b.foms || 0) - (a.foms || 0); },
    energy: function (a, b) { return (a.e || Infinity) - (b.e || Infinity); }
  };

  /* ------------------------------------------------------------ URL state */
  function writeHash() {
    var d = defaults(), u = new URLSearchParams();
    Object.keys(F).forEach(function (k) {
      var v = F[k];
      if (Array.isArray(v) ? v.length : v !== d[k]) u.set(k, Array.isArray(v) ? v.join("|") : v);
    });
    var h = u.toString();
    history.replaceState(null, "", h ? "#" + h : location.pathname + location.search);
  }
  function readHash() {
    var u = new URLSearchParams(location.hash.slice(1)), d = defaults();
    Object.keys(d).forEach(function (k) {
      if (!u.has(k)) return;
      var v = u.get(k);
      if (Array.isArray(d[k])) F[k] = v ? v.split("|") : [];
      else if (typeof d[k] === "boolean") F[k] = v === "true";
      else F[k] = v;
    });
  }

  /* ------------------------------------------------------------ rendering: controls */
  function chip(label, n, pressed) {
    return '<button type="button" class="chip" data-v="' + esc(label) + '" aria-pressed="' + pressed + '">' +
      esc(label) + '<span class="n">' + (n || 0) + "</span></button>";
  }
  function renderControls() {
    var vc = counts("venue", function (p) { return [p.v]; });
    var venues = VENUE_ORDER.filter(function (v) { return META.by_venue && META.by_venue[v] || vc[v]; });
    Object.keys(vc).forEach(function (v) { if (venues.indexOf(v) < 0) venues.push(v); });
    $("venues").innerHTML = venues.map(function (v) { return chip(v, vc[v], F.venues.indexOf(v) >= 0); }).join("");

    var ac = counts("app", function (p) { return p.ap; });
    var apps = Object.keys(ac).sort(function (a, b) { return ac[b] - ac[a]; });
    F.apps.forEach(function (a) { if (apps.indexOf(a) < 0) apps.push(a); });
    $("apps").innerHTML = apps.length ? apps.map(function (a) { return chip(a, ac[a], F.apps.indexOf(a) >= 0); }).join("")
      : '<span class="n" style="color:var(--muted)">None in this selection</span>';

    var cc = counts("country", function (p) { return p.cn || []; });
    var countries = Object.keys(cc).sort(function (a, b) { return cc[b] - cc[a]; });
    $("country").innerHTML = '<option value="">All</option>' + countries.map(function (c) {
      return '<option value="' + esc(c) + '"' + (F.country === c ? " selected" : "") + ">" + esc(c) + " (" + cc[c] + ")</option>";
    }).join("");

    Array.prototype.forEach.call($("kind").children, function (b) { b.setAttribute("aria-pressed", b.dataset.v === F.kind); });
    $("q").value = F.q;
    $("y0").value = F.y0; $("y1").value = F.y1;
    $("related").checked = F.related; $("cal").checked = F.cal; $("fresh").checked = F.fresh;
    $("sort").value = F.sort;
  }
  function renderLegend() {
    var c = counts("arch", function (p) { return p.prim === "Other" ? ["Other"] : p.ar; });
    var keys = Object.keys(c).sort(function (a, b) {
      return (a === "Other") - (b === "Other") || c[b] - c[a];
    });
    F.arch.forEach(function (a) { if (keys.indexOf(a) < 0) keys.push(a); });
    $("legend").innerHTML = keys.map(function (k) {
      var on = F.arch.indexOf(k) >= 0, off = F.arch.length && !on;
      return '<li class="' + (off ? "off" : "") + '"><button type="button" data-v="' + esc(k) + '" aria-pressed="' + on + '">' +
        '<span class="sw" style="background:' + (ARCH_COLORS[k] || ARCH_COLORS.Other) + '"></span><span>' + esc(k) +
        '</span><span class="n">' + (c[k] || 0) + "</span></button></li>";
    }).join("");

    var yc = {};
    VIEW.forEach(function (p) { if (p.y) yc[p.y] = (yc[p.y] || 0) + 1; });
    var ys = Object.keys(yc).sort().reverse(), mx = Math.max.apply(null, ys.map(function (y) { return yc[y]; }).concat([1]));
    $("years").innerHTML = ys.map(function (y) {
      return '<div class="yr"><span>' + y + '</span><span class="bar" style="width:' + (100 * yc[y] / mx).toFixed(1) +
        '%"></span><span class="yn">' + yc[y] + "</span></div>";
    }).join("");
  }

  /* ------------------------------------------------------------ rendering: plot */
  function renderPlot() {
    var pts = VIEW.filter(function (p) { return p.e && p.s.sndr; });
    // draw at the container's real pixel width so text stays legible on phones
    var W = Math.max(320, Math.round($("plot").clientWidth || 820));
    var narrow = W < 560;
    var H = narrow ? Math.round(W * 0.95) : Math.min(440, Math.round(W * 0.52));
    var L = narrow ? 44 : 56, R = W - (narrow ? 8 : 18), T = 14, B = H - 46;
    var xs = pts.map(function (p) { return Math.log10(p.e); }), ys = pts.map(function (p) { return p.s.sndr; });
    var x0 = xs.length ? Math.floor(Math.min.apply(null, xs)) : -15, x1 = xs.length ? Math.ceil(Math.max.apply(null, xs)) : -6;
    if (x1 - x0 < 3) { x0 -= 1; x1 += 1; }
    var y0 = ys.length ? Math.floor((Math.min.apply(null, ys) - 2) / 10) * 10 : 20, y1 = ys.length ? Math.ceil((Math.max.apply(null, ys) + 2) / 10) * 10 : 110;
    if (y1 - y0 < 30) { y0 = Math.max(0, y0 - 10); y1 += 10; }
    var sx = function (lx) { return L + (lx - x0) / (x1 - x0) * (R - L); };
    var sy = function (v) { return B - (v - y0) / (y1 - y0) * (B - T); };
    var g = [];
    g.push('<svg viewBox="0 0 ' + W + " " + H + '" xmlns="http://www.w3.org/2000/svg"><defs><clipPath id="pc"><rect x="' + L + '" y="' + T + '" width="' + (R - L) + '" height="' + (B - T) + '"/></clipPath></defs>');
    var JL = { "-18": "1 aJ", "-17": "10 aJ", "-16": "100 aJ", "-15": "1 fJ", "-14": "10 fJ", "-13": "100 fJ", "-12": "1 pJ", "-11": "10 pJ", "-10": "100 pJ", "-9": "1 nJ", "-8": "10 nJ", "-7": "100 nJ", "-6": "1 µJ", "-5": "10 µJ", "-4": "100 µJ", "-3": "1 mJ" };
    g.push('<g class="axis">');
    var step = (x1 - x0) * 62 > (R - L) ? 2 : 1;   // thin out decade labels when space is short
    for (var lx = x0; lx <= x1; lx++) {
      g.push('<line class="gridline" x1="' + sx(lx) + '" x2="' + sx(lx) + '" y1="' + T + '" y2="' + B + '"/>');
      if ((lx - x0) % step === 0) g.push('<text x="' + sx(lx) + '" y="' + (B + 18) + '" text-anchor="middle">' + (JL[lx] || "1e" + lx + " J") + "</text>");
    }
    for (var yv = y0; yv <= y1; yv += 10) {
      g.push('<line class="gridline" x1="' + L + '" x2="' + R + '" y1="' + sy(yv) + '" y2="' + sy(yv) + '"/>');
      g.push('<text x="' + (L - 8) + '" y="' + (sy(yv) + 4) + '" text-anchor="end">' + yv + "</text>");
    }
    g.push('<line x1="' + L + '" x2="' + R + '" y1="' + B + '" y2="' + B + '"/><line x1="' + L + '" x2="' + L + '" y1="' + T + '" y2="' + B + '"/></g>');
    g.push('<text class="axis-title" x="' + ((L + R) / 2) + '" y="' + (H - 6) + '" text-anchor="middle">Energy per Nyquist sample, P / f' +
      '<tspan baseline-shift="sub" font-size="9">s,Nyq</tspan></text>');
    g.push('<text class="axis-title" transform="translate(12 ' + ((T + B) / 2) + ') rotate(-90)" text-anchor="middle">SNDR (dB)</text>');

    // Schreier FoM contours: SNDR = FoMs + 10 log10(2E); labelled where each line leaves the bottom or right edge
    g.push('<g clip-path="url(#pc)">');
    var k2 = 10 * Math.log10(2);
    [150, 160, 170, 180, 190].forEach(function (fom) {
      var a = fom + k2 + 10 * x0, b = fom + k2 + 10 * x1;
      g.push('<line class="fomline" x1="' + sx(x0) + '" y1="' + sy(a) + '" x2="' + sx(x1) + '" y2="' + sy(b) + '"/>');
    });
    g.push("</g>");
    [150, 160, 170, 180, 190].forEach(function (fom) {
      var ya = fom + k2 + 10 * x0, x, y;                       // where the line enters at the left edge
      if (ya >= y0 + 3 && ya <= y1 - 3) { x = L + 4; y = sy(ya) - 5; }
      else {
        var yb = y0 + 1.5, xb = (yb - fom - k2) / 10;          // otherwise where it crosses the bottom
        if (xb < x0 || xb > x1 || sx(xb) > R - 60) return;
        x = sx(xb) + 5; y = sy(yb) - 3;
      }
      g.push('<text class="fomlabel" x="' + x + '" y="' + y + '">' + fom + "</text>");
    });

    if (!pts.length) {
      g.push('<text class="placeholder" x="' + ((L + R) / 2) + '" y="' + ((T + B) / 2) + '" text-anchor="middle">' +
        (ALL.length ? "No paper in this selection reports SNDR, power and sample rate together." : "No data yet.") + "</text>");
    }
    g.push('<g clip-path="url(#pc)">');
    // draw newest on top
    pts.slice().sort(function (a, b) { return (a.d || "").localeCompare(b.d || ""); }).forEach(function (p) {
      g.push('<circle data-id="' + esc(p.id) + '" cx="' + sx(Math.log10(p.e)).toFixed(1) + '" cy="' + sy(p.s.sndr).toFixed(1) +
        '" r="' + (narrow ? 3.4 : 4.6) + '" fill="' + (ARCH_COLORS[p.prim] || ARCH_COLORS.Other) + '"/>');
    });
    g.push("</g></svg>");
    $("plot").innerHTML = g.join("");
    $("plot-note").textContent = pts.length
      ? pts.length + " of " + VIEW.length + " papers in this selection report SNDR, power and sample rate (or bandwidth for oversampled converters). Dashed lines are constant Schreier FoM, labelled in dB."
      : "Each dot is a paper in the current selection that reports SNDR, power and sample rate (or bandwidth).";
  }

  /* ------------------------------------------------------------ rendering: rows */
  function spec(p, k, text, lbl) {
    if (!text) return '<span class="spec"></span>';
    return '<span class="spec' + (p.ver[k] ? "" : " auto") + '"><span class="lbl">' + lbl + "</span>" + text + "</span>";
  }
  function rowHTML(p) {
    var au = p.au || [];
    var names = au.slice(0, 3).join(", ") + (au.length > 3 ? " et al." : "");
    var tags = p.ar.map(function (a) {
      return '<span class="tag arch" style="background:' + (ARCH_COLORS[a] || ARCH_COLORS.Other) + '">' + esc(a) + "</span>";
    }).concat(p.ap.map(function (a) { return '<span class="tag">' + esc(a) + "</span>"; }));
    if (p.cal) tags.push('<span class="tag">Calibration</span>');
    if (p.ct === "EA") tags.push('<span class="tag">Early access</span>');
    if (p.lv !== "core") tags.push('<span class="tag lv">Converter in abstract only</span>');
    var fresh = META.sweep_done && p.first === META.updated;
    var foms = p.s.foms != null ? spec(p, "foms", p.s.foms.toFixed(1) + " dB", "FoMs")
      : p.fomsCalc != null ? '<span class="spec auto"><span class="lbl">FoMs</span>≈' + p.fomsCalc.toFixed(1) + " dB</span>" : '<span class="spec"></span>';
    return '<div class="tr" role="row" data-id="' + esc(p.id) + '">' +
      '<div class="pub" role="cell"><span class="venue">' + esc(p.v) + "</span><span>" + esc(fmtDate(p.d)) + "</span>" +
      (fresh ? '<span class="new">New</span>' : "") + "</div>" +
      '<div class="paper" role="cell"><a class="title" href="' + esc(p.url || (p.doi ? "https://doi.org/" + p.doi : "#")) +
      '" target="_blank" rel="noopener">' + esc(p.t) + "</a>" +
      (names ? '<p class="by">' + esc(names) + "</p>" : "") +
      ((p.org || []).length ? '<p class="by org">' + esc(p.org.slice(0, 2).join("; ")) + "</p>" : "") +
      (tags.length ? '<div class="tags">' + tags.join("") + "</div>" : "") + "</div>" +
      spec(p, "res", p.s.res ? p.s.res + " b" : "", "Bits") +
      spec(p, "fs", fmtSI(p.s.fs, "S/s"), "fₛ") +
      spec(p, "sndr", p.s.sndr ? p.s.sndr.toFixed(1) + " dB" : "", "SNDR") +
      spec(p, "p", fmtSI(p.s.p, "W"), "Power") +
      spec(p, "node", p.s.node ? p.s.node + " nm" : "", "Node") +
      foms + "</div>";
  }
  function renderRows() {
    var n = VIEW.length;
    $("count").innerHTML = "<strong>" + n.toLocaleString() + "</strong> " + (F.kind === "DAC" ? "DAC" : "ADC") +
      " paper" + (n === 1 ? "" : "s");
    $("rows").innerHTML = VIEW.slice(0, LIMIT).map(rowHTML).join("");
    $("more").hidden = n <= LIMIT;
    $("more").textContent = "Show " + Math.min(PAGE, n - LIMIT) + " more of " + (n - LIMIT).toLocaleString();
    var empty = $("empty");
    if (!ALL.length) {
      empty.hidden = false;
      empty.innerHTML = "No papers collected yet. Run <code>python3 collector/collect.py</code> on the lab server to fill the index (see the README).";
    } else if (!n) {
      empty.hidden = false;
      empty.innerHTML = 'No papers match these filters. <button type="button" class="link-btn" id="reset2">Clear filters</button>';
      $("reset2").onclick = reset;
    } else empty.hidden = true;
  }

  function update(opts) {
    VIEW = ALL.filter(function (p) { return match(p); }).sort(SORTS[F.sort] || SORTS.date);
    if (!opts || !opts.keepLimit) LIMIT = PAGE;
    renderControls();
    renderLegend();
    renderPlot();
    renderRows();
    writeHash();
  }
  function reset() { F = defaults(); update(); }

  /* ------------------------------------------------------------ interaction */
  function toggle(arr, v) { var i = arr.indexOf(v); if (i >= 0) arr.splice(i, 1); else arr.push(v); }
  function bind() {
    var t;
    $("q").addEventListener("input", function (e) { clearTimeout(t); t = setTimeout(function () { F.q = e.target.value.trim(); update(); }, 160); });
    $("kind").addEventListener("click", function (e) { var b = e.target.closest("button"); if (b) { F.kind = b.dataset.v; F.arch = []; update(); } });
    $("venues").addEventListener("click", function (e) { var b = e.target.closest("button"); if (b) { toggle(F.venues, b.dataset.v); update(); } });
    $("apps").addEventListener("click", function (e) { var b = e.target.closest("button"); if (b) { toggle(F.apps, b.dataset.v); update(); } });
    $("legend").addEventListener("click", function (e) { var b = e.target.closest("button"); if (b) { toggle(F.arch, b.dataset.v); update(); } });
    $("y0").addEventListener("change", function (e) { F.y0 = e.target.value; update(); });
    $("y1").addEventListener("change", function (e) { F.y1 = e.target.value; update(); });
    $("country").addEventListener("change", function (e) { F.country = e.target.value; update(); });
    ["related", "cal", "fresh"].forEach(function (k) { $(k).addEventListener("change", function (e) { F[k] = e.target.checked; update(); }); });
    $("sort").addEventListener("change", function (e) { F.sort = e.target.value; update(); });
    $("reset").addEventListener("click", reset);
    $("more").addEventListener("click", function () { LIMIT += PAGE; renderRows(); });
    $("csv").addEventListener("click", downloadCSV);

    var tip = $("tooltip"), fig = document.querySelector(".figure");
    $("plot").addEventListener("mousemove", function (e) {
      var c = e.target.closest("circle");
      if (!c) { tip.hidden = true; return; }
      var p = BYID[c.dataset.id];
      tip.innerHTML = "<b>" + esc(p.t) + "</b>" + esc(p.v + ", " + fmtDate(p.d)) + "<br>" +
        esc([p.s.sndr ? p.s.sndr.toFixed(1) + " dB SNDR" : "", fmtSI(p.s.fs, "S/s"), fmtSI(p.s.p, "W")].filter(Boolean).join(", "));
      var r = fig.getBoundingClientRect();
      tip.hidden = false;
      var x = e.clientX - r.left + 14, y = e.clientY - r.top + 14;
      if (x + 340 > r.width) x = e.clientX - r.left - 340 - 14;
      tip.style.left = Math.max(8, x) + "px"; tip.style.top = y + "px";
    });
    $("plot").addEventListener("mouseleave", function () { tip.hidden = true; });
    $("plot").addEventListener("click", function (e) {
      var c = e.target.closest("circle");
      if (!c) return;
      var idx = VIEW.indexOf(BYID[c.dataset.id]);
      if (idx >= LIMIT) { LIMIT = Math.ceil((idx + 1) / PAGE) * PAGE; renderRows(); }
      var row = document.querySelector('.tr[data-id="' + c.dataset.id + '"]');
      if (row) {
        document.querySelectorAll(".tr.hl").forEach(function (r) { r.classList.remove("hl"); });
        row.classList.add("hl");
        row.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
      }
    });
    $("rows").addEventListener("mouseover", function (e) {
      var r = e.target.closest(".tr");
      document.querySelectorAll("#plot circle.hl").forEach(function (c) { c.classList.remove("hl"); });
      if (r) { var c = document.querySelector('#plot circle[data-id="' + r.dataset.id + '"]'); if (c) { c.classList.add("hl"); c.parentNode.appendChild(c); } }
    });
    window.addEventListener("hashchange", function () { F = defaults(); readHash(); update(); });
    var rw, lastW = $("plot").clientWidth;
    window.addEventListener("resize", function () {
      clearTimeout(rw);
      rw = setTimeout(function () { if ($("plot").clientWidth !== lastW) { lastW = $("plot").clientWidth; renderPlot(); } }, 150);
    });
  }

  function downloadCSV() {
    var cols = ["id", "date", "venue", "title", "authors", "affiliations", "countries", "type", "architectures", "applications",
      "calibration", "bits", "fs_Sps", "bw_Hz", "sndr_dB", "power_W", "node_nm", "foms_dB", "foms_calc_dB", "energy_J", "checked_fields", "url", "doi"];
    var q = function (v) { v = v == null ? "" : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    var lines = [cols.join(",")].concat(VIEW.map(function (p) {
      return [p.id, p.d, p.v, p.t, (p.au || []).join("; "), (p.org || []).join("; "), (p.cn || []).join("; "), p.k,
        p.ar.join("; "), p.ap.join("; "), p.cal ? "yes" : "", p.s.res, p.s.fs, p.s.bw, p.s.sndr, p.s.p, p.s.node,
        p.s.foms, p.fomsCalc, p.e, Object.keys(p.ver).join("; "), p.url, p.doi].map(q).join(",");
    }));
    var blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "adc-census-" + (META.updated || "export") + ".csv";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  /* ------------------------------------------------------------ boot */
  function getJSON(u) { return fetch(u, { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(u + " " + r.status); return r.json(); }); }
  function getText(u) { return fetch(u, { cache: "no-cache" }).then(function (r) { return r.ok ? r.text() : ""; }).catch(function () { return ""; }); }

  Promise.all([getJSON("data/meta.json").catch(function () { return {}; }), getJSON("data/papers.json").catch(function () { return []; }), getText("data/annotations.csv")])
    .then(function (res) {
      META = res[0] || {};
      ALL = applyAnnotations(res[1] || [], parseCSV(res[2] || ""));
      ALL.forEach(function (p) { BYID[p.id] = p; });

      var nA = ALL.filter(function (p) { return p.k === "ADC" && p.lv === "core"; }).length;
      var nD = ALL.filter(function (p) { return p.k === "DAC" && p.lv === "core"; }).length;
      var venues = Object.keys(META.by_venue || {}).length;
      if (ALL.length) {
        $("lede").innerHTML = "<strong>" + nA.toLocaleString() + " ADC</strong> and <strong>" + nD.toLocaleString() +
          " DAC</strong> papers from " + venues + " IEEE solid-state circuits venues, " + esc(fmtDate(META.coverage_from)) +
          " to " + esc(fmtDate(META.coverage_to)) + ". Updated " + esc(META.updated || "") +
          (META.sweep_done && META.last_run_new ? ", with " + META.last_run_new + " papers added in the latest update." : ".") +
          (META.sweep_done ? "" : " The initial collection is still running, so earlier years may be incomplete.");
      } else {
        $("lede").textContent = "A monthly index of ADC and DAC papers in ISSCC, VLSI, JSSC, CICC, ESSCIRC, A-SSCC, SSC-L, TCAS-I/II and TVLSI. The first collection has not run yet.";
      }
      $("fresh").parentNode.hidden = !(META.sweep_done && META.last_run_new);

      var years = ALL.map(function (p) { return p.y; }).filter(Boolean);
      var ymin = years.length ? Math.min.apply(null, years) : 2023, ymax = years.length ? Math.max.apply(null, years) : new Date().getFullYear();
      var opts = "";
      for (var y = ymax; y >= ymin; y--) opts += '<option value="' + y + '">' + y + "</option>";
      $("y0").innerHTML = '<option value="">Any</option>' + opts;
      $("y1").innerHTML = '<option value="">Any</option>' + opts;

      readHash();
      bind();
      update();
    })
    .catch(function (err) {
      $("lede").textContent = "The paper index could not be loaded (" + err.message + ").";
    });
})();
