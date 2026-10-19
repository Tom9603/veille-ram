(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const SVG_NS = "http://www.w3.org/2000/svg";
  const PREFS_KEY = "veille-ram:prefs";
  // Catégories suivies : AMD Ryzen 7 7800X3D neuf, en version Box (boîte, garantie AMD)
  // et en version Tray (sans boîte, garantie du vendeur).
  const GROUPS = ["box", "tray"];
  const GROUP = {
    box: { label: "Box", long: "Version Box", sub: "En boîte, garantie AMD 3 ans", color: "var(--box)" },
    tray: { label: "Tray", long: "Version Tray", sub: "Sans boîte, garantie vendeur", color: "var(--tray)" },
  };
  const groupOf = (o) => (o.version === "tray" ? "tray" : "box");
  const versionLabel = (o) => GROUP[groupOf(o)].label;
  const VIEWS = { marche: "Marché", offres: "Offres", historique: "Historique", reglages: "Réglages" };
  const STOCK = {
    in_stock: { label: "En stock", color: "var(--good)" },
    on_order: { label: "Sur commande", color: "var(--warning)" },
    out_of_stock: { label: "Rupture", color: "var(--critical)" },
    unknown: { label: "Stock non affiché", color: "var(--muted)" },
  };
  const SORT_LABELS = { "price-asc": "prix croissant", "price-desc": "prix décroissant", version: "version", shop: "boutique" };

  // ---------- Préférences (mémorisées sur l'appareil) ----------

  const DEFAULT_PREFS = { cat: "all", sort: "price-asc", available: false, verifiedOnly: false, details: false, theme: "auto", period: "all" };
  let prefs = { ...DEFAULT_PREFS };
  try { prefs = { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") }; } catch (e) { /* stockage indisponible */ }
  // Préférences de l'ancienne veille RAM (latences, tri par CL) : remises par défaut.
  if (!GROUP[prefs.cat]) prefs.cat = "all";
  if (!SORT_LABELS[prefs.sort]) prefs.sort = "price-asc";
  delete prefs.cl;

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
  const dateFmt = new Intl.DateTimeFormat("fr-FR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Paris" });
  const shortFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Paris" });
  const dayFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", timeZone: "Europe/Paris" });
  const rtf = new Intl.RelativeTimeFormat("fr", { numeric: "auto" });
  const hourFmt = { format: (d) => new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Paris" }).format(d).replace(":", "h") };

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

  // ---------- Relevé à la demande ----------
  // ↻ publie une demande sur un canal ntfy que le robot de relevé (GitHub Actions)
  // surveille en continu : il relève les prix (1 à 2 minutes) et les publie. Sans clé.

  const NTFY_DEFAULT = { server: "https://ntfy.sh", topic: "veille-ram-vxgh897lgs", refresh_topic: "veille-ram-vxgh897lgs-releve" };
  const ntfy = () => ({ ...NTFY_DEFAULT, ...((state.config && state.config.ntfy) || {}) });
  const REFRESH_TIMEOUT_MS = 4 * 60 * 1000;

  async function getJSON(path) {
    const res = await fetch(`${path}?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`${path} : HTTP ${res.status}`);
    return { data: await res.json(), cached: res.headers.get("x-veille-cache") === "1" };
  }

  async function load() {
    $("refresh").classList.add("spinning");
    document.body.classList.add("loading");
    try {
      const [latest, history, config] = await Promise.all([
        getJSON("data/cpu/latest.json"),
        getJSON("data/cpu/history.json"),
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
    if (kind === "done" || kind === "info") syncTimer = setTimeout(() => { box.hidden = true; }, kind === "info" ? 5000 : 4000);
  }

  // Demande un relevé au robot, attend qu'il soit publié, puis recharge les données.
  async function refreshPrices() {
    if (refreshing) return;
    refreshing = true;
    $("refresh").classList.add("spinning");
    const started = Date.now();
    const tick = () => showSync(`Relevé des prix en cours… ${Math.round((Date.now() - started) / 1000)} s`);
    tick();
    const ticker = setInterval(tick, 1000);
    try {
      const before = state.latest ? state.latest.checked_at : "";
      const { server, refresh_topic: topic } = ntfy();
      const res = await fetch(`${server.replace(/\/$/, "")}/${topic}`, { method: "POST", body: "↻", cache: "no-store" });
      if (res.status === 429) throw new Error("trop de demandes, réessaie dans quelques minutes");
      if (!res.ok) throw new Error(`le service de demande a répondu ${res.status}`);
      // Le relevé prend 1 à 2 minutes, puis le site se met à jour (moins d'une minute).
      while (Date.now() - started < REFRESH_TIMEOUT_MS) {
        await sleep(6000);
        let fresh = null;
        try { fresh = (await getJSON("data/cpu/latest.json")).data; } catch (e) { /* réseau : on réessaie */ }
        if (fresh && fresh.checked_at !== before) {
          await load();
          showSync(`Prix relevés à l'instant (${state.latest.offers.length} offres).`, "done");
          return;
        }
      }
      throw new Error("le robot n'a pas répondu à temps, les prix arriveront au prochain relevé");
    } catch (err) {
      console.error(err);
      showSync(`Actualisation impossible : ${err.message}.`, "error");
    } finally {
      clearInterval(ticker);
      refreshing = false;
      $("refresh").classList.remove("spinning");
    }
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

  const thresholds = () => state.latest.thresholds_eur || {};
  const groupLimit = (g) => {
    const v = thresholds()[g] ?? thresholds().box;
    return typeof v === "number" ? v : null;
  };
  const limitFor = (o) => groupLimit(groupOf(o));
  const selectedGroups = () => (GROUP[prefs.cat] ? [prefs.cat] : GROUPS);
  const offerKey = (o) => `${o.shop}|${o.ref || o.name}|${groupOf(o)}|${o.url}`;
  const gapText = (o) => {
    if (limitFor(o) == null) return "";
    const gap = o.price_eur - limitFor(o);
    return gap > 0 ? `${eurRound(gap)} au-dessus du seuil` : `${eurRound(-gap)} sous le seuil`;
  };
  const hasDeal = (g) => state.latest.offers.some((o) => o.deal && groupOf(o) === g);

  function bestListed(g) {
    return state.latest.offers
      .filter((o) => o.stock !== "out_of_stock" && (g == null || groupOf(o) === g))
      .reduce((best, o) => (!best || o.price_eur < best.price_eur ? o : best), null);
  }

  // Relevés incomplets (une source bloquée) : meilleurs prix peut-être faussés, non tracés.
  function historyPoints() {
    return state.history.filter((h) => !h.partial).map((h) => {
      const p = { t: new Date(h.checked_at) };
      for (const g of GROUPS) p[g] = h[g] ? h[g].price_eur : null;
      return p;
    }).sort((a, b) => a.t - b.t);
  }

  function changeSincePrevious(g) {
    const pts = historyPoints();
    if (pts.length < 2) return null;
    const [a, b] = pts.slice(-2);
    return a[g] != null && b[g] != null ? Math.round((b[g] - a[g]) * 100) / 100 : null;
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
    $("cat-switch").hidden = v === "reglages";
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
    // Un relevé par heure de 6h à 23h : en journée, 2 h sans relevé signalent un problème ; la nuit, 8 h.
    const day = parisClock().hour >= 8;
    if (state.fromCache) showBanner("Hors ligne : affichage des dernières données enregistrées.");
    else if (age > (day ? 2 : 8)) showBanner(`Aucun relevé depuis ${Math.floor(age)} h : le robot a peut-être raté un passage. Touche ↻ pour en lancer un.`);
    else showBanner("");
    if (state.latest.product && state.latest.product.label) $("product").textContent = state.latest.product.label;
    renderMarche();
    renderOffres();
    renderHistorique();
    renderReglages();
  }

  function renderMarche() {
    const latest = state.latest;
    const groups = selectedGroups();
    const deals = latest.offers.filter((o) => o.deal && groups.includes(groupOf(o))).sort((a, b) => a.price_eur - b.price_eur);
    const deal = deals[0] || null;
    const offer = deal || bestListed(groups.length === 1 ? groups[0] : null);
    // Une affaire sur l'autre version que celle affichée : on le dit, et un toucher l'affiche.
    const elsewhere = !deal && GROUPS.find((g) => !groups.includes(g) && hasDeal(g));

    const pill = $("status-pill");
    pill.classList.toggle("is-deal", !!(deal || elsewhere));
    pill.classList.toggle("is-link", !!elsewhere);
    pill.onclick = elsewhere ? () => setPref("cat", "all") : null;
    pill.replaceChildren(icon(deal || elsewhere ? "check" : "clock"),
      deal ? "Bonne affaire !" : elsewhere ? `Bonne affaire en ${GROUP[elsewhere].label} › voir`
        : groups.length === 1 ? `Pas d'affaire en ${GROUP[groups[0]].label}` : "Pas d'affaire pour l'instant");
    $("updated-pill").textContent = `Mis à jour ${relative(new Date(latest.checked_at))}`;

    $("hero").classList.toggle("is-deal", !!deal);
    const scope = groups.length === 1 ? GROUP[groups[0]].long : "Box et Tray";
    $("hero-label").textContent = deal ? `Bonne affaire · ${versionLabel(deal)}` : `Meilleur prix · ${scope}`;
    $("hero-price").textContent = offer ? eur(offer.price_eur) : "—";
    $("hero-name").textContent = offer ? `${offer.name} · ${versionLabel(offer)}` : "Aucune offre disponible à ce relevé";

    const facts = $("hero-facts");
    facts.replaceChildren();
    if (offer) {
      const stock = STOCK[offer.stock] || STOCK.unknown;
      facts.append(
        el("span", null, offer.shop),
        el("span", null, dot(stock.color), stock.label),
        el("span", null, gapText(offer)),
      );
      const d = changeSincePrevious(groupOf(offer));
      if (d) facts.append(el("span", null, deltaChip(d), "depuis le passage précédent"));
    }
    const url = offer && safeUrl(offer.url);
    $("hero-link").hidden = !url;
    if (url) $("hero-link").href = url;

    const list = $("by-cat");
    list.replaceChildren(...GROUPS.map((g) => {
      const best = bestListed(g);
      const out = best ? 0 : latest.offers.filter((o) => groupOf(o) === g).length;   // toutes en rupture ?
      return el("button", {
        type: "button",
        class: `row-cat${prefs.cat === g ? " is-selected" : ""}`,
        onclick: () => { setPref("cat", g); location.hash = "#offres"; },
      },
      el("span", { class: "cat-name" }, dot(GROUP[g].color), el("span", null, GROUP[g].label,
        hasDeal(g) && el("span", { class: "badge deal" }, "Bonne affaire"),
        el("span", { class: "cat-sub" }, `${GROUP[g].sub} · seuil ${eur(groupLimit(g))}`))),
      el("span", { class: "cat-right" },
        el("span", { class: "cat-price" }, best ? eur(best.price_eur) : "—",
          el("small", null, best ? deltaChip(changeSincePrevious(g)) || el("span", { class: "cat-sub" }, best.shop)
            : el("span", { class: "cat-sub" }, out ? `en rupture (${out} offre${out > 1 ? "s" : ""})` : "aucune offre"))),
        el("span", { class: "chev", "aria-hidden": "true" }, "›")));
    }));

    const trend = $("trend");
    trend.replaceChildren(el("p", null, latest.trend || "Pas de commentaire sur ce passage."));
    if (latest.blocked_sources && latest.blocked_sources.length) {
      trend.append(el("p", { class: "caption" }, `Sources inaccessibles ce passage : ${latest.blocked_sources.join(", ")}`));
    }
    $("next-run").textContent = nextRun();
  }

  function parisClock() {
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
      .formatToParts(new Date()).map((p) => [p.type, p.value]));
    return { hour: Number(parts.hour), minute: Number(parts.minute) };
  }

  // Relevés (et notifications) à hh:13, de 6h à 23h, heure de Paris.
  function relevesSlots() {
    const s = (state.config && state.config.schedule) || {};
    const minute = s.minute ?? 13;
    const slots = [];
    for (let h = s.from_hour ?? 6; h <= (s.to_hour ?? 23); h++) slots.push(h * 60 + minute);
    return slots;
  }

  function nextRun() {
    const { hour, minute } = parisClock();
    const now = hour * 60 + minute;
    const slots = relevesSlots();
    const fmt = (m) => `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}`;
    const next = slots.find((m) => m > now);
    return next !== undefined ? `Aujourd'hui à ${fmt(next)}` : `Demain à ${fmt(slots[0])}`;
  }

  function filteredOffers() {
    const groups = selectedGroups();
    const sorters = {
      "price-asc": (a, b) => a.price_eur - b.price_eur,
      "price-desc": (a, b) => b.price_eur - a.price_eur,
      version: (a, b) => GROUPS.indexOf(groupOf(a)) - GROUPS.indexOf(groupOf(b)) || a.price_eur - b.price_eur,
      shop: (a, b) => a.shop.localeCompare(b.shop, "fr") || a.price_eur - b.price_eur,
    };
    return state.latest.offers
      .filter((o) => groups.includes(groupOf(o)))
      .filter((o) => !prefs.available || o.stock === "in_stock" || o.stock === "on_order")
      .filter((o) => !prefs.verifiedOnly || o.verified || o.via)
      .sort(sorters[prefs.sort] || sorters["price-asc"]);
  }

  function renderOffres() {
    const offers = filteredOffers();
    const total = state.latest.offers.filter((o) => selectedGroups().includes(groupOf(o))).length;
    $("result-count").textContent = offers.length
      ? `${offers.length} offre${offers.length > 1 ? "s" : ""}${offers.length < total ? ` sur ${total}` : ""} · ${SORT_LABELS[prefs.sort] || ""}`
      : "";
    const list = $("offers");
    if (!offers.length) {
      list.replaceChildren(el("li", { class: "empty" },
        el("p", null, total ? "Aucune offre ne correspond à tes filtres." : "Aucune offre relevée pour cette version à ce relevé."),
        total ? el("button", { type: "button", class: "btn btn-ghost", onclick: () => { prefs.available = false; setPref("verifiedOnly", false); } }, "Retirer les filtres") : null));
      return;
    }
    list.replaceChildren(...offers.map(offerCard));
  }

  function offerCard(o) {
    const stock = STOCK[o.stock] || STOCK.unknown;
    const key = offerKey(o);
    const open = prefs.details || openOffers.has(key);
    const url = safeUrl(o.url);
    const li = el("li", { class: ["offer", o.deal && "is-deal", o.stock === "out_of_stock" && "is-out", open && "is-open"].filter(Boolean).join(" ") });
    const head = el("button", { type: "button", class: "offer-head", "aria-expanded": String(open) },
      el("span", { class: "offer-top" },
        el("span", { class: "badge" }, dot(GROUP[groupOf(o)].color), versionLabel(o)),
        o.deal && el("span", { class: "badge deal" }, "Bonne affaire")),
      el("span", { class: "offer-price" }, eur(o.price_eur)),
      el("span", { class: "offer-name" }, o.name),
      el("span", { class: "offer-gap" }, gapText(o)),
      el("span", { class: "offer-sub", style: "grid-column: 1 / -1" },
        el("span", null, o.shop),
        el("span", null, dot(stock.color), stock.label)));
    const more = el("div", { class: "offer-more" }, el("div", null,
      el("dl", { class: "facts" },
        fact("Référence", o.ref || "non précisée", true),
        fact("Version", groupOf(o) === "tray" ? "Tray (sans boîte)" : "Box (en boîte)"),
        fact("Seuil", eur(limitFor(o))),
        fact("Prix", o.verified ? "Vérifié chez la boutique"
          : o.via ? `Relevé via ${o.via}, ${o.shipping === "unknown" ? "frais de port inconnus" : "livraison incluse"}` : "Non vérifié (comparateur)"),
        fact("Vendeur", o.marketplace ? "Marketplace (vendeur tiers)" : "Boutique"),
        fact("Stock", stock.label),
        fact("Garantie", groupOf(o) === "tray" ? "Celle du vendeur" : "AMD, 3 ans")),
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
    const groups = selectedGroups();
    $("chart-title").textContent = groups.length > 1 ? "Meilleur prix par version" : `Meilleur prix · ${GROUP[groups[0]].long}`;
    $("legend").replaceChildren(...(groups.length > 1 ? groups.map((g) => {
      const key = el("span", { class: "key" });
      key.style.background = GROUP[g].color;
      return el("li", null, key, GROUP[g].label);
    }) : []));

    const pts = periodPoints();
    const current = pts.length ? pts[pts.length - 1] : null;   // « Actuel » : le dernier relevé seulement
    $("stats-rows").replaceChildren(...groups.map((g) => {
      const values = pts.map((p) => p[g]).filter((v) => v != null);
      return el("tr", null,
        el("td", null, el("span", { class: "cat-cell" }, dot(GROUP[g].color), GROUP[g].label)),
        el("td", null, current ? eur(current[g]) : "—"),
        el("td", null, values.length ? eur(Math.min(...values)) : "—"),
        el("td", null, values.length ? eur(Math.max(...values)) : "—"));
    }));
    $("history-rows").replaceChildren(...[...pts].reverse().map((p) =>
      el("tr", null, el("td", null, shortFmt.format(p.t)), ...GROUPS.map((g) => el("td", null, eur(p[g]))))));

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

    const series = selectedGroups().map((g) => ({ key: g, name: GROUP[g].label, color: GROUP[g].color }));
    const points = periodPoints().filter((p) => series.some((s) => p[s.key] != null));
    $("chart-hint").textContent = !points.length
      ? "Aucun relevé sur cette période pour cette version."
      : points.length < 2
        ? "L'historique se remplit à chaque relevé (toutes les heures en journée)."
        : "Touche ou glisse sur le graphique pour lire les prix d'une date.";
    if (!points.length) return;

    const W = Math.max(280, box.clientWidth);
    const H = Math.round(Math.min(260, Math.max(190, W * 0.55)));
    const m = { top: 14, right: 48, bottom: 24, left: 38 };
    const iw = W - m.left - m.right;
    const ih = H - m.top - m.bottom;

    let refs = series.map((s) => ({ v: groupLimit(s.key), label: `seuil ${s.name}`, color: s.color }));
    // Versions au même seuil : une seule ligne.
    refs = refs.reduce((acc, r) => {
      const same = acc.find((a) => a.v === r.v);
      if (same) Object.assign(same, { label: "seuil", color: "var(--muted)" });
      else acc.push({ ...r });
      return acc;
    }, []);

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

    // Seuils trop proches les uns des autres : lignes seules, valeurs reportées sous le graphique.
    const sortedRefs = refs.sort((a, b) => b.v - a.v);
    const crowded = sortedRefs.some((r, i) => i > 0 && Math.abs(y(r.v) - y(sortedRefs[i - 1].v)) < 18);
    sortedRefs.forEach((r, i) => {
      const yy = y(r.v);
      root.append(svg("line", { x1: m.left, x2: m.left + iw, y1: yy, y2: yy, stroke: r.color, "stroke-width": 1, opacity: 0.55 }));
      if (crowded) return;
      const label = svg("text", { x: m.left + 4, y: i === 0 ? yy - 5 : yy + 13 });
      label.textContent = `${r.label} · ${r.v} €`;
      root.append(label);
    });
    if (crowded) {
      $("chart-hint").textContent += ` Seuils : ${sortedRefs.map((r) => `${r.label.replace("seuil ", "")} ${r.v} €`).join(" · ")}.`;
    }

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
    $("th-box").textContent = eur(groupLimit("box"));
    $("th-tray").textContent = eur(groupLimit("tray"));
    const slots = relevesSlots();
    const fmt = (m) => `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}`;
    $("set-schedule").textContent = `toutes les heures, ${fmt(slots[0])}–${fmt(slots[slots.length - 1])}`;
    $("ntfy-topic").textContent = ntfy().topic;
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
    setChecked($("cat-switch"), "data-cat", prefs.cat);
    setChecked($("period"), "data-period", prefs.period);
    setChecked($("set-theme"), "data-theme-value", prefs.theme);
    $("sort").value = prefs.sort;
    $("set-sort").value = prefs.sort;
    $("set-cat").value = prefs.cat;
    $("f-stock").setAttribute("aria-pressed", String(prefs.available));
    $("f-verified").setAttribute("aria-pressed", String(prefs.verifiedOnly));
    $("f-details").setAttribute("aria-pressed", String(prefs.details));
    $("set-stock").checked = prefs.available;
    $("set-verified").checked = prefs.verifiedOnly;
    $("set-details").checked = prefs.details;
  }

  async function copyTopic() {
    const topic = ntfy().topic;
    try {
      await navigator.clipboard.writeText(topic);
      showSync(`Nom du canal copié : ${topic}`, "done");
    } catch (e) {
      showSync(`Nom du canal : ${topic}`, "info");
    }
  }

  // Envoyée depuis ce téléphone : vérifie que l'abonnement ntfy fonctionne.
  async function testNotification() {
    const { server, topic } = ntfy();
    try {
      const res = await fetch(`${server.replace(/\/$/, "")}/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          title: "Veille 7800X3D : notifications activées",
          message: "Test réussi. Tu recevras ici le relevé de chaque heure, de 6h13 à 23h13, et une alerte dès que le 7800X3D passe sous le seuil.",
          tags: ["white_check_mark"],
          click: location.href.split("#")[0],
        }),
      });
      if (!res.ok) throw new Error(res.status === 429 ? "trop d'envois, réessaie plus tard" : `ntfy a répondu ${res.status}`);
      showSync("Notification de test envoyée : elle doit arriver dans quelques secondes.", "done");
    } catch (err) {
      showSync(`Test impossible : ${err instanceof TypeError ? "pas de connexion à ntfy" : err.message}.`, "error");
    }
  }

  // ---------- Événements ----------

  $("cat-switch").addEventListener("click", (e) => { const b = e.target.closest("[data-cat]"); if (b) setPref("cat", b.dataset.cat); });
  $("period").addEventListener("click", (e) => { const b = e.target.closest("[data-period]"); if (b) setPref("period", b.dataset.period); });
  $("set-theme").addEventListener("click", (e) => { const b = e.target.closest("[data-theme-value]"); if (b) setPref("theme", b.dataset.themeValue); });
  $("sort").addEventListener("change", (e) => setPref("sort", e.target.value));
  $("set-sort").addEventListener("change", (e) => setPref("sort", e.target.value));
  $("set-cat").addEventListener("change", (e) => setPref("cat", e.target.value));
  $("f-stock").addEventListener("click", () => setPref("available", !prefs.available));
  $("f-verified").addEventListener("click", () => setPref("verifiedOnly", !prefs.verifiedOnly));
  $("f-details").addEventListener("click", () => { openOffers.clear(); setPref("details", !prefs.details); });
  $("set-stock").addEventListener("change", (e) => setPref("available", e.target.checked));
  $("set-verified").addEventListener("change", (e) => setPref("verifiedOnly", e.target.checked));
  $("set-details").addEventListener("change", (e) => setPref("details", e.target.checked));
  $("ntfy-copy").addEventListener("click", copyTopic);
  $("ntfy-test").addEventListener("click", testNotification);
  $("refresh").addEventListener("click", refreshPrices);
  $("set-refresh").addEventListener("click", refreshPrices);
  window.addEventListener("hashchange", () => showView(true));
  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState !== "visible" || refreshing) return;
    if (Date.now() - state.loadedAt > 60000) await load();
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
    // Quand une nouvelle version de l'appli prend la main, on recharge une fois pour l'afficher.
    const hadController = !!navigator.serviceWorker.controller;
    let reloaded = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (hadController && !reloaded) { reloaded = true; location.reload(); }
    });
    navigator.serviceWorker.register("sw.js", { updateViaCache: "none" })
      .then((reg) => reg.update())
      .catch((err) => console.warn("Service worker :", err));
  }

  applyTheme();
  syncControls();
  showView(false);
  setupPullToRefresh();
  load();
})();
