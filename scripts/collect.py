#!/usr/bin/env python3
"""Relevé automatique du prix de l'AMD Ryzen 7 7800X3D neuf, sans IA.

Lancé par GitHub Actions (toutes les heures en journée, et bouton ↻ de l'appli).
Sources :

- en direct (prix vu chez la boutique) : les modules de scripts/sources/,
  un par boutique (voir SOURCES plus bas) ;
- Ledenicheur : fiches du 7800X3D Box et Tray, avec le prix de chaque boutique
  (Amazon, Cdiscount, Fnac, AliExpress…), livraison incluse.

Garde le processeur seul, neuf, en version Box (en boîte) ou Tray (sans boîte,
OEM), et écrit un relevé au format attendu par scripts/record.py.

Usage :
    python3 scripts/collect.py /chemin/vers/run.json
"""

import gzip
import html
import importlib
import json
import re
import sys
import time
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
NAME = "AMD Ryzen 7 7800X3D"
REFS = {"box": "100-100000910WOF", "tray": "100-000000910"}

# Fiches Ledenicheur : les offres affichées sont les moins chères, triées par prix.
LEDENICHEUR = {
    "box": "https://ledenicheur.fr/product.php?p=8053700",
    "tray": "https://ledenicheur.fr/product.php?p=8053713",
}

# Boutiques lues en direct : (libellé, module de scripts/sources/, noms des boutiques
# couvertes). Si la lecture réussit, leurs offres vues via Ledenicheur sont ignorées
# (doublons) ; sinon Ledenicheur prend le relais.
SOURCES = [
    ("ldlc.com / materiel.net", "ldlc_materiel", {"ldlc", "materiel.net"}),
    ("alternate.fr", "alternate", {"alternate"}),
    ("topachat.com", "topachat", {"topachat"}),
    ("grosbill.com", "grosbill", {"grosbill"}),
    ("aliexpress.com", "aliexpress", {"aliexpress"}),
]


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
    m = re.search(r"(\d[\d\s  ]*)(?:[.,](\d{1,2}))?", raw)
    if not m:
        return None
    euros = re.sub(r"[\s  ]", "", m.group(1))
    value = float(f"{euros}.{m.group(2) or '0'}")
    return value if 50 <= value <= 2000 else None


def stock_from(label):
    s = label.lower()
    if "pas en stock" in s or "rupture" in s or "épuisé" in s or "indisponible" in s or "out_of_stock" in s:
        return "out_of_stock"
    if "en stock" in s or "dernière" in s or "in_stock" in s:
        return "in_stock"
    if s.strip():
        return "on_order"
    return "unknown"


def used(blob):
    """Occasion et reconditionné exclus : la veille ne suit que du neuf."""
    return bool(re.search(r"occasion|reconditionn|seconde main|refurb|comme neuf|d'exposition", blob, re.I))


def other_product(title):
    """Autre processeur, lot ou PC complet : hors sujet."""
    t = title.lower()
    if "7800x3d" not in t.replace(" ", ""):
        return True
    return bool(re.search(r"9800x3d|7900x3d|7950x3d|\bpc (?:gamer|gaming|fixe|complet|de bureau)|gaming pc|ordinateur|"
                          r"unit[ée] centrale|\bkit\b|\bpack\b|bundle|\+ ?carte|carte m[èe]re|\bb650|\bx670|\bx870|"
                          r"\bb850|\brtx\b|\brx ?\d{4}|\bssd\b|\d+ ?go (?:de )?ram", t))


def version_of(title, default):
    """Box ou Tray d'après le titre de l'offre ; à défaut, la version de la fiche."""
    t = title.lower()
    if re.search(r"\btray\b|\boem\b|\bmpk\b|sans bo[iî]te|(?<!socket de )plateau|100-000000910\b", t):
        return "tray"
    if re.search(r"\bbox\b|\bwof\b|en bo[iî]te|bo[iî]te|100-100000910", t):
        return "box"
    return default


def offer(version, p, shop, stock, url, verified, marketplace=False, via=None, name=NAME, ref=None):
    o = {"name": name, "ref": REFS[version] if ref is None else ref, "version": version, "price_eur": p, "shop": shop,
         "stock": stock, "marketplace": marketplace, "verified": verified, "url": url}
    if via:
        o["via"] = via
    return o


# ---------- Ledenicheur ----------

def ledenicheur(page, version, skip_shops=frozenset()):
    """Fiche produit : une offre par boutique (prix livraison incluse, stock, lien)."""
    offers = []
    for block in page.split('data-test="OfferListItem"')[1:]:
        block = block[:9000]
        shop = re.search(r'<img[^>]*alt="([^"]+)"', block)
        link = re.search(r'href="((?:https://ledenicheur\.fr)?/go-to-shop/[^"]+)"', block)
        # Balises remplacées par « | » pour ne pas coller un nombre du titre au prix.
        body = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " | ", re.sub(r"<(svg|style|script)[^>]*>.*?</\1>", " ", block, flags=re.S))))
        cost = re.search(r"\|\s*(\d{1,3}(?:[\s  ]\d{3})*,\d{2})\s*€(?!\s*/)", body)
        if not (shop and link and cost):
            continue
        title = re.sub(r"[|\s]+", " ", body[:cost.start()]).strip()
        if 'data-test="UsedBadge"' in block or used(title) or other_product(title):
            continue
        shop_name = html.unescape(shop.group(1)).strip()
        if shop_name.lower().replace(" marketplace", "") in skip_shops:
            continue
        p = price(cost.group(1))
        if p is None:
            continue
        stock = re.search(r"(En stock|Pas en stock|Stock inconnu|Rupture[^|]*|Expédié[^|]{0,40}|Sous \d+[^|]{0,30}|Sur commande)", body, re.I)
        url = html.unescape(link.group(1))
        offers.append(offer(version_of(title, version), p, shop_name, stock_from(stock.group(1)) if stock else "unknown",
                            url if url.startswith("http") else "https://ledenicheur.fr" + url, False,
                            marketplace="marketplace" in shop_name.lower() or shop_name in ("AliExpress", "eBay"),
                            via="Ledenicheur"))
    return offers


# ---------- Assemblage ----------

def dedupe(offers):
    """Une seule fois chaque offre (boutique, version, lien) : la moins chère."""
    best = {}
    for o in offers:
        key = (o["shop"].lower(), o["version"], o["url"])
        if key not in best or o["price_eur"] < best[key]["price_eur"]:
            best[key] = o
    return sorted(best.values(), key=lambda o: o["price_eur"])


def collect():
    offers, blocked, read_directly = [], [], set()

    for label, module, shops in SOURCES:
        try:
            found = importlib.import_module(f"sources.{module}").collect(fetch)
        except Exception as err:  # une source en panne ne doit pas bloquer les autres
            print(f"{label} : {err}", file=sys.stderr)
            blocked.append(label)
            continue
        if not found:
            print(f"{label} : aucune offre reconnue", file=sys.stderr)
        read_directly.update(shops)
        offers += found

    for version, url in LEDENICHEUR.items():
        try:
            time.sleep(0.4)
            offers += ledenicheur(fetch(url), version, frozenset(read_directly))
        except Exception as err:
            print(f"Ledenicheur {version} : {err}", file=sys.stderr)
            if "ledenicheur.fr" not in blocked:
                blocked.append("ledenicheur.fr")
    return dedupe(offers), blocked


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
        counts[o["shop"]] = counts.get(o["shop"], 0) + 1
    n = {v: sum(1 for o in offers if o["version"] == v) for v in ("box", "tray")}
    run = {
        "offers": offers,
        "trend": f"{len(offers)} offres relevées ({n['box']} Box, {n['tray']} Tray) : "
                 + ", ".join(f"{shop} {k}" for shop, k in sorted(counts.items())) + ".",
        "blocked_sources": blocked,
    }
    with open(argv[0], "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    print(f"{len(offers)} offres relevées" + (f", sources inaccessibles : {', '.join(blocked)}" if blocked else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
