#!/usr/bin/env python3
"""Relevé automatique des prix, sans IA, pour l'actualisation à la demande.

Lancé par GitHub Actions (bouton ↻ de l'appli et deux fois par jour). Sources :

- en direct (prix vérifiés chez la boutique) : LDLC, Materiel.net, Alternate, Grosbill ;
- Ledenicheur : liste des kits, puis fiche des moins chers pour avoir le prix de
  chaque boutique (Amazon, Cdiscount, Fnac, TopAchat…), livraison incluse.

Garde les kits DDR5 2x16 Go 6000 MHz en CL30, CL32 ou CL36 et écrit un relevé au
format attendu par scripts/record.py.

Usage :
    python3 scripts/collect.py /chemin/vers/run.json
"""

import gzip
import html
import json
import re
import sys
import time
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
TARGET_CLS = {30, 32, 36}
PRODUCT_PAGES_PER_CL = 6     # fiches Ledenicheur ouvertes par latence (les kits les moins chers)
KEEP_PER_CL = 20             # offres gardées par latence dans le relevé

LEDENICHEUR_PAGES = [
    "https://ledenicheur.fr/s/ddr5-32-go-6000-cl30/",
    "https://ledenicheur.fr/s/ddr5-32-go-6000/",
    "https://ledenicheur.fr/s/ddr5-6000-cl36/",
]
LDLC_PAGES = [
    "https://www.ldlc.com/recherche/ddr5%206000/",
    "https://www.ldlc.com/recherche/ddr5%206000/page2/",
    "https://www.ldlc.com/recherche/ddr5%206000/page3/",
]
MATERIEL_PAGE = "https://www.materiel.net/recherche/ddr5%206000%202x16/"
ALTERNATE_PAGE = "https://www.alternate.fr/listing.xhtml?q=ddr5+6000+2x16"
GROSBILL_PAGE = "https://www.grosbill.com/memoire-pc-2/32go-ddr5"

# Boutiques lues en direct : si leur lecture a réussi, leurs offres vues via
# Ledenicheur sont ignorées (doublons) ; sinon Ledenicheur prend le relais.
DIRECT_SHOPS = {"ldlc.com": "ldlc", "materiel.net": "materiel.net", "alternate.fr": "alternate", "grosbill.com": "grosbill"}


# ---------- Outils ----------

def fetch(url, attempts=2):
    for attempt in range(attempts):
        try:
            return fetch_once(url)
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(3)


def fetch_once(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=20) as res:
        body = res.read()
        if res.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return body.decode("utf-8", errors="replace")


def text(fragment):
    fragment = re.sub(r"<(script|style|svg)[^>]*>.*?</\1>", " ", fragment, flags=re.S)
    fragment = re.sub(r"<sup>(\d+)</sup>", r",\1", fragment)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def price(raw):
    """« 1 234,56 € », « € 724,00 », « 609€,95 », « 664.99 » → nombre en euros."""
    raw = raw.replace("€ ", "€").replace("€,", ",")
    m = re.search(r"(\d[\d\s  ]*)(?:[.,](\d{1,2}))?", raw)
    if not m:
        return None
    euros = re.sub(r"[\s  ]", "", m.group(1))
    value = float(f"{euros}.{m.group(2) or '0'}")
    return value if 50 <= value <= 2000 else None


def detect_cl(*parts):
    blob = " ".join(p for p in parts if p)
    m = re.search(r"\bCL\s?(\d{2})\b", blob, re.I)
    if not m:  # références fabricant : 6000C30, 560C30, 60C36, 6000J3038, 6000HC30…
        m = re.search(r"(?:6000|600|560|60)H?[CJ](\d{2})", blob)
    return int(m.group(1)) if m else None


def is_kit(blob):
    b = blob.lower().replace(" ", " ")
    two_by_16 = re.search(r"2\s?x\s?16|16\s?go, 2 pce|32 go \(2x", b)
    laptop = re.search(r"so-?dimm|so-dim", b)
    return "ddr5" in b and "6000" in b and bool(two_by_16) and not laptop


def tidy(name):
    """Retire du nom affiché le bruit technique répété partout (DDR5, 6000 MHz, 2x16 Go…)."""
    name = re.sub(r"\([^)]*\)", " ", name)
    name = re.sub(r"\b(DDR5|DIMM|PC5-48000|PC48000|\d{4}\s?MHz|2\s?x\s?16\s?G[oB]?|32\s?G[oB]|CL\s?\d{2}|AMD Expo|Memory)\b",
                  " ", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip(" -,")


def reference(*parts):
    blob = " ".join(p for p in parts if p)
    for pattern in (r"\b(F5-6000[A-Z0-9-]+)", r"\b(KF560[A-Z0-9-]+)", r"\b(CM[A-Z0-9]*6000C\d{2}[A-Z0-9]*)",
                    r"\b(CP2K16G60C\d{2}[A-Z0-9]*)", r"\b(PV[A-Z0-9]*600C\d{2}K)", r"\b([A-Z0-9]{2,}6000H?C\d{2}[A-Z0-9-]*)",
                    r"\b([A-Z0-9]{3,}60C\d{2}[A-Z0-9]*)"):
        m = re.search(pattern, blob)
        if m:
            return m.group(1)
    return ""


def stock_from(label):
    s = label.lower()
    if "pas en stock" in s or "rupture" in s or "épuisé" in s or "indisponible" in s:
        return "out_of_stock"
    if "en stock" in s or "dernière" in s or "dernières" in s:
        return "in_stock"
    if s.strip():
        return "on_order"
    return "unknown"


def offer(name, ref, cl, p, shop, stock, url, verified, marketplace=False, via=None):
    o = {"name": name, "ref": ref, "cl": cl, "price_eur": p, "shop": shop, "stock": stock,
         "marketplace": marketplace, "verified": verified, "url": url}
    if via:
        o["via"] = via
    return o


# ---------- Ledenicheur ----------

def ledenicheur_list(pages):
    """Liste des kits avec leur prix « dès » (boutique non précisée)."""
    products = {}
    for page in pages:
        for card in page.split('data-test="ProductCardProductName"')[1:]:
            m = re.search(r'href="(/product\.php\?p=\d+)".*?<p[^>]*>(.*?)</p>\s*</a>\s*<p[^>]*>(.*?)</p>', card, re.S)
            if not m:
                continue
            url, name, spec = "https://ledenicheur.fr" + m.group(1), text(m.group(2)), text(m.group(3))
            if not is_kit(f"{name} {spec}"):
                continue
            cl = detect_cl(name)
            dès = re.search(r"Dès\s*</p>.*?>([^<]*\d[^<]*€)", card[:8000], re.S) or re.search(r">([\d\s ,]+)\s*€<", card[:8000])
            p = price(text(dès.group(1))) if dès else None
            if cl not in TARGET_CLS or p is None:
                continue
            products[url] = offer(tidy(name), reference(name), cl, p, "Ledenicheur (meilleur prix)", "unknown", url, False)
    return list(products.values())


def ledenicheur_shops(product, page, skip_shops=frozenset()):
    """Fiche produit : une offre par boutique (prix livraison incluse, stock, lien)."""
    offers = []
    for block in page.split('data-test="OfferListItem"')[1:]:
        block = block[:9000]
        shop = re.search(r'<img[^>]*alt="([^"]+)"', block)
        link = re.search(r'href="((?:https://ledenicheur\.fr)?/go-to-shop/[^"]+)"', block)
        # Balises remplacées par « | » pour ne pas coller « CL36 » au prix « 469,99 € ».
        body = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " | ", re.sub(r"<(svg|style|script)[^>]*>.*?</\1>", " ", block, flags=re.S))))
        cost = re.search(r"\|\s*(\d{1,3}(?:[\s\u00a0\u202f]\d{3})*,\d{2})\s*€(?!\s*/)", body)
        if not (shop and link and cost):
            continue
        title = re.sub(r"[|\s]+", " ", body[:cost.start()])
        other_cl = detect_cl(title)
        if (other_cl and other_cl != product["cl"]) or re.search(r"so-?dimm", title, re.I):
            continue  # Ledenicheur rattache parfois un autre kit à la fiche
        shop_name = html.unescape(shop.group(1)).strip()
        if shop_name.lower().replace(" marketplace", "") in skip_shops:
            continue
        p = price(cost.group(1))
        if p is None:
            continue
        stock = re.search(r"(En stock|Pas en stock|Stock inconnu|Rupture[^|]*|Expédié[^|]{0,40}|Sous \d+[^|]{0,30}|Sur commande)", body, re.I)
        offers.append(offer(product["name"], product["ref"], product["cl"], p, shop_name,
                            stock_from(stock.group(1)) if stock else "unknown",
                            html.unescape(link.group(1)) if link.group(1).startswith("http")
                            else "https://ledenicheur.fr" + html.unescape(link.group(1)), False,
                            marketplace="marketplace" in shop_name.lower(), via="Ledenicheur"))
    return offers


# ---------- Boutiques en direct ----------

def ldlc_like(page, shop, base, item_split, title_re, desc_re, price_re, stock_re):
    """LDLC et Materiel.net partagent la même plateforme (titres, descriptions, prix « 609€<sup>95</sup> »)."""
    offers = []
    for block in re.split(item_split, page)[1:]:
        title = re.search(title_re, block, re.S)
        desc = re.search(desc_re, block, re.S)
        cost = re.search(price_re, block, re.S)
        if not (title and cost):
            continue
        url, name = title.group(1), text(title.group(2))
        details = text(desc.group(1)) if desc else ""
        if not is_kit(f"{name} {details}"):
            continue
        cl = detect_cl(name, details)
        p = price(text(cost.group(1)))
        if cl not in TARGET_CLS or p is None:
            continue
        avail = re.search(stock_re, block, re.S)
        offers.append(offer(tidy(re.sub(r"\s+-\s+2 x 16 Go.*$", "", name)), reference(details, name), cl, p, shop,
                            stock_from(text(avail.group(1))) if avail else "unknown",
                            url if url.startswith("http") else base + url, True,
                            marketplace='data-is-marketplace="1"' in block))
    return offers


def ldlc(pages):
    offers = []
    for page in pages:
        offers += ldlc_like(page, "LDLC", "https://www.ldlc.com", r'<li[^>]*class="pdt-item"[^>]*>',
                            r'<h3 class\s*="title-3">\s*<a href="([^"]+)"[^>]*>(.*?)</a>', r'<p class="desc">(.*?)</p>',
                            r'<div class="price">(?:<div class="price">)?(.*?)</div>', r'class="modal-stock-web[^"]*stock[^"]*"[^>]*>(.*?)</div>')
    return offers


def materiel(page):
    return ldlc_like(page, "Materiel.net", "https://www.materiel.net", r'<li class="c-products-list__item"',
                     r'<a href="(https://www\.materiel\.net/produit/[^"]+)"[^>]*>\s*<h2 class="c-product__title">(.*?)</h2>',
                     r'<p class="c-product__description">(.*?)</p>', r'<span class="o-product__price">(.*?)</span>',
                     r'o-availability__value[^"]*">(.*?)</span>')


def alternate(page):
    offers = []
    for block in re.split(r'<a href="(?=https://www\.alternate\.fr/[^"]+/html/product/)', page)[1:]:
        url = block.split('"', 1)[0]
        name = re.search(r'<div class="product-name[^"]*">(.*?)</div>', block, re.S)
        sub = re.search(r'<span class="product-name-sub">(.*?)</span>', block, re.S)
        bullets = " ".join(text(b) for b in re.findall(r"<li>(.*?)</li>", block, re.S))
        cost = re.search(r'<span class="price[^"]*">(.*?)</span>', block, re.S)
        if not (name and cost):
            continue
        name, sub = text(name.group(1)), text(sub.group(1)) if sub else ""
        if not is_kit(f"{name} {sub} {bullets}"):
            continue
        cl = detect_cl(bullets, sub, name)
        p = price(text(cost.group(1)))
        if cl not in TARGET_CLS or p is None:
            continue
        avail = re.search(r'delivery-info[^>]*>\s*<span[^>]*>(.*?)</span>', block, re.S)
        colour = sub.split(",")[0].strip() if sub else ""
        brand = re.sub(r" 32 Go DDR5-6000.*$", "", name)
        offers.append(offer(f"{brand}{' ' + colour if colour and len(colour) < 15 else ''}", reference(sub, name), cl, p,
                            "Alternate", stock_from(text(avail.group(1))) if avail else "unknown", url, True))
    return offers


def grosbill(page, get=fetch):
    offers = []
    for row in page.split('class="product-row')[1:]:
        name = re.search(r'<a href="([^"]+)" class="p-name">(.*?)</a>', row, re.S)
        cost = re.search(r'data-price="([\d.]+)"', row)
        avail = re.search(r'class="dw-status[^"]*">(.*?)</span>', row, re.S)
        if not (name and cost):
            continue
        url, title = "https://www.grosbill.com" + name.group(1), text(name.group(2))
        if not is_kit(title):
            continue
        cl = detect_cl(title)
        if cl is None:  # le nom ne donne pas toujours la latence : on la lit sur la fiche
            try:
                m = re.search(r'Latence CAS \(CL\)","value":"(\d{2})', get(url))
                cl = int(m.group(1)) if m else None
            except Exception:
                cl = None
        p = price(cost.group(1))
        if cl not in TARGET_CLS or p is None:
            continue
        offers.append(offer(tidy(title), reference(title), cl, p, "Grosbill",
                            stock_from(text(avail.group(1))) if avail else "unknown", url, True))
    return offers


# ---------- Assemblage ----------

def dedupe(offers):
    """Une seule offre par (boutique, kit, CL) : la moins chère."""
    best = {}
    for o in offers:
        key = (o["shop"].lower(), (o["ref"] or o["name"]).lower(), o["cl"])
        if key not in best or o["price_eur"] < best[key]["price_eur"]:
            best[key] = o
    return list(best.values())


def better_names(offers):
    """Alternate n'affiche que la marque : on reprend le nom du même kit (même référence) vu ailleurs."""
    names = {o["ref"]: o["name"] for o in offers if o["ref"] and o["shop"] != "Alternate"}
    for o in offers:
        if o["shop"] == "Alternate" and o["ref"] in names:
            o["name"] = names[o["ref"]]
    return offers


def keep_cheapest(offers, per_cl=KEEP_PER_CL):
    kept = []
    for cl in sorted(TARGET_CLS):
        kept += sorted((o for o in offers if o["cl"] == cl), key=lambda o: o["price_eur"])[:per_cl]
    return sorted(kept, key=lambda o: o["price_eur"])


def collect():
    offers, blocked = [], []

    def source(label, run):
        try:
            found = run()
            if not found:
                print(f"{label} : aucune offre reconnue", file=sys.stderr)
            return found
        except Exception as err:  # une source en panne ne doit pas bloquer les autres
            print(f"{label} : {err}", file=sys.stderr)
            blocked.append(label)
            return []

    read_directly = set()
    for label, run in (
        ("ldlc.com", lambda: ldlc([fetch(LDLC_PAGES[0])] + [fetch(u, attempts=1) for u in LDLC_PAGES[1:]])),
        ("materiel.net", lambda: materiel(fetch(MATERIEL_PAGE))),
        ("alternate.fr", lambda: alternate(fetch(ALTERNATE_PAGE))),
        ("grosbill.com", lambda: grosbill(fetch(GROSBILL_PAGE))),
    ):
        found = source(label, run)
        if found:
            read_directly.add(DIRECT_SHOPS[label])
        offers += found

    listed = source("ledenicheur.fr", lambda: ledenicheur_list([fetch(u) for u in LEDENICHEUR_PAGES]))
    for cl in sorted(TARGET_CLS):
        cheapest = sorted((p for p in listed if p["cl"] == cl), key=lambda p: p["price_eur"])
        for i, product in enumerate(cheapest):
            shops = []
            if i < PRODUCT_PAGES_PER_CL:
                try:
                    time.sleep(0.4)
                    shops = ledenicheur_shops(product, fetch(product["url"]), frozenset(read_directly))
                except Exception as err:
                    print(f"Fiche Ledenicheur {product['url']} : {err}", file=sys.stderr)
            offers += shops or [product]
    return better_names(dedupe(offers)), blocked


def main(argv):
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    offers, blocked = collect()
    if not offers:
        print("ERREUR : aucune offre relevée, rien n'est écrit.", file=sys.stderr)
        sys.exit(3)
    counts = {}
    for o in offers:
        shop = o["shop"] if o.get("via") is None else "autres boutiques via Ledenicheur"
        shop = "Ledenicheur" if shop.startswith("Ledenicheur") else shop
        counts[shop] = counts.get(shop, 0) + 1
    run = {
        "offers": keep_cheapest(offers),
        "trend": f"Relevé automatique de {len(offers)} offres ("
                 + ", ".join(f"{shop} {n}" for shop, n in sorted(counts.items())) + ").",
        "blocked_sources": blocked,
    }
    with open(argv[0], "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    print(f"{len(offers)} offres relevées" + (f", sources inaccessibles : {', '.join(blocked)}" if blocked else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
