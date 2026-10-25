#!/usr/bin/env python3
"""Relevé automatique du prix des pièces suivies (processeurs AMD Ryzen 7 7800X3D et 9800X3D,
carte mère MSI B850M GAMING PLUS WIFI6E), neuves, sans IA.

Lancé par GitHub Actions (toutes les heures en journée, et bouton ↻ de l'appli).
Sources :

- en direct (prix vu chez la boutique) : les modules de scripts/sources/,
  un par boutique (voir SOURCES plus bas) ;
- Ledenicheur : fiche(s) de chaque produit, avec le prix de chaque boutique
  (Amazon, Cdiscount, Fnac, AliExpress…), livraison incluse quand elle est connue.

Garde le produit seul et neuf (pas de lot, de PC complet, d'autre modèle ni d'occasion) ; pour un
processeur, en version Box (en boîte) ou Tray (sans boîte, OEM). Écrit un relevé au format attendu
par scripts/record.py (champ « product » : clé du produit dans PRODUCTS).

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
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
LN = "https://ledenicheur.fr/product.php?p={}&filters=price_inc_shipping"


def cpu(model, refs, ledenicheur, price_range):
    """Processeur AMD Ryzen 7 suivi, en versions Box et Tray."""
    key = model.lower()
    return {"key": key, "kind": "cpu", "model": model, "name": f"AMD Ryzen 7 {model}", "refs": refs,
            "search": key,                                          # terme cherché dans les boutiques
            "title_re": re.compile(rf"^AMD Ryzen[™®]? 7 {model}\b", re.I),   # titre en boutique : le CPU d'abord
            "topachat": ("wpr", key),                               # TopAchat : (rubrique, filtre de modèle)
            "ledenicheur": {v: LN.format(p) for v, p in ledenicheur.items()},
            "price_range": price_range}


# Produits suivis. Fiches Ledenicheur, prix livraison incluse : les offres affichées sont les moins
# chères, celles dont les frais de port sont connus d'abord, puis les autres.
# refs : version → référence du fabricant ; un produit sans variante n'a qu'une version (« std »).
# price_range : fourchette plausible d'un prix neuf (écarte leurres et prix fantaisistes).
PRODUCTS = {
    "7800x3d": cpu("7800X3D", {"box": "100-100000910WOF", "tray": "100-000000910"},
                   {"box": 8053700, "tray": 8053713}, (200, 600)),
    "9800x3d": cpu("9800X3D", {"box": "100-100001084WOF", "tray": "100-000001084"},
                   {"box": 13951156, "tray": 13963569}, (280, 800)),
    "b850m": {"key": "b850m", "kind": "motherboard", "model": "B850M", "name": "MSI B850M GAMING PLUS WIFI6E",
              "refs": {"std": "7E81-001R"},
              "search": "b850m gaming plus wifi6e",
              # Pas la B850M GAMING PLUS WIFI (sans 6E), ni la B850 (ATX), ni les PZ / MAX
              "title_re": re.compile(r"^MSI\s+B850M\s+GAMING\s+PLUS\s+WI-?FI\s?6E\b", re.I),
              "match": re.compile(r"\bB850M[\s-]*GAMING[\s-]*PLUS[\s-]*WI-?FI[\s-]*6E\b", re.I),
              "topachat": ("w_cm_am5", "b850m gaming plus"),
              "ledenicheur": {"std": LN.format(15126881)},
              "price_range": (100, 400)},
}
OTHER_X3D = ("7800x3d", "9800x3d", "7900x3d", "7950x3d", "9900x3d", "9950x3d", "5800x3d", "5700x3d")

# Boutiques lues en direct : (libellé, module de scripts/sources/, noms des boutiques couvertes,
# types de produits). Si la lecture réussit, leurs offres vues via Ledenicheur sont ignorées
# (doublons) ; sinon Ledenicheur prend le relais.
SOURCES = [
    ("ldlc.com / materiel.net", "ldlc_materiel", {"ldlc", "materiel.net"}, {"cpu", "motherboard"}),
    ("alternate.fr", "alternate", {"alternate"}, {"cpu", "motherboard"}),
    ("topachat.com", "topachat", {"topachat"}, {"cpu", "motherboard"}),
    ("grosbill.com", "grosbill", {"grosbill"}, {"cpu", "motherboard"}),
    # AliExpress : aucune offre de cette carte mère expédiée depuis l'Europe
    ("aliexpress.com", "aliexpress", {"aliexpress"}, {"cpu"}),
]

# Titre d'une offre en boutique à écarter (lot, accessoire, autre modèle), par type de produit.
EXCLUDE = {
    "cpu": re.compile(r"\+|bundle|\bkit\b|\bpack\b|\bduo\b|\btrio\b|\bPC\b|\bRTX\b|\bRX ?\d|\bSSD\b|\d+ ?Go\b"
                      r"|\bW1[01]\b|ventirad(?!\s*non\b)|watercooling|coreliquid|carte m[eè]re|d[ée]lid", re.I),
    "motherboard": re.compile(r"\+|bundle|\bkit\b|\bpack\b|\bduo\b|\btrio\b|\bPZ\b|\bMAX\b|ryzen \d \d{4}", re.I),
}
TRAY = re.compile(r"\btray\b|\boem\b|\bmpk\b|\bbulk\b|sans bo[iî]te|plateau", re.I)


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
    # Adresse avec accents (Alternate : « …/carte-mère-socket-AM5/… ») : encodée, sinon la requête échoue.
    url = urllib.parse.quote(url, safe=":/?&=%#+,;@!$'()*~[]")
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
    if "inconnu" in s or "stock ?" in s:
        return "unknown"
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


def excluded(product, blob):
    """Titre d'offre en boutique hors sujet : lot, accessoire, autre modèle, occasion."""
    return bool(EXCLUDE[product["kind"]].search(blob)) or used(blob)


def classify(product, blob, mpn=""):
    """(version, référence) d'une offre : d'après la référence du fabricant lue chez la boutique si
    c'est l'une des nôtres, sinon d'après le titre (Tray s'il le dit, sinon Box, vente au détail)."""
    refs = product["refs"]
    if len(refs) == 1:   # produit sans variante
        return next(iter(refs.items()))
    for version, ref in refs.items():
        if mpn and mpn == ref:
            return version, ref
    version = "tray" if TRAY.search(blob) else "box"
    return version, refs[version]


def other_product(title, product):
    """Titre Ledenicheur d'un autre produit, d'un lot ou d'un PC complet : hors sujet."""
    t = title.lower()
    if product["kind"] != "cpu":
        return not product["match"].search(title) or bool(re.search(
            r"\+|bundle|\bkit\b|\bpack\b|\bpz\b|\bmax\b|ryzen \d \d{4}|\bpc (?:gamer|gaming|fixe|complet|de bureau)"
            r"|gaming pc|ordinateur|unit[ée] centrale", t))
    if product["key"] not in t.replace(" ", ""):
        return True
    if any(x in t for x in OTHER_X3D if x != product["key"]):
        return True
    return bool(re.search(r"\bpc (?:gamer|gaming|fixe|complet|de bureau)|gaming pc|"
                          r"(?<!processeur d')(?<!processeur pour )ordinateur|"
                          r"unit[ée] centrale|\bkit\b|\bpack\b|bundle|\+ ?carte|carte m[èe]re|\bb650|\bx670|\bx870|"
                          r"\bb850|\brtx\b|\brx ?\d{4}|\bssd\b|\d+ ?go (?:de )?ram", t))


def version_of(title, default, product):
    """Box ou Tray d'après le titre de l'offre ; à défaut, la version de la fiche."""
    t, refs = title.lower(), product["refs"]
    if len(refs) == 1:
        return default
    if (re.search(r"\btray\b|\boem\b|\bmpk\b|\bbulk\b|en vrac|sans bo[iî]te|sans emballage|(?<!socket de )plateau", t)
            or refs["tray"] in t):
        return "tray"
    if re.search(r"\bbox\b|\bwof\b|en bo[iî]te|bo[iî]te", t) or refs["box"][:13].lower() in t:
        return "box"
    return default


def offer(product, version, p, shop, stock, url, verified, marketplace=False, via=None, shipping=None):
    o = {"product": product["key"], "name": product["name"], "ref": product["refs"][version], "version": version,
         "price_eur": p, "shop": shop, "stock": stock, "marketplace": marketplace, "verified": verified, "url": url}
    if via:
        o["via"] = via
    if shipping:
        o["shipping"] = shipping   # included : livraison comprise dans le prix ; unknown : frais de port inconnus
    return o


# ---------- Ledenicheur ----------

def ledenicheur(page, product, version, skip_shops=frozenset()):
    """Fiche produit : une offre par boutique (prix livraison incluse, stock, lien)."""
    if 'data-test="OfferListItem"' not in page:   # page anti-robot ou nouvelle mise en page
        raise RuntimeError("aucune offre dans la page")
    offers = []
    for block in page.split('data-test="OfferListItem"')[1:]:
        # le découpage tombe au milieu de la balise d'ouverture : on retire la fin de ses attributs
        block = re.sub(r'^[^<]*?">', "", block[:9000], count=1)
        shop = re.search(r'<img[^>]*alt="([^"]+)"', block)
        link = re.search(r'href="((?:https://ledenicheur\.fr)?/go-to-shop/[^"]+)"', block)
        # Balises remplacées par « | » pour ne pas coller un nombre du titre au prix.
        body = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " | ", re.sub(r"<(svg|style|script)[^>]*>.*?</\1>", " ", block, flags=re.S))))
        cost = re.search(r"\|\s*(\d{1,3}(?:[\s  ]\d{3})*,\d{2})\s*€(?!\s*/)", body)
        if not (shop and link and cost):
            continue
        title = re.sub(r"[|\s]+", " ", body[:cost.start()]).strip()
        if 'data-test="UsedBadge"' in block or used(title) or other_product(title, product):
            continue
        shop_name = html.unescape(shop.group(1)).strip()
        if shop_name.lower().replace(" marketplace", "") in skip_shops:
            continue
        p = price(cost.group(1))
        if p is None:
            continue
        stock = re.search(r"(En stock|Pas en stock|Stock inconnu|Rupture[^|]*|Expédié[^|]{0,40}|Sous \d+[^|]{0,30}|Sur commande)", body, re.I)
        shipping = re.search(r"Livraison gratuite|Livraison \d|Frais de livraison inconnus", body, re.I)
        url = html.unescape(link.group(1))
        offers.append(offer(product, version_of(title, version, product), p, shop_name,
                            stock_from(stock.group(1)) if stock else "unknown",
                            url if url.startswith("http") else "https://ledenicheur.fr" + url, False,
                            marketplace="marketplace" in shop_name.lower() or shop_name in ("AliExpress", "eBay"),
                            via="Ledenicheur",
                            shipping="included" if shipping and "inconnu" not in shipping.group(0).lower() else "unknown"))
    return offers


# ---------- Assemblage ----------

def dedupe(offers):
    """Une seule fois chaque offre (produit, boutique, version, lien) : la moins chère."""
    best = {}
    for o in offers:
        key = (o["product"], o["shop"].lower(), o["version"], o["url"])
        if key not in best or o["price_eur"] < best[key]["price_eur"]:
            best[key] = o
    return sorted(best.values(), key=lambda o: o["price_eur"])


def collect_product(product, blocked):
    """Offres d'un produit : boutiques en direct, puis Ledenicheur pour les autres."""
    offers, read_directly = [], set()
    for label, module, shops, kinds in SOURCES:
        if product["kind"] not in kinds:
            continue
        try:
            found = importlib.import_module(f"sources.{module}").collect(fetch, product)
        except Exception as err:  # une source en panne ne doit pas bloquer les autres
            print(f"{label} ({product['model']}) : {err}", file=sys.stderr)
            if label not in blocked:
                blocked.append(label)
            continue
        if not found:
            print(f"{label} ({product['model']}) : aucune offre reconnue", file=sys.stderr)
        # Seules les boutiques effectivement lues remplacent leurs offres vues via Ledenicheur.
        read_directly.update(shop for shop in shops if any(o["shop"].lower() == shop for o in found))
        offers += [{**o, "product": product["key"]} for o in found]

    for version, url in product["ledenicheur"].items():
        try:
            time.sleep(0.4)
            offers += ledenicheur(fetch(url), product, version, frozenset(read_directly))
        except Exception as err:
            print(f"Ledenicheur {product['model']} {version} : {err}", file=sys.stderr)
            if "ledenicheur.fr" not in blocked:
                blocked.append("ledenicheur.fr")
    return offers


def collect():
    offers, blocked = [], []
    for product in PRODUCTS.values():
        offers += collect_product(product, blocked)
    return dedupe(offers), blocked


def valid(o):
    """Offre acceptée par scripts/record.py ? Une offre bancale est écartée, pas tout le relevé."""
    return (o.get("product") in PRODUCTS and o.get("version") in PRODUCTS[o["product"]]["refs"] and isinstance(o.get("price_eur"), (int, float)) and 50 <= o["price_eur"] <= 2000
            and all(isinstance(o.get(k), str) and o[k].strip() for k in ("name", "shop", "url"))
            and o["url"].startswith("https://") and isinstance(o.get("ref", ""), str)
            and o.get("stock") in ("in_stock", "on_order", "out_of_stock", "unknown")
            and isinstance(o.get("marketplace"), bool) and isinstance(o.get("verified"), bool))


def main(argv):
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    offers, blocked = collect()
    for o in [o for o in offers if not valid(o)]:
        print(f"Offre écartée (format invalide) : {o}", file=sys.stderr)
    offers = [o for o in offers if valid(o)]
    if not offers:
        print("ERREUR : aucune offre relevée, rien n'est écrit.", file=sys.stderr)
        sys.exit(3)
    parts = []
    for key, product in PRODUCTS.items():
        mine = [o for o in offers if o["product"] == key]
        if len(product["refs"]) > 1:
            n = {v: sum(1 for o in mine if o["version"] == v) for v in ("box", "tray")}
            parts.append(f"{product['model']} : {len(mine)} offres ({n['box']} Box, {n['tray']} Tray)")
        else:
            parts.append(f"{product['model']} : {len(mine)} offres")
    shops = sorted({o["shop"] for o in offers})
    run = {
        "offers": offers,
        "trend": " · ".join(parts) + f". Boutiques : {', '.join(shops)}.",
        "blocked_sources": blocked,
    }
    with open(argv[0], "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    print(f"{len(offers)} offres relevées" + (f", sources inaccessibles : {', '.join(blocked)}" if blocked else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
