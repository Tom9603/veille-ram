"""Boutiques lues en direct : un module par boutique, chacun expose collect(fetch).

collect(fetch) renvoie la liste des offres au format de scripts/record.py (name, ref,
version, price_eur, shop, stock, marketplace, verified, url) et lève une exception si
la première page ne peut pas être lue (la boutique est alors notée « bloquée »).
"""
