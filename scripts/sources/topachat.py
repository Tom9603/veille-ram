"""TopAchat : AMD Ryzen 7 7800X3D neuf, versions box et tray.

Le site (SvelteKit, groupe LDLC) rend tout côté serveur. La page « Processeur » filtrée sur « 7800x3d »
embarque, dans un objet JavaScript, chaque fiche : {ref:"in…",label:"…",offer:{availability:{…},price:{price_final:…}}}.
On ouvre ensuite chaque fiche 7800X3D pour lire sur la page même de la boutique le JSON-LD (référence AMD
en « mpn », prix, état neuf, vendeur) et l'étiquette de disponibilité (« EN STOCK », « DISPO FOURNISSEUR »…).
TopAchat n'affiche pas de frais de port sur ses fiches (calculés au panier) : le prix est donc hors port.
Si une fiche ne répond pas, on garde les données de la liste. Si la page catégorie arrive sans ses données
(anti-bot, refonte), on lève une erreur plutôt que de renvoyer une liste vide trompeuse.
"""

import json
import re
import time

from collect import price, stock_from

BASE = "https://www.topachat.com"
URLS = [BASE + "/pages/produits_cat_est_micro_puis_rubrique_est_wpr_puis_mc_est_7800x3d.html"]   # + les fiches trouvées

REFS = {"box": "100-100000910WOF", "tray": "100-000000910"}

# Nom commençant par le CPU : écarte les autres CPU (9800X3D, 7800X…), les PC, les ventirads, les outils de délidage.
CPU = re.compile(r"^AMD Ryzen 7 7800X3D\b", re.I)
EXCLUDE = re.compile(r"\+|bundle|\bkit\b|\bpack\b|\bduo\b|\btrio\b|\bPC\b|\bRTX\b|\bRX \d|\bSSD\b|\d+ ?Go\b|\bW1[01]\b"
                     r"|watercooling|carte m[eè]re|d[ée]lid|occasion|reconditionn|refurb|comme neuf|seconde main", re.I)
TRAY = re.compile(r"\btray\b|\boem\b|\bmpk\b|\bbulk\b|sans bo[iî]te|plateau", re.I)
# Disponibilité schema.org (secours si l'étiquette affichée manque) → mots compris par collect.stock_from
SCHEMA_STOCK = {"InStock": "en stock", "LimitedAvailability": "en stock", "OutOfStock": "rupture",
                "SoldOut": "rupture", "Discontinued": "rupture"}

# Fiche dans les données de la page : référence TopAchat, nom, sous-titre, disponibilité ; le reste suit.
CARD = re.compile(r'\{ref:"(in\d+)",label:"((?:[^"\\]|\\.)*)",sublabel:(?:"((?:[^"\\]|\\.)*)"|null),'
                  r'offer:\{availability:\{code:"[^"]*",label:"([^"]*)"\}')


def listing(page):
    """Cartes de la catégorie : (lien, nom, sous-titre, prix, disponibilité) des seuls 7800X3D neufs."""
    cards = {}
    for m in CARD.finditer(page):
        ref, name, sub, avail = m.groups()
        sub = sub or ""
        nxt = page.find('{ref:"in', m.end())   # s'arrêter à la fiche suivante : pas de prix ni de lien d'une autre
        window = page[m.end():nxt if nxt > 0 else m.end() + 2500]
        cost = re.search(r"price_final:([\d.]+)", window)
        link = re.search(r'url_product:"(/pages/[^"]+)"', window)
        p = price(cost.group(1)) if cost else None
        if not CPU.search(name) or EXCLUDE.search(f"{name} {sub}") or p is None or ref in cards:
            continue
        url = BASE + (link.group(1) if link else f"/pages/detail2_cat_est_micro_puis_rubrique_est_wpr_puis_ref_est_{ref}.html")
        cards[ref] = (url, name, sub, p, avail)
    return list(cards.values())


def product(page):
    """Fiche produit : offre du JSON-LD (prix, mpn, état, vendeur) et étiquette de disponibilité affichée."""
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            data = json.loads(m.group(1), strict=False)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "Product" and isinstance(item.get("offers"), dict):
                offer = item["offers"]
                i = page.find(f'product:{{ref:"{item.get("sku", "")}"')
                avail = re.search(r'availability:\{code:"[^"]*",label:"([^"]*)"', page[i:i + 3000]) if i >= 0 else None
                return {"name": item.get("name", ""), "mpn": item.get("mpn") or "", "price": float(offer["price"]),
                        "new": "NewCondition" in offer.get("itemCondition", "NewCondition"),
                        "seller": offer.get("seller", {}).get("name", ""),
                        "stock": avail.group(1) if avail else SCHEMA_STOCK.get(
                            offer.get("availability", "").rsplit("/", 1)[-1], "")}
    return None


def collect(fetch):
    offers = []
    page = fetch(URLS[0])   # première page : une erreur remonte (source bloquée)
    # Une vraie page de catégorie (même vide) porte le terme filtré ; sinon anti-bot ou refonte : on le signale.
    if not re.search(r'search_term:"7800x3d"', page, re.I):
        raise RuntimeError("TopAchat : page catégorie sans données produit (anti-bot ou refonte du site)")
    for url, name, sub, p, avail in listing(page):
        version = "tray" if TRAY.search(name) else "box"   # sans mention : boîte
        ref, label, seller = REFS[version], avail, "TopAchat"
        try:
            time.sleep(0.4)
            info = product(fetch(url))
        except Exception:
            info = None   # fiche en panne : on garde les données de la liste
        if info:
            if not info["new"] or EXCLUDE.search(info["name"]):
                continue
            if info["mpn"] in REFS.values():
                ref = info["mpn"]
                version = "box" if ref == REFS["box"] else "tray"
            p, label, seller = info["price"], info["stock"] or avail, info["seller"] or seller
        # « EN STOCK » → en stock ; « DISPO FOURNISSEUR » (expédié depuis le fournisseur) → sur commande
        offers.append({"name": "AMD Ryzen 7 7800X3D", "ref": ref, "version": version, "price_eur": round(p, 2),
                       "shop": "TopAchat", "stock": stock_from(label),
                       "marketplace": "topachat" not in seller.lower(), "verified": True, "url": url})
    return offers
