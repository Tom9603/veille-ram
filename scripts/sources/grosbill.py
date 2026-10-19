"""Grosbill : AMD Ryzen 7 7800X3D neuf, versions box (« WOF ») et tray.

La recherche liste les fiches (cartes « product-row », prix dans data-price) ; chaque fiche 7800X3D est
ensuite ouverte pour y lire, sur le site même de la boutique, le JSON-LD : référence AMD (mpn), prix, état,
vendeur et frais de port (shippingRate, 6,99 €), ajoutés au prix sauf si le bandeau du site annonce la
livraison offerte à partir d'un montant atteint (« Livraison offerte à partir de 299€* d'achat du 16 au 19
octobre inclus ») et que l'opération n'est pas terminée. Si une fiche ne répond pas, on garde le prix de la
liste (sans le port). Une recherche sans aucune carte produit (anti-robot, refonte) lève une erreur.
"""

import html
import json
import re
import time
from datetime import date, datetime, timezone

from collect import price, stock_from, text

BASE = "https://www.grosbill.com"
URLS = [BASE + "/recherche?q=7800x3d"]   # + les fiches produit trouvées dans la liste

REFS = {"box": "100-100000910WOF", "tray": "100-000000910"}

CPU = re.compile(r"^AMD Ryzen 7 7800X3D\b", re.I)   # écarte les PC (« VENOM - R7-7800X3D/… », « Sapphire… ») et les autres CPU
EXCLUDE = re.compile(r"\+|bundle|\bkit\b|\bpack\b|\bPC\b|ventirad|watercooling|coreliquid|carte m[eè]re|d[ée]lid"
                     r"|occasion|reconditionn|refurb|comme neuf|seconde main", re.I)
TRAY = re.compile(r"\btray\b|\boem\b|\bmpk\b|sans bo[iî]te|plateau", re.I)
AVAILABILITY = {"InStock": "in_stock", "LimitedAvailability": "in_stock", "OutOfStock": "out_of_stock",
                "SoldOut": "out_of_stock", "Discontinued": "out_of_stock", "PreOrder": "on_order", "BackOrder": "on_order"}
MOIS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
        "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}


def listing(page):
    """Cartes de la recherche : (lien, nom, prix, disponibilité, vendu par Grosbill) des seuls 7800X3D neufs."""
    cards = []
    for row in page.split('class="product-row')[1:]:
        if "product-row--bundle" in row[:80]:
            continue   # « Kit Upgrade AM5 Ryzen 7 7800X3D + … » : lot
        name = re.search(r'<a href="([^"]+)" class="p-name">(.*?)</a>', row, re.S)
        cost = re.search(r'data-price="([\d.]+)"', row)
        avail = re.search(r'class="dw-status[^"]*">(.*?)</span>', row, re.S)
        if not (name and cost):
            continue
        title, p = text(name.group(2)), price(cost.group(1))
        if not CPU.search(title) or EXCLUDE.search(title) or p is None:
            continue
        url = html.unescape(name.group(1))
        cards.append((url if url.startswith("http") else BASE + url, title, p,
                      text(avail.group(1)) if avail else "", "product-row--gb" in row[:80]))
    return cards


def paris_today():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Paris")).date()
    except Exception:
        return datetime.now(timezone.utc).date()


def free_shipping_from(page, today=None):
    """Seuil de livraison offerte annoncé par le bandeau du site (opération ponctuelle), sinon None.
    Si le bandeau donne une date de fin (« du 16 au 19 octobre inclus ») déjà passée, il est ignoré."""
    m = re.search(r"Livraison (?:offerte|gratuite) (?:à partir de|dès) (\d[\d\s]*(?:[.,]\d{1,2})?)\s*€(.{0,80})",
                  text(page), re.I)
    if not m:
        return None
    end = re.search(r"\bau (\d{1,2})(?:er)? (" + "|".join(MOIS) + r")", m.group(2), re.I)
    if end:
        today = today or paris_today()
        last = date(today.year, MOIS[end.group(2).lower()], int(end.group(1)))
        if (last - today).days > 180:   # bandeau de décembre encore affiché en janvier
            last = last.replace(year=today.year - 1)
        if last < today:
            return None   # opération terminée : bandeau périmé
    return float(re.sub(r"\s", "", m.group(1)).replace(",", "."))


def product(page):
    """Fiche produit : offre du JSON-LD (prix, mpn, état, vendeur, port), stock affiché."""
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(m.group(1), strict=False)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if not (isinstance(item, dict) and item.get("@type") == "Product" and isinstance(item.get("offers"), dict)):
                continue
            o = item["offers"]
            rate = (o.get("shippingDetails") or {}).get("shippingRate") or {}
            avail = re.search(r'pdp-stock-detail__status">(.*?)</div>', page, re.S)
            return {"name": item.get("name", ""), "mpn": item.get("mpn") or "", "price": float(o["price"]),
                    "new": "NewCondition" in o.get("itemCondition", "NewCondition"),
                    "seller": (o.get("seller") or {}).get("name", ""),
                    "shipping": float(rate["value"]) if rate.get("value") not in (None, "") else None,
                    "stock": text(avail.group(1)) if avail else "",
                    "availability": AVAILABILITY.get(o.get("availability", "").rsplit("/", 1)[-1], "unknown")}
    return None


def collect(fetch):
    offers, first = [], fetch(URLS[0])   # première page : une erreur remonte (source bloquée)
    if 'class="product-row' not in first:   # page anti-robot ou nouvelle mise en page : pas une simple absence d'offre
        raise RuntimeError("Grosbill : recherche sans liste de produits (blocage ou mise en page changée)")
    for url, title, p, label, own in listing(first):
        version = "tray" if TRAY.search(title) else "box"   # « WOF » / « BOX » ou sans mention : boîte
        ref, stock, marketplace = REFS[version], stock_from(label) if label else "unknown", not own
        try:
            time.sleep(0.4)
            page = fetch(url)
            info = product(page)
        except Exception:
            info = None   # fiche en panne : on garde le prix de la liste
        if info:
            if not info["new"] or EXCLUDE.search(info["name"]):
                continue
            if info["mpn"] in REFS.values():
                ref = info["mpn"]
                version = "box" if ref == REFS["box"] else "tray"
            shipping = info["shipping"] or 0
            threshold = free_shipping_from(page)
            if threshold is not None and info["price"] >= threshold:
                shipping = 0   # livraison offerte pendant l'opération affichée en bandeau
            p = round(info["price"] + shipping, 2)
            stock = stock_from(info["stock"]) if info["stock"] else info["availability"]
            marketplace = bool(info["seller"]) and "grosbill" not in info["seller"].lower()
        offers.append({"name": "AMD Ryzen 7 7800X3D", "ref": ref, "version": version, "price_eur": p,
                       "shop": "Grosbill", "stock": stock, "marketplace": marketplace, "verified": True, "url": url})
    return offers
