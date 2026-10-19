"""Alternate France : AMD Ryzen 7 7800X3D neuf, versions box et tray.

La recherche liste les fiches (une « Tray », une « processeur en boîte ») ; chaque fiche 7800X3D est
ensuite ouverte pour y lire, sur le site même de la boutique, la référence AMD (mpn du JSON-LD), le prix,
le stock et les frais d'expédition affichés (« en sus à partir de € 9,90 »), ajoutés au prix.
Si une fiche ne répond pas, on garde le prix de la liste, plus le port lu sur l'autre fiche s'il y en a un.
Note : « à partir de € 9,90 » est un minimum ; la page d'aide Alternate annonce € 10,98 le colis standard
et renvoie au panier pour le montant exact, que ce module ne peut pas lire.
"""

import json
import re
import time

from collect import price, stock_from, text

SHIPPING_DEFAULT = 9.90   # « frais d'expédition en sus à partir de € 9,90 »
URLS = ["https://www.alternate.fr/listing.xhtml?q=7800x3d"]   # + les fiches produit trouvées dans la liste

REFS = {"box": "100-100000910WOF", "tray": "100-000000910"}

# Écarte les PC (« ALTERNATE PC Gaming… ») et les autres CPU ; « Ryzen™ » toléré (déjà vu sur le 9800X3D)
CPU = re.compile(r"^AMD Ryzen[™®]? 7 7800X3D\b", re.I)
EXCLUDE = re.compile(r"\+|bundle|\bkit\b|\bpack\b|\bPC\b|ventirad|watercooling|carte m[eè]re|d[ée]lid"
                     r"|occasion|reconditionn|refurb|comme neuf|seconde main", re.I)
TRAY = re.compile(r"\btray\b|\boem\b|\bmpk\b|sans bo[iî]te|plateau", re.I)


def stock(label):
    if re.search(r"plus (?:en stock|disponible)|n'est plus", label, re.I):   # stock_from y verrait « en stock »
        return "out_of_stock"
    # « En rupture de stock, prêt à être expédié dans 7-13 jours ouvrables » : commandable, donc sur commande
    return "on_order" if re.search(r"exp[ée]di[ée] dans", label, re.I) else stock_from(label)


def euros(raw):
    """« € 9,90 » → 9.9 (collect.price ignore les montants sous 50 €)."""
    m = re.search(r"(\d[\d.]*),(\d{2})", raw)
    return float(m.group(1).replace(".", "") + "." + m.group(2)) if m else None


def listing(page):
    """Cartes de la recherche : (lien, nom, sous-titre, prix, disponibilité) des seuls 7800X3D neufs."""
    cards = []
    for block in re.split(r'<a href="(?=https://www\.alternate\.fr/[^"]+/html/product/)', page)[1:]:
        url = block.split('"', 1)[0]
        name = re.search(r'<div class="product-name[^"]*">(.*?)</div>', block, re.S)
        sub = re.search(r'<span class="product-name-sub">(.*?)</span>', block, re.S)
        cost = re.search(r'<span class="price[^"]*">(.*?)</span>', block, re.S)
        avail = re.search(r'delivery-info[^>]*>\s*<span[^>]*>(.*?)</span>', block, re.S)
        if not (name and cost):
            continue
        name, sub = text(name.group(1)), text(sub.group(1)) if sub else ""
        p = price(text(cost.group(1)))
        if not CPU.search(name) or EXCLUDE.search(f"{name} {sub}") or p is None:
            continue
        cards.append((url, name, sub, p, text(avail.group(1)) if avail else ""))
    return cards


def product(page):
    """Fiche produit : offre du JSON-LD (prix, mpn, état, vendeur), stock et port affichés."""
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            data = json.loads(m.group(1), strict=False)   # le JSON contient des tabulations brutes
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "Product" and isinstance(item.get("offers"), dict):
                ship = re.search(r'id="shipping-price">(.*?)</div>', page, re.S)
                avail = re.search(r'class="availability-text"[^>]*>(.*?)</strong>', page, re.S)
                return {"mpn": item.get("mpn") or "", "price": float(item["offers"]["price"]),
                        "new": "NewCondition" in item["offers"].get("itemCondition", "NewCondition"),
                        "seller": item["offers"].get("seller", {}).get("name", ""),
                        # bloc présent sans montant (port offert) : 0 ; bloc absent : inconnu
                        "shipping": (euros(text(ship.group(1))) or 0.0) if ship else None,
                        "stock": text(avail.group(1)) if avail else ""}
    return None


def collect(fetch):
    page = fetch(URLS[0])   # première page : une erreur remonte (source bloquée)
    if "Résultats pour" not in page:   # page anti-robot ou d'erreur servie en 200 : bloquée, pas « vide »
        raise RuntimeError("Alternate : page de recherche méconnaissable (blocage ?)")
    cards = []
    for card in listing(page):
        try:
            time.sleep(0.4)
            info = product(fetch(card[0]))
        except Exception:
            info = None   # fiche en panne : on garde le prix de la liste
        cards.append((card, info))
    # Le port est le même pour toute la boutique : une fiche en panne reprend celui lu sur l'autre fiche,
    # et si aucune fiche ne l'indique, le minimum annoncé (9,90 €), pour ne pas afficher une fausse baisse.
    known = [i["shipping"] for _, i in cards if i and i["shipping"] is not None] or [SHIPPING_DEFAULT]
    offers = []
    for (url, name, sub, p, avail), info in cards:
        version = "tray" if TRAY.search(sub) or TRAY.search(name) else "box"   # sans mention : boîte
        ref, label, seller, ship = REFS[version], avail, "ALTERNATE", known[0]
        if info:
            if not info["new"]:
                continue
            if info["mpn"] in REFS.values():
                ref = info["mpn"]
                version = "box" if ref == REFS["box"] else "tray"
            p, ship = info["price"], ship if info["shipping"] is None else info["shipping"]
            label, seller = info["stock"] or avail, info["seller"] or seller
        p = round(p + ship, 2)
        marketplace = "alternate" not in seller.lower()   # Alternate vend lui-même (« ALTERNATE GmbH »)
        offers.append({"name": "AMD Ryzen 7 7800X3D", "ref": ref, "version": version, "price_eur": p,
                       "shop": "Alternate", "stock": stock(label) if label else "unknown",
                       "marketplace": marketplace, "verified": True, "url": url})
    return offers
