"""LDLC et Materiel.net (même plateforme) : processeur suivi (7800X3D, 9800X3D…) neuf, versions box et tray.

Une page de recherche par boutique. Le prix est lu sur le site même de la boutique (verified=True) ;
ces pages n'affichent pas les frais de port, price_eur est donc le prix affiché.
"""

import re

from collect import price, stock_from, text

# (page, boutique, base des liens, découpe des cartes, titre (lien, nom), description, prix, disponibilité)
SHOPS = [
    ("https://www.ldlc.com/recherche/{key}/", "LDLC", "https://www.ldlc.com",
     r'<li[^>]*class="pdt-item[ "]', r'<h3 class\s*="title-3">\s*<a href="([^"]+)"[^>]*>(.*?)</a>',
     # prix : div « price » la plus interne ; en promo, « new-price » (et non « old-price », le prix barré)
     r'<p class="desc">(.*?)</p>', r'<div class="(?:new-)?price">((?:(?!<div).)*?)</div>',
     r'data-stock-web="\d".*?openModal">(.*?)</div>'),
    # « c-products-list__item has-odr » (offre de remboursement) : d'où le [ "] dans la découpe
    ("https://www.materiel.net/recherche/{key}/", "Materiel.net", "https://www.materiel.net",
     r'<li class="c-products-list__item[ "]',
     r'<a href="(https://www\.materiel\.net/produit/[^"]+)"[^>]*>\s*<h2 class="c-product__title">(.*?)</h2>',
     # en promo : « o-product__price o-product__cut-price » (prix barré, ignoré) puis « … o-product__price--promo »
     r'<p class="c-product__description">(.*?)</p>', r'<span class="o-product__price(?![^"]*cut-price)[^"]*">(.*?)</span>',
     r'o-availability__value[^"]*">(.*?)</span>'),
]


def cpu(product):
    """Nom commençant par le processeur : écarte les PC (« LDLC PC11… », « PC Gamer… ») et les autres CPU."""
    return re.compile(rf"^AMD Ryzen 7 {product['model']}\b", re.I)

BUNDLE = re.compile(r"\+|bundle|\bkit\b|\bpack\b|ventirad|watercooling|carte m[eè]re|delid|délid", re.I)
USED = re.compile(r"occasion|reconditionn|refurb|comme neuf|seconde main|utilisé", re.I)
TRAY = re.compile(r"\btray\b|\boem\b|\bmpk\b|sans bo[iî]te|plateau", re.I)


def stock(label):
    # « En stock fournisseur » (LDLC) / « Dispo fournisseur » (Materiel.net) : pas en entrepôt, expédié sous quelques jours
    return "on_order" if "fournisseur" in label.lower() else stock_from(label)


def parse(page, product, shop, base, item_re, title_re, desc_re, price_re, stock_re):
    offers, refs, cpu_re = [], product["refs"], cpu(product)
    for card in re.split(item_re, page)[1:]:
        title, cost = re.search(title_re, card, re.S), re.search(price_re, card, re.S)
        if not (title and cost):
            continue
        name, desc = text(title.group(2)), re.search(desc_re, card, re.S)
        blob = f"{name} {text(desc.group(1)) if desc else ''}"
        p = price(text(cost.group(1)))
        if not cpu_re.search(name) or BUNDLE.search(name) or USED.search(blob) or p is None:
            continue
        version = "tray" if TRAY.search(blob) else "box"   # sans mention : boîte (vente au détail)
        avail = re.search(stock_re, card, re.S)
        marketplace = 'data-is-marketplace="1"' in card
        url = title.group(1)
        offers.append({"name": product["name"], "ref": refs[version], "version": version, "price_eur": p,
                       "shop": f"{shop} Marketplace" if marketplace else shop,
                       "stock": stock(text(avail.group(1))) if avail else "unknown",
                       "marketplace": marketplace, "verified": True,
                       "url": url if url.startswith("http") else base + url})
    return offers


def collect(fetch, product):
    offers = []
    for i, (url, *rules) in enumerate(SHOPS):
        try:
            page = fetch(url.format(key=product["key"]))
        except Exception:
            if i == 0:
                raise   # première page en échec : l'appelant note la source comme bloquée
            continue
        # Page reçue (200) mais sans liste de produits ni « Aucun produit » : anti-bot ou maquette changée
        if i == 0 and not re.search(rules[2], page) and "Aucun produit" not in page:
            raise RuntimeError(f"{rules[0]} : page de recherche inattendue (anti-bot ?)")
        offers += parse(page, product, *rules)
    return offers
