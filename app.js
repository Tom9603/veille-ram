(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const SVG_NS = "http://www.w3.org/2000/svg";
  const PREFS_KEY = "veille-ram:prefs";
  const STALE_HOURS = 14;
  const CLS = [30, 32, 36];
  const CL_COLOR = { 30: "var(--cl30)", 32: "var(--cl32)", 36: "var(--cl36)" };
  const VIEWS = { marche: "Marché", offres: "Offres", historique: "Historique", reglages: "Réglages" };
  const STOCK = {
    in_stock: { label: "En stock", color: "var(--good)" },
    on_order: { label: "Sur commande", color: "var(--warning)" },
    out_of_stock: { label: "Rupture", color: "var(--critical)" },
    unknown: { label: "Stock non affiché", color: "var(--muted)" },
  };
  const SORT_LABELS = { "price-asc": "prix croissant", "price-desc": "prix décroissant", cl: "latence", shop: "boutique" };

  // ---------- Préférences (mémorisées sur l'appareil) ----------

  const DEFAULT_PREFS = { cl: "all", sort: "price-asc", available: false, verifiedOnly: false, details: false, theme: "auto", period: "all", autoRefresh: true };
  let prefs = { ...DEFAULT_PREFS };
  try { prefs = { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") }; } catch (e) { /* stockage indisponible */ }

  function setPref(key, value) {
    prefs[key] = value;
    try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch (e) { /* tant pis */ }
    if (key === "theme") applyTheme();
    syncControls();
    renderAll();
  }

  // ---------- Formats ----------

  const eurFmt = {
    int: new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }),
    dec: new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", minimumFractionDigits: 2 }),
  };
  const eur = (v) => (v == null ? "—" : (Number.isInteger(v) ? eurFmt.int : eurFmt.dec).format(v));
  const eurRound = (v) => eurFmt.int.format(Math.round(v));
  const perGo = (v) => `${new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v / 32)} €/Go`;
  const dateFmt = new Intl.DateTimeFormat("fr-FR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Paris" });
  const shortFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Paris" });
  const dayFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", timeZone: "Europe/Paris" });
  const rtf = new Intl.RelativeTimeFormat("fr", { numeric: "auto" });

  function relative(date) {
    const minutes = Math.round((date - Date.now()) / 60000);
    if (minutes >= -1) return "à l'instant";
    if (minutes > -60) return rtf.format(minutes, "minute");
    const hours = Math.round(minutes / 60);
    if (Math.abs(hours) < 48) return rtf.format(hours, "hour");
    return rtf.format(Math.round(hours / 24), "day");
  }

  // ---------- DOM (les textes viennent du web : jamais d'innerHTML) ----------

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
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
  const ICONS = {
    check: "M5 12.5l4.5 4.5L19 7.5",
    clock: "M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
    up: "M12 19V5M5 12l7-7 7 7",
    down: "M12 5v14M5 12l7 7 7-7",
  };
  function icon(name) {
    const s = svg("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" });
    s.append(svg("path", { d: ICONS[name] }));
    return s;
  }
  function dot(color) {
    const d = el("span", { class: "dot" });
    d.style.background = color;
    return d;
  }
  function safeUrl(url) {
    try {
      const u = new URL(url);
      return u.protocol === "https:" ? u.href : null;
    } catch (e) {
      return null;
    }
  }
  function deltaChip(d) {
    if (!d) return null;
    return el("span", { class: `delta ${d < 0 ? "down" : "up"}`, title: "Depuis le passage précédent" },
      icon(d < 0 ? "down" : "up"), `${eurRound(Math.abs(d))}`);
  }

  // ---------- Données ----------

  let state = { latest: null, history: [], config: null, loadedAt: 0, fromCache: false };
  const openOffers = new Set();

  // ---------- GitHub (actualisation à la demande) ----------
  // La clé ne quitte jamais ce téléphone : elle n'est envoyée qu'à api.github.com.

  const REPO = "Tom9603/veille-ram";
  const BRANCH = "gh-pages";
  const WORKFLOW = "actualiser.yml";
  const TOKEN_KEY = "veille-ram:gh-token";
  const AUTO_REFRESH_MINUTES = 15;

  function getToken() {
    try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; }
  }
  function setToken(token) {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token); else localStorage.removeItem(TOKEN_KEY);
      return true;
    } catch (e) {
      return false;
    }
  }

  function github(path, options = {}) {
    return fetch(`https://api.github.com/repos/${REPO}${path}`, {
      ...options,
      cache: "no-store",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${getToken()}`,
        "X-GitHub-Api-Version": "2022-11-28",
        ...(options.headers || {}),
      },
    });
  }

  async function getJSON(path) {
    // Avec la clé, on lit le dépôt directement : données à jour sans attendre la republication du site.
    if (getToken() && path.startsWith("data/")) {
      try {
        const res = await github(`/contents/${path}?ref=${BRANCH}`, { headers: { Accept: "application/vnd.github.raw+json" } });
        if (res.ok) return { data: await res.json(), cached: false };
      } catch (e) { /* repli sur le site ci-dessous */ }
    }
    const res = await fetch(`${path}?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`${path} : HTTP ${res.status}`);
    return { data: await res.json(), cached: res.headers.get("x-veille-cache") === "1" };
  }

  async function load() {
    $("refresh").classList.add("spinning");
    document.body.classList.add("loading");
    try {
      const [latest, history, config] = await Promise.all([
        getJSON("data/latest.json"),
        getJSON("data/history.json"),
        getJSON("config.json").catch(() => ({ data: null })),
      ]);
      state = { latest: latest.data, history: history.data, config: config.data, loadedAt: Date.now(), fromCache: latest.cached || history.cached };
      renderAll();
    } catch (err) {
      console.error(err);
      showBanner(state.latest
        ? "Impossible d'actualiser : affichage des dernières données connues."
        : "Impossible de charger les données. Vérifie ta connexion puis touche ↻.");
    } finally {
      if (!refreshing) $("refresh").classList.remove("spinning");
      document.body.classList.remove("loading");
    }
  }

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  let refreshing = false;
  let syncTimer;

  function showSync(message, kind) {
    clearTimeout(syncTimer);
    const box = $("sync");
    box.className = `sync${kind ? ` is-${kind}` : ""}`;
    $("sync-text").textContent = message;
    box.hidden = false;
    if (kind === "done") syncTimer = setTimeout(() => { box.hidden = true; }, 4000);
  }

  async function latestRunId() {
    const res = await github(`/actions/workflows/${WORKFLOW}/runs?per_page=1`);
    if (res.status === 401 || res.status === 403 || res.status === 404) throw new Error("auth");
    const data = await res.json();
    return data.workflow_runs && data.workflow_runs[0] ? data.workflow_runs[0].id : 0;
  }

  // Lance une vraie recherche de prix (GitHub Actions), attend la fin, puis recharge les données.
  async function refreshPrices() {
    if (refreshing) return;
    if (!getToken()) {
      await load();
      showSync("Données rechargées. Pour lancer une nouvelle recherche de prix, ajoute ta clé GitHub dans Réglages.", "error");
      return;
    }
    refreshing = true;
    $("refresh").classList.add("spinning");
    const started = Date.now();
    const tick = () => showSync(`Recherche des prix en cours… ${Math.round((Date.now() - started) / 1000)} s`);
    tick();
    try {
      const before = await latestRunId();
      const res = await github(`/actions/workflows/${WORKFLOW}/dispatches`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ref: BRANCH }),
      });
      if (res.status === 401 || res.status === 403 || res.status === 404) throw new Error("auth");
      if (!res.ok) throw new Error(`GitHub a répondu ${res.status}`);

      let run = null;
      while (Date.now() - started < 5 * 60 * 1000) {
        await sleep(4000);
        tick();
        const list = await github(`/actions/workflows/${WORKFLOW}/runs?per_page=5`);
        if (!list.ok) continue;
        const runs = (await list.json()).workflow_runs || [];
        run = runs.filter((r) => r.id > before).sort((a, b) => a.id - b.id)[0] || null;
        if (run && run.status === "completed") break;
      }
      if (!run || run.status !== "completed") throw new Error("la recherche prend plus de temps que prévu, les prix arriveront dans quelques minutes");
      if (run.conclusion !== "success") throw new Error("la recherche a échoué côté GitHub, réessaie plus tard");
      await load();
      showSync(`Prix actualisés à l'instant (${state.latest.offers.length} offres).`, "done");
    } catch (err) {
      console.error(err);
      showSync(err.message === "auth"
        ? "Clé GitHub refusée : vérifie-la dans Réglages (droit Actions en lecture et écriture sur veille-ram)."
        : `Actualisation impossible : ${err.message}.`, "error");
    } finally {
      refreshing = false;
      $("refresh").classList.remove("spinning");
    }
  }

  function maybeAutoRefresh() {
    if (!getToken() || !prefs.autoRefresh || !state.latest || refreshing) return;
    const ageMinutes = (Date.now() - new Date(state.latest.checked_at)) / 60000;
    if (ageMinutes > AUTO_REFRESH_MINUTES) refreshPrices();
  }

  // Tirer l'écran vers le bas depuis le haut de la page pour actualiser.
  function setupPullToRefresh() {
    const ptr = $("ptr");
    const THRESHOLD = 80;
    let startY = null;
    let pull = 0;
    const reset = () => {
      startY = null;
      pull = 0;
      ptr.style.transition = "transform 0.2s, opacity 0.2s";
      ptr.style.transform = "translateY(-60px)";
      ptr.style.opacity = "0";
      ptr.classList.remove("is-ready");
    };
    window.addEventListener("touchstart", (e) => {
      if (window.scrollY > 0 || refreshing || e.touches.length !== 1) return;
      startY = e.touches[0].clientY;
      ptr.style.transition = "none";
    }, { passive: true });
    window.addEventListener("touchmove", (e) => {
      if (startY === null) return;
      pull = Math.max(0, e.touches[0].clientY - startY);
      if (pull === 0) return;
      const dist = Math.min(pull * 0.5, 70);
      ptr.style.transform = `translateY(${dist - 60}px) rotate(${pull * 2}deg)`;
      ptr.style.opacity = String(Math.min(1, pull / THRESHOLD));
      ptr.classList.toggle("is-ready", pull >= THRESHOLD);
    }, { passive: true });
    window.addEventListener("touchend", () => {
      if (startY === null) return;
      const go = pull >= THRESHOLD;
      reset();
      if (go) refreshPrices();
    });
    window.addEventListener("touchcancel", reset);
  }

  const thresholds = () => state.latest.thresholds_eur;
  const limitFor = (cl) => (cl === 30 ? thresholds().cl30 : thresholds().cl32_36);
  const selectedCls = () => (prefs.cl === "all" ? CLS : [Number(prefs.cl)]);
  const offerKey = (o) => `${o.shop}|${o.ref || o.name}|${o.cl}`;

  function bestListed(cl) {
    return state.latest.offers
      .filter((o) => o.stock !== "out_of_stock" && (cl == null || o.cl === cl))
      .reduce((best, o) => (!best || o.price_eur < best.price_eur ? o : best), null);
  }

  // Les anciennes lignes d'historique regroupaient CL32 et CL36 dans « cl32_36 ».
  function historyPoints() {
    return state.history.map((h) => {
      const merged = h.cl32_36;
      const pick = (cl) => {
        const v = h[`cl${cl}`];
        if (v !== undefined) return v;
        return merged && merged.cl === cl ? merged : null;
      };
      const p = { t: new Date(h.checked_at) };
      for (const cl of CLS) p[cl] = pick(cl) ? pick(cl).price_eur : null;
      return p;
    }).sort((a, b) => a.t - b.t);
  }

  function changeSincePrevious(cl) {
    const pts = historyPoints();
    if (pts.length < 2) return null;
    const [a, b] = pts.slice(-2);
    return a[cl] != null && b[cl] != null ? Math.round((b[cl] - a[cl]) * 100) / 100 : null;
  }

  // ---------- Navigation ----------

  function currentView() {
    const h = location.hash.slice(1);
    return VIEWS[h] ? h : "marche";
  }

  function showView(scroll) {
    const v = currentView();
    for (const key of Object.keys(VIEWS)) $(`view-${key}`).hidden = key !== v;
    $("page-title").textContent = VIEWS[v];
    $("cl-switch").hidden = v === "reglages";
    document.querySelectorAll(".tabbar a").forEach((a) => {
      if (a.dataset.tab === v) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    if (v === "historique" && state.latest) renderChart();
    if (scroll) window.scrollTo({ top: 0 });
  }

  // ---------- Rendu ----------

  function showBanner(text) {
    $("banner").textContent = text || "";
    $("banner").hidden = !text;
  }

  function renderAll() {
    if (!state.latest) return;
    const age = (Date.now() - new Date(state.latest.checked_at)) / 3.6e6;
    if (state.fromCache) showBanner("Hors ligne : affichage des dernières données enregistrées.");
    else if (age > STALE_HOURS) showBanner(`Aucune analyse depuis ${Math.floor(age)} h : la veille a peut-être raté un passage.`);
    else showBanner("");
    if (state.latest.product && state.latest.product.label) $("product").textContent = state.latest.product.label;
    renderMarche();
    renderOffres();
    renderHistorique();
    renderReglages();
  }

  function renderMarche() {
    const latest = state.latest;
    const cls = selectedCls();
    const deals = latest.offers.filter((o) => o.deal && cls.includes(o.cl)).sort((a, b) => a.price_eur - b.price_eur);
    const deal = deals[0] || null;
    const offer = deal || bestListed(prefs.cl === "all" ? null : Number(prefs.cl));

    const pill = $("status-pill");
    pill.classList.toggle("is-deal", !!deal);
    pill.replaceChildren(icon(deal ? "check" : "clock"), deal ? "Bonne affaire !" : "Pas d'affaire pour l'instant");
    $("updated-pill").textContent = `Mis à jour ${relative(new Date(latest.checked_at))}`;

    $("hero").classList.toggle("is-deal", !!deal);
    const scope = prefs.cl === "all" ? "toutes latences" : `CL${prefs.cl}`;
    $("hero-label").textContent = deal ? `Bonne affaire · CL${deal.cl}` : `Meilleur prix · ${scope}`;
    $("hero-price").textContent = offer ? eur(offer.price_eur) : "—";
    $("hero-name").textContent = offer ? `${offer.name}${prefs.cl === "all" ? ` · CL${offer.cl}` : ""}` : "Aucune offre disponible à ce passage";

    const facts = $("hero-facts");
    facts.replaceChildren();
    if (offer) {
      const stock = STOCK[offer.stock] || STOCK.unknown;
      const gap = offer.price_eur - limitFor(offer.cl);
      facts.append(
        el("span", null, offer.shop),
        el("span", null, dot(stock.color), stock.label),
        el("span", null, gap > 0 ? `${eurRound(gap)} au-dessus du seuil (${eur(limitFor(offer.cl))})` : `${eurRound(-gap)} sous le seuil`),
      );
      const d = changeSincePrevious(offer.cl);
      if (d) facts.append(el("span", null, deltaChip(d), "depuis le passage précédent"));
    }
    const url = offer && safeUrl(offer.url);
    $("hero-link").hidden = !url;
    if (url) $("hero-link").href = url;

    const list = $("by-cl");
    list.replaceChildren(...CLS.map((cl) => {
      const best = bestListed(cl);
      return el("button", {
        type: "button",
        class: `row-cl${prefs.cl === String(cl) ? " is-selected" : ""}`,
        onclick: () => { setPref("cl", String(cl)); location.hash = "#offres"; },
      },
      el("span", { class: "cl-name" }, dot(CL_COLOR[cl]), el("span", null, `CL${cl}`, el("span", { class: "cl-sub" }, `seuil ${eur(limitFor(cl))}`))),
      el("span", { class: "cl-right" },
        el("span", { class: "cl-price" }, best ? eur(best.price_eur) : "—",
          el("small", null, best ? deltaChip(changeSincePrevious(cl)) || el("span", { class: "cl-sub" }, best.shop) : el("span", { class: "cl-sub" }, "aucune offre"))),
        el("span", { class: "chev", "aria-hidden": "true" }, "›")));
    }));

    const trend = $("trend");
    trend.replaceChildren(el("p", null, latest.trend || "Pas de commentaire sur ce passage."));
    if (latest.blocked_sources && latest.blocked_sources.length) {
      trend.append(el("p", { class: "caption" }, `Sources inaccessibles ce passage : ${latest.blocked_sources.join(", ")}`));
    }
    $("next-run").textContent = nextRun();
  }

  function scheduleTimes() {
    return (state.config && state.config.schedule && state.config.schedule.times) || ["11:58", "19:58"];
  }

  function nextRun() {
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
      .formatToParts(new Date()).map((p) => [p.type, p.value]));
    const now = Number(parts.hour) * 60 + Number(parts.minute);
    const mins = scheduleTimes().map((t) => { const [h, m] = t.split(":").map(Number); return h * 60 + m; }).sort((a, b) => a - b);
    const fmt = (m) => `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}`;
    const next = mins.find((m) => m > now);
    return next !== undefined ? `Aujourd'hui à ${fmt(next)}` : `Demain à ${fmt(mins[0])}`;
  }

  function filteredOffers() {
    const cls = selectedCls();
    const sorters = {
      "price-asc": (a, b) => a.price_eur - b.price_eur,
      "price-desc": (a, b) => b.price_eur - a.price_eur,
      cl: (a, b) => a.cl - b.cl || a.price_eur - b.price_eur,
      shop: (a, b) => a.shop.localeCompare(b.shop, "fr") || a.price_eur - b.price_eur,
    };
    return state.latest.offers
      .filter((o) => cls.includes(o.cl))
      .filter((o) => !prefs.available || o.stock === "in_stock" || o.stock === "on_order")
      .filter((o) => !prefs.verifiedOnly || o.verified)
      .sort(sorters[prefs.sort] || sorters["price-asc"]);
  }

  function renderOffres() {
    const offers = filteredOffers();
    const total = state.latest.offers.filter((o) => selectedCls().includes(o.cl)).length;
    $("result-count").textContent = offers.length
      ? `${offers.length} offre${offers.length > 1 ? "s" : ""}${offers.length < total ? ` sur ${total}` : ""} · ${SORT_LABELS[prefs.sort] || ""}`
      : "";
    const list = $("offers");
    if (!offers.length) {
      list.replaceChildren(el("li", { class: "empty" },
        el("p", null, total ? "Aucune offre ne correspond à tes filtres." : "Aucune offre relevée pour cette latence à ce passage."),
        total ? el("button", { type: "button", class: "btn btn-ghost", onclick: () => { prefs.available = false; setPref("verifiedOnly", false); } }, "Retirer les filtres") : null));
      return;
    }
    list.replaceChildren(...offers.map(offerCard));
  }

  function offerCard(o) {
    const stock = STOCK[o.stock] || STOCK.unknown;
    const key = offerKey(o);
    const open = prefs.details || openOffers.has(key);
    const gap = o.price_eur - limitFor(o.cl);
    const url = safeUrl(o.url);
    const li = el("li", { class: ["offer", o.deal && "is-deal", o.stock === "out_of_stock" && "is-out", open && "is-open"].filter(Boolean).join(" ") });
    const head = el("button", { type: "button", class: "offer-head", "aria-expanded": String(open) },
      el("span", { class: "offer-top" },
        el("span", { class: "badge" }, dot(CL_COLOR[o.cl]), `CL${o.cl}`),
        o.deal && el("span", { class: "badge deal" }, "Bonne affaire")),
      el("span", { class: "offer-price" }, eur(o.price_eur)),
      el("span", { class: "offer-name" }, o.name),
      el("span", { class: "offer-per-go" }, perGo(o.price_eur)),
      el("span", { class: "offer-sub", style: "grid-column: 1 / -1" },
        el("span", null, o.shop),
        el("span", null, dot(stock.color), stock.label)));
    const more = el("div", { class: "offer-more" }, el("div", null,
      el("dl", { class: "facts" },
        fact("Référence", o.ref || "non précisée", true),
        fact("Écart au seuil", gap > 0 ? `+${eurRound(gap)} (seuil ${eur(limitFor(o.cl))})` : `${eurRound(-gap)} sous le seuil`),
        fact("Prix", o.verified ? "Vérifié chez la boutique" : "Non vérifié (comparateur)"),
        fact("Vendeur", o.marketplace ? "Marketplace (vendeur tiers)" : "Boutique"),
        fact("Stock", stock.label),
        fact("Prix au Go", perGo(o.price_eur))),
      url && el("div", { class: "offer-actions" },
        el("a", { class: "btn btn-primary", href: url, target: "_blank", rel: "noopener noreferrer" }, `Voir chez ${o.shop} ↗`))));
    head.addEventListener("click", () => {
      const isOpen = li.classList.toggle("is-open");
      head.setAttribute("aria-expanded", String(isOpen));
      if (isOpen) openOffers.add(key); else openOffers.delete(key);
    });
    li.append(head, more);
    return li;
  }

  function fact(label, value, wide) {
    return el("div", { class: wide ? "wide" : null }, el("dt", null, label), el("dd", null, value));
  }

  // ---------- Historique ----------

  function periodPoints() {
    const pts = historyPoints();
    if (prefs.period === "all") return pts;
    const since = Date.now() - Number(prefs.period) * 864e5;
    return pts.filter((p) => p.t.getTime() >= since);
  }

  function renderHistorique() {
    const cls = selectedCls();
    $("chart-title").textContent = prefs.cl === "all" ? "Meilleur prix par latence" : `Meilleur prix · CL${prefs.cl}`;
    $("legend").replaceChildren(...(cls.length > 1 ? cls.map((cl) => {
      const key = el("span", { class: "key" });
      key.style.background = CL_COLOR[cl];
      return el("li", null, key, `CL${cl}`);
    }) : []));

    const pts = periodPoints();
    $("stats-rows").replaceChildren(...cls.map((cl) => {
      const values = pts.map((p) => p[cl]).filter((v) => v != null);
      const last = [...pts].reverse().find((p) => p[cl] != null);
      return el("tr", null,
        el("td", null, el("span", { class: "cl-cell" }, dot(CL_COLOR[cl]), `CL${cl}`)),
        el("td", null, last ? eur(last[cl]) : "—"),
        el("td", null, values.length ? eur(Math.min(...values)) : "—"),
        el("td", null, values.length ? eur(Math.max(...values)) : "—"));
    }));
    $("history-rows").replaceChildren(...[...pts].reverse().map((p) =>
      el("tr", null, el("td", null, shortFmt.format(p.t)), ...CLS.map((cl) => el("td", null, eur(p[cl]))))));

    if (currentView() === "historique") renderChart();
  }

  function niceStep(range) {
    for (const step of [10, 20, 25, 50, 100, 200, 250, 500]) if (range / step <= 5) return step;
    return 1000;
  }

  let hideChartTip = () => {};

  function renderChart() {
    const box = $("chart");
    const tooltip = $("tooltip");
    box.querySelectorAll("svg").forEach((n) => n.remove());
    tooltip.hidden = true;

    const series = selectedCls().map((cl) => ({ key: cl, name: `CL${cl}`, color: CL_COLOR[cl] }));
    const points = periodPoints().filter((p) => series.some((s) => p[s.key] != null));
    $("chart-hint").textContent = !points.length
      ? "Aucun relevé sur cette période pour cette latence."
      : points.length < 2
        ? "L'historique se remplit à chaque passage (2 par jour)."
        : "Touche ou glisse sur le graphique pour lire les prix d'une date.";
    if (!points.length) return;

    const W = Math.max(280, box.clientWidth);
    const H = Math.round(Math.min(260, Math.max(190, W * 0.55)));
    const m = { top: 14, right: 48, bottom: 24, left: 38 };
    const iw = W - m.left - m.right;
    const ih = H - m.top - m.bottom;

    const refs = [];
    if (series.some((s) => s.key === 30)) refs.push({ v: thresholds().cl30, label: "seuil CL30", color: "var(--cl30)" });
    if (series.some((s) => s.key !== 30)) refs.push({ v: thresholds().cl32_36, label: series.length === 1 ? `seuil ${series[0].name}` : "seuil CL32/36", color: series.length === 1 ? series[0].color : "var(--muted)" });

    const values = points.flatMap((p) => series.map((s) => p[s.key])).filter((v) => v != null).concat(refs.map((r) => r.v));
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
      "aria-label": "Évolution du meilleur prix. Les valeurs sont dans le tableau « Tous les relevés ».",
    });

    for (let v = lo; v <= hi; v += step) {
      root.append(svg("line", { x1: m.left, x2: m.left + iw, y1: y(v), y2: y(v), stroke: v === lo ? "var(--axis)" : "var(--grid)", "stroke-width": 1 }));
      const label = svg("text", { x: m.left - 6, y: y(v) + 4, "text-anchor": "end" });
      label.textContent = Math.round(v);
      root.append(label);
    }

    const spanDays = (t1 - t0) / 864e5;
    const fmt = (d) => (spanDays < 2 ? shortFmt.format(d) : dayFmt.format(d));
    const nTicks = Math.max(2, Math.min(4, Math.floor(iw / 90)));
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

    refs.sort((a, b) => b.v - a.v).forEach((r, i) => {
      const yy = y(r.v);
      root.append(svg("line", { x1: m.left, x2: m.left + iw, y1: yy, y2: yy, stroke: r.color, "stroke-width": 1, opacity: 0.55 }));
      const label = svg("text", { x: m.left + 4, y: i === 0 ? yy - 5 : yy + 13 });
      label.textContent = `${r.label} · ${r.v} €`;
      root.append(label);
    });

    const ends = [];
    for (const s of series) {
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
    const ys = ends.map((e) => e.y).sort((a, b) => a - b);
    if (ys.every((v, i) => i === 0 || v - ys[i - 1] >= 14)) {
      for (const e of ends) {
        const label = svg("text", { class: "end-label", x: e.x + 8, y: e.y + 4 });
        label.textContent = eurRound(e.v);
        root.append(label);
      }
    }

    const cross = svg("line", { y1: m.top, y2: m.top + ih, stroke: "var(--axis)", "stroke-width": 1, visibility: "hidden" });
    const marks = series.map((s) => svg("circle", { r: 5, fill: s.color, stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" }));
    const hit = svg("rect", { x: m.left - 8, y: 0, width: iw + 16, height: H, fill: "transparent" });
    root.append(cross, ...marks, hit);

    let current = -1;
    function show(i) {
      current = Math.max(0, Math.min(points.length - 1, i));
      const p = points[current];
      const px = x(p.t);
      cross.setAttribute("x1", px);
      cross.setAttribute("x2", px);
      cross.setAttribute("visibility", "visible");
      series.forEach((s, k) => {
        const v = p[s.key];
        marks[k].setAttribute("visibility", v == null ? "hidden" : "visible");
        if (v != null) { marks[k].setAttribute("cx", px); marks[k].setAttribute("cy", y(v)); }
      });
      tooltip.replaceChildren(
        el("div", { class: "t-date" }, dateFmt.format(p.t)),
        ...series.map((s) => {
          const key = el("span", { class: "key" });
          key.style.background = s.color;
          return el("div", { class: "t-row" }, key, el("strong", null, eur(p[s.key])), el("span", null, s.name));
        }),
      );
      tooltip.hidden = false;
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

  // ---------- Réglages ----------

  function renderReglages() {
    const t = thresholds();
    $("th-cl30").textContent = eur(t.cl30);
    $("th-cl32-36").textContent = eur(t.cl32_36);
    $("set-schedule").textContent = scheduleTimes().map((s) => s.replace(":", "h")).join(" · ");
    $("set-last").textContent = shortFmt.format(new Date(state.latest.checked_at));
    const blocked = state.latest.blocked_sources || [];
    $("set-blocked").textContent = blocked.length ? blocked.join(", ") : "aucune";
  }

  function applyTheme() {
    const root = document.documentElement;
    if (prefs.theme === "light" || prefs.theme === "dark") root.dataset.theme = prefs.theme;
    else delete root.dataset.theme;
    const page = getComputedStyle(root).getPropertyValue("--page").trim();
    document.querySelector('meta[name="theme-color"]').setAttribute("content", page || "#f4f4f1");
  }

  function setChecked(container, attr, value) {
    container.querySelectorAll(`[${attr}]`).forEach((b) => b.setAttribute("aria-checked", String(b.getAttribute(attr) === value)));
  }

  function syncControls() {
    setChecked($("cl-switch"), "data-cl", prefs.cl);
    setChecked($("period"), "data-period", prefs.period);
    setChecked($("set-theme"), "data-theme-value", prefs.theme);
    $("sort").value = prefs.sort;
    $("set-sort").value = prefs.sort;
    $("set-cl").value = prefs.cl;
    $("f-stock").setAttribute("aria-pressed", String(prefs.available));
    $("f-verified").setAttribute("aria-pressed", String(prefs.verifiedOnly));
    $("f-details").setAttribute("aria-pressed", String(prefs.details));
    $("set-stock").checked = prefs.available;
    $("set-verified").checked = prefs.verifiedOnly;
    $("set-details").checked = prefs.details;
    $("set-auto").checked = prefs.autoRefresh;
    renderTokenStatus();
  }

  function renderTokenStatus() {
    const on = !!getToken();
    const status = $("token-status");
    status.textContent = on ? "Activée" : "Non configurée";
    status.classList.toggle("is-on", on);
    $("token-remove").hidden = !on;
    $("token-input").placeholder = on ? "Clé enregistrée (colle une nouvelle clé pour la remplacer)" : "Colle ta clé GitHub (github_pat_…)";
  }

  async function saveToken(e) {
    e.preventDefault();
    const input = $("token-input");
    const token = input.value.trim();
    if (!token) return;
    const previous = getToken();
    if (!setToken(token)) {
      showSync("Impossible d'enregistrer la clé sur ce navigateur (stockage bloqué).", "error");
      return;
    }
    try {
      await latestRunId();
      input.value = "";
      renderTokenStatus();
      showSync("Clé enregistrée : le bouton ↻ lance maintenant une vraie recherche de prix.", "done");
    } catch (err) {
      setToken(previous);
      renderTokenStatus();
      showSync("Cette clé ne fonctionne pas : il faut le droit Actions en lecture et écriture sur le dépôt veille-ram.", "error");
    }
  }

  // ---------- Événements ----------

  $("cl-switch").addEventListener("click", (e) => { const b = e.target.closest("[data-cl]"); if (b) setPref("cl", b.dataset.cl); });
  $("period").addEventListener("click", (e) => { const b = e.target.closest("[data-period]"); if (b) setPref("period", b.dataset.period); });
  $("set-theme").addEventListener("click", (e) => { const b = e.target.closest("[data-theme-value]"); if (b) setPref("theme", b.dataset.themeValue); });
  $("sort").addEventListener("change", (e) => setPref("sort", e.target.value));
  $("set-sort").addEventListener("change", (e) => setPref("sort", e.target.value));
  $("set-cl").addEventListener("change", (e) => setPref("cl", e.target.value));
  $("f-stock").addEventListener("click", () => setPref("available", !prefs.available));
  $("f-verified").addEventListener("click", () => setPref("verifiedOnly", !prefs.verifiedOnly));
  $("f-details").addEventListener("click", () => { openOffers.clear(); setPref("details", !prefs.details); });
  $("set-stock").addEventListener("change", (e) => setPref("available", e.target.checked));
  $("set-verified").addEventListener("change", (e) => setPref("verifiedOnly", e.target.checked));
  $("set-details").addEventListener("change", (e) => setPref("details", e.target.checked));
  $("set-auto").addEventListener("change", (e) => setPref("autoRefresh", e.target.checked));
  $("token-form").addEventListener("submit", saveToken);
  $("token-remove").addEventListener("click", () => {
    setToken("");
    renderTokenStatus();
    showSync("Clé supprimée de ce téléphone.", "done");
  });
  $("refresh").addEventListener("click", refreshPrices);
  $("set-refresh").addEventListener("click", refreshPrices);
  window.addEventListener("hashchange", () => showView(true));
  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState !== "visible" || refreshing) return;
    if (Date.now() - state.loadedAt > 60000) await load();
    maybeAutoRefresh();
  });
  document.addEventListener("pointerdown", (e) => { if (!$("chart").contains(e.target)) hideChartTip(); });
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (state.latest && currentView() === "historique") renderChart(); }, 150);
  });
  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch((err) => console.warn("Service worker :", err));
  }

  applyTheme();
  syncControls();
  showView(false);
  setupPullToRefresh();
  load().then(maybeAutoRefresh);
})();
