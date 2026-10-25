"""TopAchat : produit suivi (processeur en Box ou Tray, carte mère) neuf.

Le site (SvelteKit, groupe LDLC) rend tout côté serveur. La page de la rubrique (« Processeur », « Carte mère AM5 »)
filtrée sur le modèle (« 7800x3d », « b850m gaming plus »)
embarque, dans un objet JavaScript, chaque fiche : {ref:"in…",label:"…",offer:{availability:{…},price:{price_final:…}}}.
On ouvre ensuite chaque fiche du produit pour lire sur la page même de la boutique le JSON-LD (référence fabricant
en « mpn », prix, état neuf, vendeur) et l'étiquette de disponibilité (« EN STOCK », « DISPO FOURNISSEUR »…).
TopAchat n'affiche pas de frais de port sur ses fiches (calculés au panier) : le prix est donc hors port.
Si une fiche ne répond pas, on garde les données de la liste. Si la page catégorie arrive sans ses données
(anti-bot, refonte), on lève une erreur plutôt que de renvoyer une liste vide trompeuse.
"""

import json
import re
import time
from urllib.parse import quote

from collect import classify, excluded, price, stock_from

BASE = "https://www.topachat.com"
# rubrique (« wpr » : processeurs, « w_cm_am5 » : cartes mères AM5) et filtre de modèle : product["topachat"]
CATEGORY = BASE + "/pages/produits_cat_est_micro_puis_rubrique_est_{rubric}_puis_mc_est_{term}.html"   # + les fiches


# Le nom doit commencer par le produit (product["title_re"]) : écarte les autres modèles (9800X3D, 7800X…,
# B850M GAMING PLUS WIFI sans 6E), les PC, les ventirads, les outils de délidage.
# Disponibilité schema.org (secours si l'étiquette affichée manque) → mots compris par collect.stock_from
SCHEMA_STOCK = {"InStock": "en stock", "LimitedAvailability": "en stock", "OutOfStock": "rupture",
                "SoldOut": "rupture", "Discontinued": "rupture"}

# Fiche dans les données de la page : référence TopAchat, nom, sous-titre, disponibilité ; le reste suit.
CARD = re.compile(r'\{ref:"(in\d+)",label:"((?:[^"\\]|\\.)*)",sublabel:(?:"((?:[^"\\]|\\.)*)"|null),'
                  r'offer:\{availability:\{code:"[^"]*",label:"([^"]*)"\}')


def listing(page, product):
    """Cartes de la catégorie : (lien, nom, sous-titre, prix, disponibilité) du seul produit suivi, neuf."""
    cards, title_re, rubric = {}, product["title_re"], product["topachat"][0]
    for m in CARD.finditer(page):
        ref, name, sub, avail = m.groups()
        sub = sub or ""
        nxt = page.find('{ref:"in', m.end())   # s'arrêter à la fiche suivante : pas de prix ni de lien d'une autre
        window = page[m.end():nxt if nxt > 0 else m.end() + 2500]
        cost = re.search(r"price_final:([\d.]+)", window)
        link = re.search(r'url_product:"(/pages/[^"]+)"', window)
        p = price(cost.group(1)) if cost else None
        if not title_re.search(name) or excluded(product, f"{name} {sub}") or p is None or ref in cards:
            continue
        url = BASE + (link.group(1) if link else f"/pages/detail2_cat_est_micro_puis_rubrique_est_{rubric}_puis_ref_est_{ref}.html")
        cards[ref] = (url, name, sub, p, avail)
    return list(cards.values())


def details(page):
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


def collect(fetch, product):
    offers, (rubric, term) = [], product["topachat"]
    page = fetch(CATEGORY.format(rubric=rubric, term=quote(term)))   # première page : une erreur remonte (source bloquée)
    # Une vraie page de catégorie (même vide) porte le terme filtré ; sinon anti-bot ou refonte : on le signale.
    if not re.search(rf'search_term:"{re.escape(term)}"', page, re.I):
        raise RuntimeError("TopAchat : page catégorie sans données produit (anti-bot ou refonte du site)")
    for url, name, sub, p, avail in listing(page, product):
        version, ref = classify(product, name)   # processeur sans mention : boîte
        label, seller = avail, "TopAchat"
        try:
            time.sleep(0.4)
            info = details(fetch(url))
        except Exception:
            info = None   # fiche en panne : on garde les données de la liste
        if info:
            if not info["new"] or excluded(product, info["name"]):
                continue
            version, ref = classify(product, name, info["mpn"])
            p, label, seller = info["price"], info["stock"] or avail, info["seller"] or seller
        # « EN STOCK » → en stock ; « DISPO FOURNISSEUR » (expédié depuis le fournisseur) → sur commande
        offers.append({"name": product["name"], "ref": ref, "version": version, "price_eur": round(p, 2),
                       "shop": "TopAchat", "stock": stock_from(label),
                       "marketplace": "topachat" not in seller.lower(), "verified": True, "url": url})
    return offers
