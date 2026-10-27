// Conference deadline bar shown above the Census masthead.
// Data: deadlines.json (edited by hand). The nearest confirmed deadline is pinned on the left;
// the rest rotate one card at a time when they do not all fit.
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

  function ics(list) {
    const stamp = d => new Date(d).toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
    const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MCAS Lab//Census deadlines//EN", "CALSCALE:GREGORIAN"];
    list.forEach(c => lines.push("BEGIN:VEVENT", `UID:${c.id}-${c.edition}-deadline@mixedcas-lab.github.io`, `DTSTAMP:${stamp(Date.now())}`,
      `DTSTART:${stamp(c.t)}`, `DTEND:${stamp(c.t)}`, `SUMMARY:${c.id} ${c.edition} paper deadline`,
      `DESCRIPTION:${(c.name + " · " + venueLocal(c) + (c.note ? " · " + c.note : "")).replace(/[,;]/g, "\\$&")}`, `URL:${c.url || ""}`,
      "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Deadline in 7 days", "TRIGGER:-P7D", "END:VALARM", "END:VEVENT"));
    lines.push("END:VCALENDAR");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\r\n")], { type: "text/calendar" }));
    a.download = "circuits-deadlines.ics";
    document.body.appendChild(a); a.click(); a.remove();
  }

  function rotate(view, track) {
    let paused = false, busy = false, resume;
    const pause = () => { paused = true; clearTimeout(resume); };
    const play = (ms) => { clearTimeout(resume); resume = setTimeout(() => { paused = false; }, ms || 0); };
    view.addEventListener("mouseenter", pause);
    view.addEventListener("mouseleave", () => play(600));
    view.addEventListener("focusin", pause);
    view.addEventListener("focusout", () => play(600));
    view.addEventListener("touchstart", pause, { passive: true });
    view.addEventListener("touchend", () => play(6000), { passive: true });
    setInterval(() => {
      if (paused || busy || document.hidden || track.children.length < 2) return;
      if (track.scrollWidth <= view.clientWidth + 2) return;           // everything fits: stay still
      const first = track.firstElementChild;
      const step = first.getBoundingClientRect().width + parseFloat(getComputedStyle(track).columnGap || 8);
      busy = true;
      track.style.transition = "transform .6s cubic-bezier(.4,0,.2,1)";
      track.style.transform = `translateX(${-step}px)`;
      track.addEventListener("transitionend", function done() {
        track.removeEventListener("transitionend", done);
        track.style.transition = "none";
        track.appendChild(first);
        track.style.transform = "none";
        busy = false;
      });
    }, ROTATE_MS);
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
    const rest = list.filter(c => c !== next);

    const bar = document.createElement("section");
    bar.className = "dl";
    bar.setAttribute("aria-label", "Upcoming paper deadlines");
    bar.innerHTML = `<div class="wrap dl-in">
      <div class="dl-lab"><span>DEADLINES</span><small>KST · live</small></div>
      ${next ? `<div class="dl-pin">${card(next, true)}</div>` : ""}
      <div class="dl-view"><div class="dl-track">${rest.map(c => card(c, false)).join("")}</div></div>
      ${live.length ? `<button type="button" class="dl-ics" title="Download confirmed deadlines as a calendar file (.ics), with a reminder 7 days before">+ Calendar</button>` : ""}
    </div>`;
    document.body.prepend(bar);

    const btn = bar.querySelector(".dl-ics");
    if (btn) btn.addEventListener("click", () => ics(live));

    const tick = () => bar.querySelectorAll(".dl-cd[data-t]").forEach(n => {
      let s = Math.max(0, Math.floor((+n.dataset.t - Date.now()) / 1000));
      const d = Math.floor(s / 86400); s -= d * 86400;
      const h = Math.floor(s / 3600); s -= h * 3600;
      const m = Math.floor(s / 60); s -= m * 60;
      n.innerHTML = `${d ? d + "<small>d</small> " : ""}${pad(h)}:${pad(m)}:${pad(s)}`;
      n.closest(".dl-c").classList.toggle("soon", d < 7);
    });
    tick(); setInterval(tick, 1000);

    if (!reduced) rotate(bar.querySelector(".dl-view"), bar.querySelector(".dl-track"));
  }

  fetch(SRC, { cache: "no-cache" }).then(r => r.ok ? r.json() : null).then(d => d && render(d)).catch(() => {});
})();
