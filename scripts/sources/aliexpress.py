"""AliExpress France : offres neuves du processeur suivi (7800X3D, 9800X3D…), box / tray.

Les pages de recherche fr.aliexpress.com sont rendues côté serveur : la liste des
annonces est dans le JSON `window._dida_config_._init_data_` (mods.itemList.content),
avec titre, prix en euros, pays d'expédition et étiquettes (« Livraison gratuite »…).

Particularité : AliExpress choisit pays, langue et devise d'après l'IP. Depuis un
serveur (sandbox, runners GitHub Actions) la page sort en dollars, hors TVA, livrée
aux États-Unis, et aucun paramètre d'URL n'y change rien. Seul le cookie de région
`aep_usuc_f` (France, EUR) donne les vrais prix français : collect.fetch ne sachant
pas envoyer d'en-tête, ce module fait sa propre requête (mêmes en-têtes + cookie).

Les fiches produit (/item/…) sont rendues en JavaScript (isCSR) : rien à y lire.
"""

import gzip
import json
import re
import time
import urllib.parse
import urllib.request

SEARCHES = [
    "https://fr.aliexpress.com/w/wholesale-ryzen-7-{key}.html?SearchText=ryzen+7+{key}",
    "https://fr.aliexpress.com/w/wholesale-amd-ryzen-7-{key}-tray.html?SearchText=amd+ryzen+7+{key}+tray",
    "https://fr.aliexpress.com/w/wholesale-{key}.html?SearchText={key}",
]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
COOKIE = "aep_usuc_f=site=fra&c_tp=EUR&region=FR&b_locale=fr_FR"   # livraison en France, prix en euros
# Hors de la fourchette de prix du processeur (product["price_range"]) : annonces leurres (2,93 €),
# variante moins chère (autre CPU) mise en avant, ou prix fantaisiste.

# Expédition depuis l'UE : prix TTC, sans frais d'importation. Hors UE (Chine…), au-delà
# de 150 € la TVA et les frais de douane sont réclamés à la livraison : prix affiché non TTC.
EU = {"FR", "DE", "ES", "IT", "PL", "BE", "NL", "CZ", "PT", "AT", "IE", "SK", "HU", "RO", "BG", "GR", "SE",
      "DK", "FI", "LT", "LV", "EE", "SI", "HR", "LU", "CY", "MT"}

USED = re.compile(r"occasion|reconditionn|refurb|\bused\b|second[- ]hand|seconde main|comme neuf|like new"
                  r"|usag[ée]|open ?box", re.I)
# Le titre doit commencer par le processeur lui-même (une carte mère commence par « Carte mère »,
# un ventirad par sa marque) ; certains vendeurs ajoutent « Carte mère » en fin de titre pour le référencement.
# Les annonces sponsorisées sont précédées du mot-clé acheté (« 7800X3D Processeur de jeu… »).
def cpu_first(model):
    return re.compile(r"^\W*(?:(?:new|nouveau|neuf|original|d'origine|authentique)\s+)*"
                      rf"(?:processeur|processor|cpu|amd\s+ryzen|ryzen|amd\s+r7|r7|(?:amd\s+)?{model})\b", re.I)
BUNDLE = re.compile(r"\+|\bkit\b|bundle|combo|\blot\b|avec (?:la |une )?carte|with (?:a )?motherboard"
                    r"|pc (?:complet|gamer|portable)|ordinateur complet|mini ?pc", re.I)
def other_cpu(digits):
    return re.compile(rf"\b(?!{digits})[3-9]\d{{3}}(?:X3D|XT|X|F|G|GT|GE)\b"          # 9800X3D, 7700X, 7500F…
                      rf"|\b(?:R[3579]|ryzen [3579])\s?(?!{digits})[3-9]\d{{3}}\b", re.I)   # « R5 7600 »


TRAY = re.compile(r"\btray\b|\boem\b|\bmpk\b|sans bo[iî]te|plateau|bulk|en vrac|no box|without box|100-0000\d{5}\b", re.I)
BOX = re.compile(r"\bbox(?:ed)?\b|\bbo[iî]te\b|retail|100-1000\d{5}", re.I)


def get(url):
    """Comme collect.fetch (UA navigateur, gzip, 20 s), plus le cookie de région France/EUR."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Accept-Encoding": "gzip",
        "Cookie": COOKIE,
    })
    with urllib.request.urlopen(req, timeout=20) as res:
        body = res.read()
        if res.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return body.decode("utf-8", errors="replace")


def items(page):
    """Annonces de la page de recherche (JSON embarqué), [] si absent (captcha, page vide)."""
    dec = json.JSONDecoder()
    m = re.search(r"_init_data_\s*=\s*\{\s*data:\s*", page)
    if m:
        try:
            data, _ = dec.raw_decode(page, m.end())
            return data["data"]["root"]["fields"]["mods"]["itemList"]["content"]
        except (ValueError, KeyError, TypeError):
            pass
    m = re.search(r'"itemList":\s*', page)   # repli si l'enveloppe change
    try:
        return dec.raw_decode(page, m.end())[0].get("content", []) if m else []
    except ValueError:
        return []


def offer(item, product):
    """Annonce AliExpress → offre, ou None si ce n'est pas le processeur suivi, neuf, seul, en euros, expédié de l'UE."""
    model, digits, refs = product["model"], product["model"][:4], product["refs"]
    title = re.sub(r"\s+", " ", item.get("title", {}).get("displayTitle", "")).strip()
    norm = re.sub(rf"{digits}\s?X\s?3\s?D", model, title, flags=re.I)   # « 7800 X3D », « 7800X 3D »
    if (model not in norm or not cpu_first(model).search(norm) or USED.search(norm) or BUNDLE.search(norm)
            or other_cpu(digits).search(norm)):
        return None
    sale = item.get("prices", {}).get("salePrice") or {}
    price = sale.get("minPrice")
    low, high = product["price_range"]
    if sale.get("currencyCode") != "EUR" or not isinstance(price, (int, float)) or not low <= price <= high:
        return None
    trace = item.get("trace", {})
    try:
        cdi = json.loads(urllib.parse.unquote(trace.get("pdpParams", {}).get("pdp_cdi", "") or "{}"))
    except ValueError:
        cdi = {}
    if cdi.get("shipFrom") not in EU:   # pays d'expédition absent ou hors UE : prix non TTC
        return None
    tags = " ".join(t.get("tagContent", {}).get("tagText", "") for t in item.get("sellingPoints", []))
    delivery = trace.get("utLogMap", {}).get("delivery_info", "")
    # Pas de stock affiché en recherche : une date de livraison annoncée vaut « en stock ».
    stock = ("in_stock" if re.search(r"\d{4}-\d\d-\d\d", delivery) or re.search(r"à recevoir|plus que \d|livraison\s*:", tags, re.I)
             else "unknown")
    version = "tray" if TRAY.search(norm) else "box" if BOX.search(norm) else "tray"   # AliExpress : vrac par défaut
    ref = refs["tray"] if refs["tray"] in norm else refs["box"] if refs["box"][:13] in norm else ""
    pid = str(item.get("productId", ""))
    if not pid.startswith("1005"):
        pid = str(trace.get("utLogMap", {}).get("x_object_id", pid))
    return {"name": product["name"], "ref": ref, "version": version, "price_eur": float(price), "shop": "AliExpress",
            "stock": stock, "marketplace": True, "verified": True, "url": f"https://fr.aliexpress.com/item/{pid}.html"}


def collect(fetch, product):
    """`fetch` (collect.fetch) est accepté pour l'interface mais pas utilisé : il faut le cookie de région."""
    cards = []
    for i, url in enumerate(SEARCHES):
        url = url.format(key=product["key"])
        try:
            try:
                page = get(url)
            except Exception:
                if i:
                    raise
                time.sleep(3)
                page = get(url)   # première page : une seconde tentative, puis l'erreur remonte
            listed = items(page)
            if not any((it.get("prices", {}).get("salePrice") or {}).get("currencyCode") == "EUR" for it in listed):
                raise RuntimeError("AliExpress : pas d'annonces en euros (captcha, page vide ou cookie de région ignoré)")
            cards += listed
        except Exception:
            if i == 0:
                raise
        time.sleep(0.5)
    # Une même annonce revient sur plusieurs recherches : on lit d'abord les cartes « naturelles »,
    # dont le titre n'a pas le mot-clé publicitaire ajouté devant (qui pourrait fausser box / tray).
    found = {}
    for item in sorted(cards, key=lambda it: it.get("productType") == "ad"):
        o = offer(item, product)
        if o and (o["url"] not in found or o["price_eur"] < found[o["url"]]["price_eur"]):
            found[o["url"]] = o
    return sorted(found.values(), key=lambda o: o["price_eur"])
