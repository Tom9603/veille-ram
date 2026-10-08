#!/usr/bin/env python3
"""Relevé automatique des prix, sans IA, pour l'actualisation à la demande.

Lancé par GitHub Actions (bouton ↻ de l'appli et deux fois par jour). Sources :

- en direct (prix vérifiés chez la boutique) : LDLC, Materiel.net, Alternate, Grosbill ;
- Ledenicheur : liste des kits, puis fiche des moins chers pour avoir le prix de
  chaque boutique (Amazon, Cdiscount, Fnac, TopAchat…), livraison incluse.

Garde les kits DDR5 2x16 Go en 6000 MHz (CL30, CL32, CL36) et en 5600 MHz
(CL28 à CL36), et écrit un relevé au format attendu par scripts/record.py.

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
TARGETS = {6000: {30, 32, 36}, 5600: {28, 30, 32, 34, 36}}   # latences suivies par fréquence
PRODUCT_PAGES_PER_GROUP = 6   # fiches Ledenicheur ouvertes par catégorie (les kits les moins chers)
KEEP_PER_GROUP = 20           # offres gardées par catégorie dans le relevé

LEDENICHEUR_6000_PAGES = [
    "https://ledenicheur.fr/s/ddr5-32-go-6000-cl30/",
    "https://ledenicheur.fr/s/ddr5-32-go-6000/",
    "https://ledenicheur.fr/s/ddr5-6000-cl36/",
]
# Catégorie filtrée : 5600 MHz (1170=39864), 32 Go, 2 barrettes, CL28 à CL36.
LEDENICHEUR_5600_PAGE = "https://ledenicheur.fr/c/memoire-ram?1170=39864&r_95336=32-32&r_1181=2-2&r_1172=28-36"
LDLC_PAGES = [
    "https://www.ldlc.com/recherche/ddr5%206000/",
    "https://www.ldlc.com/recherche/ddr5%206000/page2/",
    "https://www.ldlc.com/recherche/ddr5%206000/page3/",
    "https://www.ldlc.com/recherche/ddr5%205600/",
    "https://www.ldlc.com/recherche/ddr5%205600/page2/",
]
MATERIEL_PAGES = [
    "https://www.materiel.net/recherche/ddr5%206000%202x16/",
    "https://www.materiel.net/recherche/ddr5%205600%202x16/",
]
ALTERNATE_PAGES = [
    "https://www.alternate.fr/listing.xhtml?q=ddr5+6000+2x16",
    "https://www.alternate.fr/listing.xhtml?q=ddr5+5600+2x16",
]
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


def detect_speed(blob):
    b = blob.replace(" ", " ")
    if re.search(r"6000|PC5-48000|6\.000|6,000", b):
        return 6000
    if re.search(r"5600|PC5-44800|5\.600|5,600", b):
        return 5600
    return None


def detect_cl(*parts):
    blob = " ".join(p for p in parts if p)
    m = re.search(r"\bCL\s?(\d{2})\b", blob, re.I)
    if not m:  # références fabricant : 6000C30, 560C30, 5600J36, 556C36, 56C46, 6000HC30…
        m = re.search(r"(?:6000|600|560|5600|556|60|56)H?[CJ](\d{2})", blob)
    return int(m.group(1)) if m else None


def kit_speed(blob):
    """Fréquence du kit s'il s'agit bien d'un kit DDR5 2x16 Go de bureau suivi, sinon None."""
    b = blob.lower().replace(" ", " ")
    two_by_16 = re.search(r"2\s?x\s?16|16\s?go, 2 pce|32 go \(2x", b)
    laptop = re.search(r"so-?dimm|so-dim|sodimm", b)
    if "ddr5" not in b or not two_by_16 or laptop or used(b):
        return None
    return detect_speed(blob)


def used(blob):
    """Occasion et reconditionné exclus : la veille ne suit que du neuf."""
    return bool(re.search(r"occasion|reconditionn|seconde main|refurb", blob, re.I))


def tracked(speed, cl):
    return speed in TARGETS and cl in TARGETS[speed]


def tidy(name):
    """Retire du nom affiché le bruit technique répété partout (DDR5, 6000 MHz, 2x16 Go…)."""
    name = re.sub(r"\([^)]*\)?", " ", name)
    name = re.sub(r"\b(DDR5|DIMM|288-pin|RAM|PC5-48000|PC5-44800|PC48000|PC44800|\d{4}\s?MHz|\d,\d{3}\s?MHz|2\s?x\s?16\s?G[oB]?|32\s?G[oB]|CL\s?\d{2}|AMD Expo|Memory)\b",
                  " ", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip(" -,")


def reference(*parts):
    blob = " ".join(p for p in parts if p)
    for pattern in (r"\b(F5-(?:6000|5600)[A-Z0-9-]+)", r"\b(KF5(?:60|56)[A-Z0-9-]+)", r"\b(CM[A-Z0-9]*(?:6000|5600)[CZ]\d{2}[A-Z0-9]*)",
                    r"\b(CP2K16G(?:60|56)C\d{2}[A-Z0-9]*)", r"\b(PV[A-Z0-9]*(?:600|560)C\d{2}K)",
                    r"\b([A-Z0-9]{2,}(?:6000|5600)H?C\d{2}[A-Z0-9-]*)", r"\b([A-Z0-9]{3,}(?:60|56)C\d{2}[A-Z0-9]*)"):
        m = re.search(pattern, blob)
        if m:
            return m.group(1)
    return ""


def stock_from(label):
    s = label.lower()
    if "pas en stock" in s or "rupture" in s or "épuisé" in s or "indisponible" in s or "out_of_stock" in s:
        return "out_of_stock"
    if "en stock" in s or "dernière" in s or "in_stock" in s:
        return "in_stock"
    if s.strip():
        return "on_order"
    return "unknown"


def offer(name, ref, speed, cl, p, shop, stock, url, verified, marketplace=False, via=None):
    o = {"name": name, "ref": ref, "speed": speed, "cl": cl, "price_eur": p, "shop": shop, "stock": stock,
         "marketplace": marketplace, "verified": verified, "url": url}
    if via:
        o["via"] = via
    return o


def group(o):
    return (o["speed"], o["cl"] if o["speed"] == 6000 else "all")


# ---------- Ledenicheur ----------

def ledenicheur_list(pages):
    """Pages de recherche 6000 MHz : liste des kits avec leur prix « dès » (boutique non précisée)."""
    products = {}
    for page in pages:
        for card in page.split('data-test="ProductCardProductName"')[1:]:
            m = re.search(r'href="(/product\.php\?p=\d+)".*?<p[^>]*>(.*?)</p>\s*</a>\s*<p[^>]*>(.*?)</p>', card, re.S)
            if not m:
                continue
            url, name, spec = "https://ledenicheur.fr" + m.group(1), text(m.group(2)), text(m.group(3))
            speed = kit_speed(f"{name} {spec}")
            cl = detect_cl(name)
            dès = re.search(r"Dès\s*</p>.*?>([^<]*\d[^<]*€)", card[:8000], re.S) or re.search(r">([\d\s ,]+)\s*€<", card[:8000])
            p = price(text(dès.group(1))) if dès else None
            if not tracked(speed, cl) or p is None:
                continue
            products[url] = offer(tidy(name), reference(name), speed, cl, p, "Ledenicheur (meilleur prix)", "unknown", url, False)
    return list(products.values())


def ledenicheur_category(page):
    """Page catégorie filtrée : les données de chaque kit sont dans le JSON de la page."""
    products = {}
    for m in re.finditer(r'"pathName":"(/product\.php\?p=\d+)","name":"((?:[^"\\]|\\.)*)","stockStatus":"([^"]*)"', page):
        window = page[m.end():m.end() + 6000]
        nxt = window.find('"pathName":"/product.php')
        window = window if nxt < 0 else window[:nxt]
        name = json.loads(f'"{m.group(2)}"') if "\\x" not in m.group(2) else m.group(2).encode().decode("unicode_escape")
        cost = re.search(r'"priceSummary":\{"regular":([\d.]+|null),"includeShipping":([\d.]+|null)', window)
        cas = re.search(r'"Latence CAS \(CL\)"[^}]*?"number":(\d+|null)', window)
        mods = re.search(r'"Nombre de modules"[^}]*?"number":(\d+|null)', window)
        if not cost or (mods and mods.group(1) not in ("2", "null")):
            continue
        p = price(cost.group(2) if cost.group(2) != "null" else cost.group(1))
        cl = detect_cl(name) or (int(cas.group(1)) if cas and cas.group(1) != "null" else None)
        speed = detect_speed(name) or 5600
        if re.search(r"so-?dimm|sodimm|ecc", name, re.I) or not tracked(speed, cl) or p is None:
            continue
        url = "https://ledenicheur.fr" + m.group(1)
        products[url] = offer(tidy(name), reference(name), speed, cl, p, "Ledenicheur (meilleur prix)",
                              stock_from(m.group(3)) if m.group(3) == "out_of_stock" else "unknown", url, False)
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
        cost = re.search(r"\|\s*(\d{1,3}(?:[\s  ]\d{3})*,\d{2})\s*€(?!\s*/)", body)
        if not (shop and link and cost):
            continue
        title = re.sub(r"[|\s]+", " ", body[:cost.start()])
        if 'data-test="UsedBadge"' in block or used(title):
            continue
        other_cl, other_speed = detect_cl(title), detect_speed(title)
        if ((other_cl and other_cl != product["cl"]) or (other_speed and other_speed != product["speed"])
                or re.search(r"so-?dimm", title, re.I)):
            continue  # Ledenicheur rattache parfois un autre kit à la fiche
        shop_name = html.unescape(shop.group(1)).strip()
        if shop_name.lower().replace(" marketplace", "") in skip_shops:
            continue
        p = price(cost.group(1))
        if p is None:
            continue
        stock = re.search(r"(En stock|Pas en stock|Stock inconnu|Rupture[^|]*|Expédié[^|]{0,40}|Sous \d+[^|]{0,30}|Sur commande)", body, re.I)
        offers.append(offer(product["name"], product["ref"], product["speed"], product["cl"], p, shop_name,
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
        speed = kit_speed(f"{name} {details}")
        cl = detect_cl(name, details)
        p = price(text(cost.group(1)))
        if not tracked(speed, cl) or p is None:
            continue
        avail = re.search(stock_re, block, re.S)
        offers.append(offer(tidy(re.sub(r"\s+-\s+2 x 16 Go.*$", "", name)), reference(details, name), speed, cl, p, shop,
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


def materiel(pages):
    offers = []
    for page in pages:
        offers += ldlc_like(page, "Materiel.net", "https://www.materiel.net", r'<li class="c-products-list__item"',
                            r'<a href="(https://www\.materiel\.net/produit/[^"]+)"[^>]*>\s*<h2 class="c-product__title">(.*?)</h2>',
                            r'<p class="c-product__description">(.*?)</p>', r'<span class="o-product__price">(.*?)</span>',
                            r'o-availability__value[^"]*">(.*?)</span>')
    return offers


def alternate(pages):
    offers = []
    for page in pages:
        for block in re.split(r'<a href="(?=https://www\.alternate\.fr/[^"]+/html/product/)', page)[1:]:
            url = block.split('"', 1)[0]
            name = re.search(r'<div class="product-name[^"]*">(.*?)</div>', block, re.S)
            sub = re.search(r'<span class="product-name-sub">(.*?)</span>', block, re.S)
            bullets = " ".join(text(b) for b in re.findall(r"<li>(.*?)</li>", block, re.S))
            cost = re.search(r'<span class="price[^"]*">(.*?)</span>', block, re.S)
            if not (name and cost):
                continue
            name, sub = text(name.group(1)), text(sub.group(1)) if sub else ""
            speed = kit_speed(f"{name} {sub} {bullets}")
            cl = detect_cl(bullets, sub, name)
            p = price(text(cost.group(1)))
            if not tracked(speed, cl) or p is None:
                continue
            avail = re.search(r'delivery-info[^>]*>\s*<span[^>]*>(.*?)</span>', block, re.S)
            colour = sub.split(",")[0].strip() if sub else ""
            brand = re.sub(r" 32 Go DDR5-\d{4}.*$", "", name)
            offers.append(offer(f"{brand}{' ' + colour if colour and len(colour) < 15 else ''}", reference(sub, name), speed, cl, p,
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
        speed = kit_speed(f"{title} {text(row[:4000])}")
        if speed not in TARGETS:
            continue
        cl = detect_cl(title)
        if cl is None:  # le nom ne donne pas toujours la latence : on la lit sur la fiche
            try:
                m = re.search(r'Latence CAS \(CL\)","value":"(\d{2})', get(url))
                cl = int(m.group(1)) if m else None
            except Exception:
                cl = None
        p = price(cost.group(1))
        if not tracked(speed, cl) or p is None:
            continue
        offers.append(offer(tidy(title), reference(title), speed, cl, p, "Grosbill",
                            stock_from(text(avail.group(1))) if avail else "unknown", url, True))
    return offers


# ---------- Assemblage ----------

def dedupe(offers):
    """Une seule offre par (boutique, kit, fréquence, CL) : la moins chère."""
    best = {}
    for o in offers:
        key = (o["shop"].lower(), (o["ref"] or o["name"]).lower(), o["speed"], o["cl"])
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


def keep_cheapest(offers, per_group=KEEP_PER_GROUP):
    groups = {}
    for o in sorted(offers, key=lambda o: o["price_eur"]):
        groups.setdefault(group(o), []).append(o)
    kept = [o for items in groups.values() for o in items[:per_group]]
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

    def pages(urls):
        """Première page obligatoire ; les suivantes sont facultatives (une seule tentative)."""
        got = []
        for i, url in enumerate(urls):
            try:
                got.append(fetch(url, attempts=2 if i == 0 else 1))
            except Exception:
                if i == 0:
                    raise
        return got

    read_directly = set()
    for label, run in (
        ("ldlc.com", lambda: ldlc(pages(LDLC_PAGES))),
        ("materiel.net", lambda: materiel(pages(MATERIEL_PAGES))),
        ("alternate.fr", lambda: alternate(pages(ALTERNATE_PAGES))),
        ("grosbill.com", lambda: grosbill(fetch(GROSBILL_PAGE))),
    ):
        found = source(label, run)
        if found:
            read_directly.add(DIRECT_SHOPS[label])
        offers += found

    listed = source("ledenicheur.fr", lambda: ledenicheur_list(pages(LEDENICHEUR_6000_PAGES))
                    + ledenicheur_category(fetch(LEDENICHEUR_5600_PAGE)))
    groups = {}
    for product in sorted(listed, key=lambda p: p["price_eur"]):
        groups.setdefault(group(product), []).append(product)
    for products in groups.values():
        for i, product in enumerate(products):
            shops = []
            if i < PRODUCT_PAGES_PER_GROUP:
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
    n5600 = sum(1 for o in offers if o["speed"] == 5600)
    run = {
        "offers": keep_cheapest(offers),
        "trend": f"Relevé automatique de {len(offers)} offres, dont {n5600} en 5600 MHz ("
                 + ", ".join(f"{shop} {n}" for shop, n in sorted(counts.items())) + ").",
        "blocked_sources": blocked,
    }
    with open(argv[0], "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    print(f"{len(offers)} offres relevées" + (f", sources inaccessibles : {', '.join(blocked)}" if blocked else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
