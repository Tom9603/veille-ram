"""Boutiques lues en direct : un module par boutique, chacun expose collect(fetch, product).

collect(fetch, product) renvoie les offres du produit suivi (une entrée de PRODUCTS dans
scripts/collect.py) au format de scripts/record.py (name, ref, version, price_eur, shop,
stock, marketplace, verified, url) et lève une exception si la première page ne peut pas
être lue (la boutique est alors notée « bloquée »).
"""
