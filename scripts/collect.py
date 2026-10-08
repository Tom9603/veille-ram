#!/usr/bin/env python3
"""Relevé automatique des prix, sans IA, pour l'actualisation à la demande.

Lancé par GitHub Actions (bouton ↻ de l'appli) : lit Ledenicheur, Materiel.net
et Alternate, garde les kits DDR5 2x16 Go 6000 MHz en CL30, CL32 ou CL36, puis
écrit un relevé au format attendu par scripts/record.py.

Usage :
    python3 scripts/collect.py /chemin/vers/run.json
    python3 scripts/collect.py --from-files page1.html ... (tests hors ligne)
"""

import gzip
import html
import json
import re
import sys
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
TARGET_CLS = {30, 32, 36}

LEDENICHEUR_PAGES = [
    "https://ledenicheur.fr/s/ddr5-32-go-6000-cl30/",
    "https://ledenicheur.fr/s/ddr5-32-go-6000/",
    "https://ledenicheur.fr/s/ddr5-6000-cl36/",
]
MATERIEL_PAGE = "https://www.materiel.net/recherche/ddr5%206000%202x16/"
ALTERNATE_PAGE = "https://www.alternate.fr/listing.xhtml?q=ddr5+6000+2x16"


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=30) as res:
        body = res.read()
        if res.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return body.decode("utf-8", errors="replace")


def text(fragment):
    fragment = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", fragment, flags=re.S)
    fragment = re.sub(r"<sup>(\d+)</sup>", r",\1", fragment)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def price(raw):
    """« 1 234,56 € », « € 724,00 », « 609€,95 » → 1234.56 / 724.0 / 609.95."""
    m = re.search(r"(\d[\d\s  .]*)(?:€\s*)?(?:,(\d{1,2}))?", raw.replace("€ ", "€"))
    if not m:
        return None
    euros = re.sub(r"[\s  .]", "", m.group(1))
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
    name = re.sub(r"\b(DDR5|DIMM|PC5-48000|\d{4}\s?MHz|2\s?x\s?16\s?G[oB]?|32\s?G[oB]|CL\s?\d{2}|AMD Expo|Memory)\b",
                  " ", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip(" -,")


def reference(*parts):
    blob = " ".join(p for p in parts if p)
    for pattern in (r"\b(F5-6000[A-Z0-9-]+)", r"\b(KF560[A-Z0-9-]+)", r"\b(CM[A-Z0-9]*6000C\d{2}[A-Z0-9]*)",
                    r"\b(CP2K16G60C\d{2}[A-Z0-9]*)", r"\b(PV[A-Z0-9]*600C\d{2}K)", r"\b([A-Z0-9]{2,}6000H?C\d{2}[A-Z0-9-]*)"):
        m = re.search(pattern, blob)
        if m:
            return m.group(1)
    return ""


def ledenicheur(pages):
    offers = {}
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
            offers[url] = {
                "name": tidy(name), "ref": reference(name), "cl": cl, "price_eur": p,
                "shop": "Ledenicheur (meilleur prix)", "stock": "unknown",
                "marketplace": False, "verified": False, "url": url,
            }
    return list(offers.values())


def materiel(page):
    offers = []
    for block in page.split('<li class="c-products-list__item"')[1:]:
        title = re.search(r'<h2 class="c-product__title">(.*?)</h2>', block, re.S)
        link = re.search(r'href="(https://www\.materiel\.net/produit/[^"]+)"', block)
        desc = re.search(r'<p class="c-product__description">(.*?)</p>', block, re.S)
        cost = re.search(r'<span class="o-product__price">(.*?)</span>', block, re.S)
        if not (title and link and cost):
            continue
        name, details = text(title.group(1)), text(desc.group(1)) if desc else ""
        if not is_kit(f"{name} {details}"):
            continue
        cl = detect_cl(name, details)
        p = price(text(cost.group(1)))
        if cl not in TARGET_CLS or p is None:
            continue
        avail = re.search(r'o-availability__value[^"]*">(.*?)</span>', block, re.S)
        avail = text(avail.group(1)).lower() if avail else ""
        stock = ("in_stock" if "en stock" in avail else
                 "out_of_stock" if "rupture" in avail or "épuisé" in avail else
                 "on_order" if avail else "unknown")
        offers.append({
            "name": tidy(re.sub(r"\s+-\s+2 x 16 Go.*$", "", name)), "ref": reference(details, name), "cl": cl,
            "price_eur": p, "shop": "Materiel.net", "stock": stock,
            "marketplace": 'data-is-marketplace="1"' in block, "verified": True, "url": link.group(1),
        })
    return offers


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
        avail = text(avail.group(1)).lower() if avail else ""
        stock = ("in_stock" if "en stock" in avail else
                 "out_of_stock" if "pas en stock" in avail or "épuisé" in avail else
                 "on_order" if avail else "unknown")
        colour = sub.split(",")[0].strip() if sub else ""
        offers.append({
            "name": f"{re.sub(r' 32 Go DDR5-6000.*$', '', name)}{' ' + colour if colour and len(colour) < 15 else ''}",
            "ref": reference(sub, name), "cl": cl, "price_eur": p, "shop": "Alternate", "stock": stock,
            "marketplace": False, "verified": True, "url": url,
        })
    return offers


def better_names(offers):
    """Alternate n'affiche que la marque : on reprend le nom du même kit (même référence) vu ailleurs."""
    names = {o["ref"]: o["name"] for o in offers if o["ref"] and o["shop"] != "Alternate"}
    for o in offers:
        if o["shop"] == "Alternate" and o["ref"] in names:
            o["name"] = names[o["ref"]]
    return offers


def keep_cheapest(offers, per_cl=15):
    """Les 15 offres les moins chères de chaque latence, pour que CL32 et CL36 restent visibles."""
    kept = []
    for cl in sorted(TARGET_CLS):
        kept += sorted((o for o in offers if o["cl"] == cl), key=lambda o: o["price_eur"])[:per_cl]
    return sorted(kept, key=lambda o: o["price_eur"])


def collect():
    offers, blocked = [], []
    try:
        offers += ledenicheur([fetch(u) for u in LEDENICHEUR_PAGES])
    except Exception as err:  # une source en panne ne doit pas bloquer les autres
        print(f"Ledenicheur : {err}", file=sys.stderr)
        blocked.append("ledenicheur.fr")
    for name, url, parser in (("materiel.net", MATERIEL_PAGE, materiel), ("alternate.fr", ALTERNATE_PAGE, alternate)):
        try:
            found = parser(fetch(url))
            offers += found
            if not found:
                print(f"{name} : aucune offre reconnue", file=sys.stderr)
        except Exception as err:
            print(f"{name} : {err}", file=sys.stderr)
            blocked.append(name)
    return better_names(offers), blocked


def main(argv):
    if argv[:1] == ["--from-files"]:
        pages = {p: open(p, encoding="utf-8", errors="replace").read() for p in argv[1:]}
        offers = []
        for path, page in pages.items():
            parser = materiel if "materiel" in path else alternate if "alternate" in path else lambda pg: ledenicheur([pg])
            offers += parser(page)
        print(json.dumps(keep_cheapest(better_names(offers)), ensure_ascii=False, indent=1))
        return
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    offers, blocked = collect()
    if not offers:
        print("ERREUR : aucune offre relevée, rien n'est écrit.", file=sys.stderr)
        sys.exit(3)
    counts = {}
    for o in offers:
        shop = o["shop"].split(" (")[0]
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
