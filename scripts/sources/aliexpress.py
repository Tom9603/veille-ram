"""AliExpress France : offres AMD Ryzen 7 7800X3D neuves (box / tray).

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

URLS = [
    "https://fr.aliexpress.com/w/wholesale-ryzen-7-7800x3d.html?SearchText=ryzen+7+7800x3d",
    "https://fr.aliexpress.com/w/wholesale-amd-ryzen-7-7800x3d-tray.html?SearchText=amd+ryzen+7+7800x3d+tray",
    "https://fr.aliexpress.com/w/wholesale-7800x3d.html?SearchText=7800x3d",
]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
COOKIE = "aep_usuc_f=site=fra&c_tp=EUR&region=FR&b_locale=fr_FR"   # livraison en France, prix en euros
# En dehors : annonces leurres (2,93 €), variante moins chère (autre CPU) mise en avant, ou prix fantaisiste.
MIN_EUR, MAX_EUR = 200, 600

# Expédition depuis l'UE : prix TTC, sans frais d'importation. Hors UE (Chine…), au-delà
# de 150 € la TVA et les frais de douane sont réclamés à la livraison : prix affiché non TTC.
EU = {"FR", "DE", "ES", "IT", "PL", "BE", "NL", "CZ", "PT", "AT", "IE", "SK", "HU", "RO", "BG", "GR", "SE",
      "DK", "FI", "LT", "LV", "EE", "SI", "HR", "LU", "CY", "MT"}

USED = re.compile(r"occasion|reconditionn|refurb|\bused\b|second[- ]hand|seconde main|comme neuf|like new"
                  r"|usag[ée]|open ?box", re.I)
# Le titre doit commencer par le processeur lui-même (une carte mère commence par « Carte mère »,
# un ventirad par sa marque) ; certains vendeurs ajoutent « Carte mère » en fin de titre pour le référencement.
# Les annonces sponsorisées sont précédées du mot-clé acheté (« 7800X3D Processeur de jeu… »).
CPU_FIRST = re.compile(r"^\W*(?:(?:new|nouveau|neuf|original|d'origine|authentique)\s+)*"
                       r"(?:processeur|processor|cpu|amd\s+ryzen|ryzen|amd\s+r7|r7|(?:amd\s+)?7800X3D)\b", re.I)
BUNDLE = re.compile(r"\+|\bkit\b|bundle|combo|\blot\b|avec (?:la |une )?carte|with (?:a )?motherboard"
                    r"|pc (?:complet|gamer|portable)|ordinateur complet|mini ?pc", re.I)
OTHER_CPU = re.compile(r"\b(?!7800)[3-9]\d{3}(?:X3D|XT|X|F|G|GT|GE)\b"         # 9800X3D, 7700X, 7500F…
                       r"|\b(?:R[3579]|ryzen [3579])\s?(?!7800)[3-9]\d{3}\b", re.I)   # « R5 7600 »
TRAY = re.compile(r"\btray\b|\boem\b|\bmpk\b|sans bo[iî]te|plateau|bulk|en vrac|no box|without box|100-000000910", re.I)
BOX = re.compile(r"\bbox(?:ed)?\b|\bbo[iî]te\b|retail|100-100000910", re.I)


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


def offer(item):
    """Annonce AliExpress → offre, ou None si ce n'est pas un 7800X3D neuf seul, en euros, expédié de l'UE."""
    title = re.sub(r"\s+", " ", item.get("title", {}).get("displayTitle", "")).strip()
    norm = re.sub(r"7800\s?X\s?3\s?D", "7800X3D", title, flags=re.I)   # « 7800 X3D », « 7800X 3D »
    if ("7800X3D" not in norm or not CPU_FIRST.search(norm) or USED.search(norm) or BUNDLE.search(norm)
            or OTHER_CPU.search(norm)):
        return None
    sale = item.get("prices", {}).get("salePrice") or {}
    price = sale.get("minPrice")
    if sale.get("currencyCode") != "EUR" or not isinstance(price, (int, float)) or not MIN_EUR <= price <= MAX_EUR:
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
    ref = "100-000000910" if "100-000000910" in norm else "100-100000910WOF" if "100-100000910" in norm else ""
    pid = str(item.get("productId", ""))
    if not pid.startswith("1005"):
        pid = str(trace.get("utLogMap", {}).get("x_object_id", pid))
    return {"name": "AMD Ryzen 7 7800X3D", "ref": ref, "version": version, "price_eur": float(price), "shop": "AliExpress",
            "stock": stock, "marketplace": True, "verified": True, "url": f"https://fr.aliexpress.com/item/{pid}.html"}


def collect(fetch=None):
    """`fetch` (collect.fetch) est accepté pour l'interface mais pas utilisé : il faut le cookie de région."""
    cards = []
    for i, url in enumerate(URLS):
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
        o = offer(item)
        if o and (o["url"] not in found or o["price_eur"] < found[o["url"]]["price_eur"]):
            found[o["url"]] = o
    return sorted(found.values(), key=lambda o: o["price_eur"])
