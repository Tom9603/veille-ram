(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const SVG_NS = "http://www.w3.org/2000/svg";
  const STALE_HOURS = 14;

  const STOCK = {
    in_stock: { label: "En stock", color: "var(--good)" },
    on_order: { label: "Sur commande", color: "var(--warning)" },
    out_of_stock: { label: "Rupture", color: "var(--critical)" },
    unknown: { label: "Stock ?", color: "var(--muted)" },
  };

  const eurFmt = {
    int: new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }),
    dec: new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", minimumFractionDigits: 2 }),
  };
  const eur = (v) => (v == null ? "—" : (Number.isInteger(v) ? eurFmt.int : eurFmt.dec).format(v));
  const eurRound = (v) => eurFmt.int.format(Math.round(v));
  const signedEur = (v) => (v > 0 ? "+" : "−") + eur(Math.abs(v));

  const dateFmt = new Intl.DateTimeFormat("fr-FR", {
    weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Paris",
  });
  const dayFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", timeZone: "Europe/Paris" });
  const hourFmt = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", timeZone: "Europe/Paris" });
  const rtf = new Intl.RelativeTimeFormat("fr", { numeric: "auto" });

  function relative(date) {
    const minutes = Math.round((date - Date.now()) / 60000);
    if (Math.abs(minutes) < 60) return rtf.format(minutes, "minute");
    const hours = Math.round(minutes / 60);
    if (Math.abs(hours) < 48) return rtf.format(hours, "hour");
    return rtf.format(Math.round(hours / 24), "day");
  }

  // Les textes viennent du web (relevés de l'agent) : on ne passe jamais par innerHTML.
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") node.className = v;
      else node.setAttribute(k, v);
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      node.append(c instanceof Node ? c : String(c));
    }
    return node;
  }

  function svg(tag, attrs) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
    return node;
  }

  function safeUrl(url) {
    try {
      const u = new URL(url);
      return u.protocol === "https:" ? u.href : null;
    } catch {
      return null;
    }
  }

  function dot(color) {
    const d = el("span", { class: "dot" });
    d.style.background = color;
    return d;
  }

  const ICONS = {
    check: "M5 12.5l4.5 4.5L19 7.5",
    clock: "M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
  };
  function icon(name) {
    const s = svg("svg", { viewBox: "0 0 24 24", width: "16", height: "16", "aria-hidden": "true" });
    s.append(svg("path", {
      d: ICONS[name], fill: "none", stroke: "currentColor", "stroke-width": "2.2",
      "stroke-linecap": "round", "stroke-linejoin": "round",
    }));
    return s;
  }

  // ---------- Chargement ----------

  let state = { latest: null, history: [], config: null, loadedAt: 0 };
  let hideChartTip = () => {};

  async function getJSON(path) {
    const res = await fetch(`${path}?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`${path} : HTTP ${res.status}`);
    return { data: await res.json(), cached: res.headers.get("x-veille-cache") === "1" };
  }

  async function load() {
    const btn = $("refresh");
    btn.classList.add("spinning");
    document.body.classList.add("loading");
    try {
      const [latest, history, config] = await Promise.all([
        getJSON("data/latest.json"),
        getJSON("data/history.json"),
        getJSON("config.json").catch(() => ({ data: null })),
      ]);
      state = { latest: latest.data, history: history.data, config: config.data, loadedAt: Date.now() };
      render(latest.cached || history.cached);
    } catch (err) {
      showBanner(state.latest
        ? "Impossible d'actualiser, affichage des dernières données connues."
        : "Impossible de charger les données. Vérifie ta connexion puis touche ↻.");
      console.error(err);
    } finally {
      btn.classList.remove("spinning");
      document.body.classList.remove("loading");
    }
  }

  function showBanner(text) {
    const b = $("banner");
    b.textContent = text || "";
    b.hidden = !text;
  }

  // ---------- Rendu ----------

  function render(fromCache) {
    const { latest, history, config } = state;
    const t = latest.thresholds_eur;
    const checkedAt = new Date(latest.checked_at);
    const ageHours = (Date.now() - checkedAt) / 3.6e6;

    if (fromCache) showBanner("Hors ligne : affichage des dernières données enregistrées.");
    else if (ageHours > STALE_HOURS) showBanner(`Aucune analyse depuis ${Math.floor(ageHours)} h : la veille a peut-être raté un passage.`);
    else showBanner("");

    if (latest.product && latest.product.label) $("product").textContent = latest.product.label;
    if (config && config.schedule) {
      const times = config.schedule.times.map((x) => x.replace(":", "h")).join(" et ");
      $("schedule").textContent = `Analyses à ${times} (heure de Paris).`;
    }

    renderHero(latest, t);
    renderAlt(latest, t);

    $("when-value").textContent = relative(checkedAt);
    $("when-meta").textContent = dateFmt.format(checkedAt);

    renderChart();
    renderHistoryTable(history);
    renderOffers(latest.offers || []);
    renderNotes(latest);
  }

  function renderHero(latest, t) {
    const hero = $("hero");
    const status = $("status");
    const deal = latest.deal ? latest.offers.find((o) => o.deal) : null;
    const offer = deal || (latest.best && latest.best.cl30);
    const limit = offer && offer.cl !== 30 ? t.cl32_36 : t.cl30;

    hero.classList.toggle("is-deal", !!deal);
    status.classList.toggle("is-deal", !!deal);
    status.replaceChildren(icon(deal ? "check" : "clock"), deal ? "Bonne affaire !" : "Pas encore d'affaire");

    $("hero-label").textContent = deal ? `Bonne affaire CL${deal.cl}` : "Meilleur prix CL30";
    $("hero-value").textContent = offer ? eur(offer.price_eur) : "—";
    $("hero-meta").textContent = offer
      ? [offer.name, offer.shop, (STOCK[offer.stock] || STOCK.unknown).label].join(" · ")
      : "Aucun kit CL30 trouvé à ce passage.";

    const gap = $("hero-gap");
    gap.replaceChildren();
    if (offer) {
      const diff = offer.price_eur - limit;
      gap.append(diff > 0
        ? el("span", { class: "up" }, `Seuil ${eur(limit)} · encore ${eurRound(diff)} au-dessus`)
        : el("span", { class: "ok" }, `${eurRound(-diff)} sous ton seuil de ${eur(limit)}`));
      const change = latest.change_since_previous_eur && latest.change_since_previous_eur.cl30;
      if (!deal && change) gap.append(el("br"), el("span", { class: "up" }, `${signedEur(change)} depuis le passage précédent`));
    }

    const link = $("hero-link");
    const url = offer && safeUrl(offer.url);
    link.hidden = !url;
    if (url) link.href = url;
  }

  function renderAlt(latest, t) {
    const alt = latest.best && latest.best.cl32_36;
    $("alt-value").textContent = alt ? eur(alt.price_eur) : "—";
    const meta = $("alt-meta");
    meta.replaceChildren();
    if (alt) {
      meta.append(`CL${alt.cl} · ${alt.shop}`, el("br"));
      const diff = alt.price_eur - t.cl32_36;
      meta.append(diff > 0 ? `seuil ${eur(t.cl32_36)} (+${eurRound(diff)})` : `sous le seuil de ${eur(t.cl32_36)}`);
    } else {
      meta.append(`seuil ${eur(t.cl32_36)}`);
    }
  }

  function renderOffers(offers) {
    const list = $("offers");
    list.replaceChildren();
    if (!offers.length) {
      list.append(el("li", { class: "offer" }, el("span", { class: "offer-meta" }, "Aucune offre relevée à ce passage.")));
      return;
    }
    for (const o of offers) {
      const stock = STOCK[o.stock] || STOCK.unknown;
      const url = safeUrl(o.url);
      const classes = ["offer", o.deal && "is-deal", o.stock === "out_of_stock" && "is-out"].filter(Boolean).join(" ");
      list.append(el("li", { class: classes },
        el("div", { class: "offer-name" },
          el("span", { class: "chip" }, dot(o.cl === 30 ? "var(--series-1)" : "var(--series-2)"), `CL${o.cl}`),
          el("span", null, o.name)),
        el("div", { class: "offer-price" }, eur(o.price_eur)),
        el("div", { class: "offer-meta" }, [o.ref, o.shop].filter(Boolean).join(" · ")),
        el("div", { class: "offer-stock" }, dot(stock.color), stock.label),
        el("div", { class: "offer-flags" },
          o.deal && el("span", { class: "chip deal" }, "Bonne affaire"),
          !o.verified && el("span", { class: "chip" }, "Prix non vérifié"),
          o.marketplace && el("span", { class: "chip" }, "Marketplace"),
          url && el("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, "Voir l'offre →")),
      ));
    }
  }

  function renderNotes(latest) {
    const notes = $("notes");
    notes.replaceChildren();
    if (latest.trend) notes.append(el("p", null, el("strong", null, "Tendance : "), latest.trend));
    if (latest.blocked_sources && latest.blocked_sources.length) {
      notes.append(el("p", null, el("strong", null, "Sources inaccessibles : "), latest.blocked_sources.join(", ")));
    }
  }

  function historyPoints(history) {
    return history.map((h) => ({
      t: new Date(h.checked_at),
      cl30: h.cl30 ? h.cl30.price_eur : null,
      alt: h.cl32_36 ? h.cl32_36.price_eur : null,
    }));
  }

  function renderHistoryTable(history) {
    const rows = $("history-rows");
    rows.replaceChildren();
    for (const p of historyPoints(history).reverse()) {
      rows.append(el("tr", null, el("td", null, dateFmt.format(p.t)), el("td", null, eur(p.cl30)), el("td", null, eur(p.alt))));
    }
  }

  // ---------- Graphique ----------

  const SERIES = [
    { key: "cl30", name: "CL30", color: "var(--series-1)", threshold: "cl30" },
    { key: "alt", name: "CL32/36", color: "var(--series-2)", threshold: "cl32_36" },
  ];

  function niceStep(range) {
    for (const step of [10, 20, 25, 50, 100, 200, 250, 500]) if (range / step <= 5) return step;
    return 1000;
  }

  function renderChart() {
    const box = $("chart");
    const tooltip = $("tooltip");
    box.querySelectorAll("svg").forEach((n) => n.remove());
    tooltip.hidden = true;

    const points = historyPoints(state.history);
    const t = state.latest.thresholds_eur;
    $("chart-hint").textContent = points.length < 2
      ? "L'historique se remplit à chaque passage (2 par jour)."
      : "Touche ou glisse sur le graphique pour lire les prix d'une date.";
    if (!points.length) return;

    const W = Math.max(280, box.clientWidth);
    const H = Math.round(Math.min(240, Math.max(180, W * 0.5)));
    const m = { top: 14, right: 52, bottom: 24, left: 40 };
    const iw = W - m.left - m.right;
    const ih = H - m.top - m.bottom;

    const values = points.flatMap((p) => [p.cl30, p.alt]).filter((v) => v != null).concat([t.cl30, t.cl32_36]);
    let lo = Math.min(...values);
    let hi = Math.max(...values);
    const step = niceStep(hi - lo + 40);
    lo = Math.floor((lo - 10) / step) * step;
    hi = Math.ceil((hi + 10) / step) * step;
    const y = (v) => m.top + ih - ((v - lo) / (hi - lo)) * ih;

    let t0 = points[0].t.getTime();
    let t1 = points[points.length - 1].t.getTime();
    if (t1 - t0 < 3.6e6) { t0 -= 12 * 3.6e6; t1 += 12 * 3.6e6; }
    const x = (d) => m.left + ((d.getTime() - t0) / (t1 - t0)) * iw;

    const root = svg("svg", {
      viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", tabindex: "0",
      "aria-label": "Évolution du meilleur prix CL30 et CL32/36. Le détail est dans « Voir les données ».",
    });

    // Grille et axe Y
    for (let v = lo; v <= hi; v += step) {
      root.append(svg("line", { x1: m.left, x2: m.left + iw, y1: y(v), y2: y(v), stroke: v === lo ? "var(--axis)" : "var(--grid)", "stroke-width": 1 }));
      const label = svg("text", { x: m.left - 6, y: y(v) + 4, "text-anchor": "end" });
      label.textContent = Math.round(v);
      root.append(label);
    }

    // Axe X : 2 à 4 repères selon la largeur, sans doublon
    const spanDays = (t1 - t0) / 864e5;
    const fmt = (d) => (spanDays < 2 ? `${dayFmt.format(d)} ${hourFmt.format(d).replace(/\s/g, "")}` : dayFmt.format(d));
    const nTicks = Math.max(2, Math.min(4, Math.floor(iw / 85)));
    const ticks = points.length === 1
      ? [{ d: points[0].t, anchor: "middle" }]
      : Array.from({ length: nTicks }, (_, i) => ({
        d: new Date(t0 + ((t1 - t0) * i) / (nTicks - 1)),
        anchor: i === 0 ? "start" : i === nTicks - 1 ? "end" : "middle",
      }));
    let lastLabel = "";
    for (const tick of ticks) {
      const text = fmt(tick.d);
      if (text === lastLabel) continue;
      lastLabel = text;
      const label = svg("text", { x: x(tick.d), y: H - 6, "text-anchor": tick.anchor });
      label.textContent = text;
      root.append(label);
    }

    // Seuils (lignes de référence)
    SERIES.forEach((s, i) => {
      const v = t[s.threshold];
      const yy = y(v);
      root.append(svg("line", { x1: m.left, x2: m.left + iw, y1: yy, y2: yy, stroke: s.color, "stroke-width": 1, opacity: 0.5 }));
      const label = svg("text", { class: "ref-label", x: m.left + 4, y: i === 0 ? yy - 5 : yy + 13 });
      label.textContent = `seuil ${s.name} · ${v} €`;
      root.append(label);
    });

    // Séries
    const ends = [];
    for (const s of SERIES) {
      let seg = [];
      const flush = () => {
        if (seg.length > 1) {
          root.append(svg("path", {
            d: seg.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p[s.key]).toFixed(1)}`).join(""),
            fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round",
          }));
        } else if (seg.length === 1) {
          root.append(svg("circle", { cx: x(seg[0].t), cy: y(seg[0][s.key]), r: 4, fill: s.color, stroke: "var(--surface)", "stroke-width": 2 }));
        }
        seg = [];
      };
      for (const p of points) (p[s.key] == null ? flush() : seg.push(p));
      flush();
      const last = [...points].reverse().find((p) => p[s.key] != null);
      if (last) {
        root.append(svg("circle", { cx: x(last.t), cy: y(last[s.key]), r: 4, fill: s.color, stroke: "var(--surface)", "stroke-width": 2 }));
        ends.push({ x: x(last.t), y: y(last[s.key]), v: last[s.key] });
      }
    }
    // Étiquettes de fin, seulement si elles ne se chevauchent pas
    if (ends.length < 2 || Math.abs(ends[0].y - ends[1].y) >= 14) {
      for (const e of ends) {
        const label = svg("text", { class: "end-label", x: e.x + 8, y: e.y + 4 });
        label.textContent = eurRound(e.v);
        root.append(label);
      }
    }

    // Réticule + infobulle
    const cross = svg("line", { y1: m.top, y2: m.top + ih, stroke: "var(--axis)", "stroke-width": 1, visibility: "hidden" });
    const marks = SERIES.map((s) => svg("circle", { r: 5, fill: s.color, stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" }));
    root.append(cross, ...marks);
    const hit = svg("rect", { x: m.left - 8, y: 0, width: iw + 16, height: H, fill: "transparent" });
    root.append(hit);

    let current = -1;
    function show(i) {
      current = Math.max(0, Math.min(points.length - 1, i));
      const p = points[current];
      const px = x(p.t);
      cross.setAttribute("x1", px);
      cross.setAttribute("x2", px);
      cross.setAttribute("visibility", "visible");
      SERIES.forEach((s, k) => {
        const v = p[s.key];
        marks[k].setAttribute("visibility", v == null ? "hidden" : "visible");
        if (v != null) { marks[k].setAttribute("cx", px); marks[k].setAttribute("cy", y(v)); }
      });
      tooltip.replaceChildren(
        el("div", { class: "t-date" }, dateFmt.format(p.t)),
        ...SERIES.map((s) => {
          const key = el("span", { class: "key" });
          key.style.background = s.color;
          return el("div", { class: "t-row" }, key, el("strong", null, eur(p[s.key])), el("span", null, s.name));
        }),
      );
      tooltip.hidden = false;
      // À côté du réticule, du côté où il reste le plus de place
      const scale = box.clientWidth / W;
      const left = px * scale;
      const tw = tooltip.offsetWidth;
      const side = left > box.clientWidth / 2 ? left - tw - 12 : left + 12;
      tooltip.style.left = `${Math.max(0, Math.min(box.clientWidth - tw, side))}px`;
      tooltip.style.top = "0px";
    }
    function hide() {
      current = -1;
      cross.setAttribute("visibility", "hidden");
      marks.forEach((mk) => mk.setAttribute("visibility", "hidden"));
      tooltip.hidden = true;
    }
    function nearest(evt) {
      const rect = root.getBoundingClientRect();
      const px = ((evt.clientX - rect.left) / rect.width) * W;
      let best = 0;
      points.forEach((p, i) => { if (Math.abs(x(p.t) - px) < Math.abs(x(points[best].t) - px)) best = i; });
      return best;
    }
    hit.addEventListener("pointermove", (e) => show(nearest(e)));
    hit.addEventListener("pointerdown", (e) => show(nearest(e)));
    hit.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") hide(); });
    root.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        show(current < 0 ? points.length - 1 : current + (e.key === "ArrowRight" ? 1 : -1));
      } else if (e.key === "Escape") hide();
    });
    root.addEventListener("blur", hide);
    hideChartTip = hide;

    box.prepend(root);
  }

  // ---------- Démarrage ----------

  $("refresh").addEventListener("click", load);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && Date.now() - state.loadedAt > 60000) load();
  });
  document.addEventListener("pointerdown", (e) => {
    if (!$("chart").contains(e.target)) hideChartTip();
  });
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => state.latest && renderChart(), 150);
  });

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch((err) => console.warn("Service worker :", err));
  }
  load();
})();
