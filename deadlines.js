// Conference deadline bar shown above the Census masthead.
// Data: deadlines.json (edited by hand). All cards rotate one at a time when they do not all fit
// (nearest confirmed deadline highlighted); swipe or drag to move by hand. Cards are sized so none is cut off.
(function () {
  "use strict";
  const SRC = "deadlines.json";
  const ROTATE_MS = 3800;
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const reduced = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pad = n => String(n).padStart(2, "0");
  const kst = t => new Date(t).toLocaleString("en-US", { timeZone: "Asia/Seoul", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).replace(",", "");
  const venueLocal = c => {
    const m = /T(\d\d):(\d\d)/.exec(c.due), d = /^(\d{4})-(\d\d)-(\d\d)/.exec(c.due);
    return m && d ? `${MONTHS[+d[2] - 1]} ${+d[3]} ${m[1]}:${m[2]} ${c.tz || ""}`.trim() : "";
  };
  const estLabel = e => { const m = /^(\d{4})-(\d\d)/.exec(e || ""); return m ? `~${MONTHS[+m[2] - 1]} ${m[1]}` : "TBA"; };

  function card(c, isNext) {
    const live = !!c.t;
    const tip = [c.name, c.dates && c.venue ? `${c.venue} · ${c.dates}` : c.venue,
      live ? `Deadline: ${venueLocal(c)}${c.note ? " · " + c.note : ""}` : `Not announced yet${c.ref ? " · " + c.ref : ""}`].filter(Boolean).join("\n");
    return `<a class="dl-c${live ? "" : " est"}${isNext ? " next" : ""}" href="${esc(c.url || "#")}" target="_blank" rel="noopener" title="${esc(tip)}">
      <span class="dl-h"><b>${esc(c.id)}</b> ${esc(c.edition)}${live ? '<i class="dl-dot" aria-hidden="true"></i>' : ""}</span>
      ${live ? `<span class="dl-cd" data-t="${c.t}"></span><span class="dl-t">${kst(c.t)} KST</span>`
             : `<span class="dl-cd">${estLabel(c.est)}</span><span class="dl-t">est. · not announced</span>`}
      <span class="dl-v">${esc(c.venue || "TBA")}</span>
    </a>`;
  }


  // Size the rotating cards so a whole number of them fills the space: no card is ever cut off.
  const MIN_W = 150, MAX_W = 210;
  function fit(view, track) {
    const gap = parseFloat(getComputedStyle(track).columnGap) || 8;
    const avail = view.clientWidth, count = track.children.length;
    if (!avail || !count) return;
    const n = Math.max(1, Math.floor((avail + gap) / (MIN_W + gap)));
    const w = n >= count ? Math.min(MAX_W, (avail - (count - 1) * gap) / count) : (avail - (n - 1) * gap) / n;
    track.style.setProperty("--dl-w", Math.floor(w) + "px");
  }

  // Auto-advance one card every ROTATE_MS; swipe (touch) or drag sideways to move by hand.
  function rotate(view, track) {
    let paused = false, busy = false, resume, x0 = null, y0 = 0;
    const gap = () => parseFloat(getComputedStyle(track).columnGap) || 8;
    const fits = () => track.scrollWidth <= view.clientWidth + 2;
    const hold = ms => { paused = true; clearTimeout(resume); if (ms) resume = setTimeout(() => { paused = false; }, ms); };

    function step(dir) {                                // dir = +1: next card, -1: previous card
      if (busy || track.children.length < 2 || fits()) return;
      const first = track.firstElementChild, last = track.lastElementChild;
      const w = first.getBoundingClientRect().width + gap();
      if (reduced) { dir > 0 ? track.appendChild(first) : track.prepend(last); return; }
      busy = true;
      if (dir < 0) {                                    // put the last card in front, then slide it in
        track.style.transition = "none";
        track.prepend(last);
        track.style.transform = `translateX(${-w}px)`;
        void track.offsetWidth;
      }
      track.style.transition = "transform .5s cubic-bezier(.4,0,.2,1)";
      track.style.transform = dir > 0 ? `translateX(${-w}px)` : "translateX(0)";
      track.addEventListener("transitionend", function done() {
        track.removeEventListener("transitionend", done);
        track.style.transition = "none";
        if (dir > 0) track.appendChild(first);
        track.style.transform = "none";
        busy = false;
      });
    }

    // mouse over a card pauses (so it can be clicked); leaving resumes
    track.addEventListener("mouseover", e => { if (e.target.closest(".dl-c")) hold(); });
    track.addEventListener("mouseleave", () => hold(800));
    view.addEventListener("focusin", () => hold());
    view.addEventListener("focusout", () => hold(800));

    // touch swipe and mouse drag
    const down = (x, y) => { x0 = x; y0 = y; hold(); };
    const up = (x, y) => {
      if (x0 === null) return;
      const dx = x - x0, dy = y - y0; x0 = null;
      if (Math.abs(dx) > 30 && Math.abs(dx) > Math.abs(dy)) step(dx < 0 ? 1 : -1);
      hold(6000);
      return Math.abs(dx) > 30;
    };
    view.addEventListener("touchstart", e => down(e.touches[0].clientX, e.touches[0].clientY), { passive: true });
    view.addEventListener("touchend", e => up(e.changedTouches[0].clientX, e.changedTouches[0].clientY), { passive: true });
    let dragged = false;
    view.addEventListener("pointerdown", e => { if (e.pointerType === "mouse") { dragged = false; down(e.clientX, e.clientY); } });
    addEventListener("pointerup", e => { if (e.pointerType === "mouse" && x0 !== null) dragged = up(e.clientX, e.clientY); });
    view.addEventListener("click", e => { if (dragged) { e.preventDefault(); dragged = false; } }, true);
    view.addEventListener("dragstart", e => e.preventDefault());

    setInterval(() => { if (!paused && !document.hidden) step(1); }, ROTATE_MS);
  }

  function render(data) {
    const now = Date.now();
    const all = (data.conferences || []).map(c => Object.assign({}, c, { t: c.due ? Date.parse(c.due) : null }));
    const has = new Set(all.map(c => c.id + "|" + c.edition));
    // A passed deadline rolls over to next year's edition as an estimate, until deadlines.json is updated.
    const list = all.map(c => {
      if (!c.t || c.t > now) return c;
      const ed = String(+c.edition + 1), d = new Date(c.t);
      if (has.has(c.id + "|" + ed)) return null;
      return { id: c.id, edition: ed, name: c.name, venue: "TBA", url: c.url, t: null,
        est: `${d.getUTCFullYear() + 1}-${pad(d.getUTCMonth() + 1)}`, ref: `${c.edition} deadline: ${venueLocal(c)}` };
    }).filter(Boolean)
      .sort((a, b) => (a.t || Date.parse((a.est || "9999-12") + "-28")) - (b.t || Date.parse((b.est || "9999-12") + "-28")));
    if (!list.length) return;
    const live = list.filter(c => c.t);
    const next = live[0];

    const bar = document.createElement("section");
    bar.className = "dl";
    bar.setAttribute("aria-label", "Upcoming paper deadlines");
    bar.innerHTML = `<div class="wrap dl-in">
      <div class="dl-lab"><span>DEADLINES</span><small>KST · live</small></div>
      <div class="dl-view"><div class="dl-track">${list.map(c => card(c, c === next)).join("")}</div></div>
    </div>`;
    document.body.prepend(bar);

    const view = bar.querySelector(".dl-view"), track = bar.querySelector(".dl-track");
    fit(view, track);
    if (window.ResizeObserver) new ResizeObserver(() => fit(view, track)).observe(view);
    else addEventListener("resize", () => fit(view, track));

    const tick = () => bar.querySelectorAll(".dl-cd[data-t]").forEach(n => {
      let s = Math.max(0, Math.floor((+n.dataset.t - Date.now()) / 1000));
      const d = Math.floor(s / 86400); s -= d * 86400;
      const h = Math.floor(s / 3600); s -= h * 3600;
      const m = Math.floor(s / 60); s -= m * 60;
      n.innerHTML = `${d ? d + "<small>d</small> " : ""}${pad(h)}:${pad(m)}:${pad(s)}`;
      n.closest(".dl-c").classList.toggle("soon", d < 7);
    });
    tick(); setInterval(tick, 1000);

    rotate(view, track);
  }

  fetch(SRC, { cache: "no-cache" }).then(r => r.ok ? r.json() : null).then(d => d && render(d)).catch(() => {});
})();
