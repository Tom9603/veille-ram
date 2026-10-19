# Consignes pour un agent de veille

Les relevés de l'heure sont faits sans IA par `scripts/collect.py`. Ce fichier
sert si un agent IA doit faire une recherche complète à la main. Pour changer
les seuils, modifie `config.json`.

## Mission

Trouver le meilleur prix actuel **en France** des **AMD Ryzen 7 7800X3D** et
**9800X3D** neufs, en version **Box** (en boîte, garantie AMD 3 ans ; réf.
100-100000910WOF et 100-100001084WOF) et **Tray** (sans boîte, OEM/MPK, garantie
du vendeur ; réf. 100-000000910 et 100-000001084). Champ `product` de chaque
offre : `7800x3d` ou `9800x3d`.

- Ignore l'occasion, le reconditionné, les lots (processeur + carte mère…), les
  PC complets et les autres processeurs (7900X3D, 7800X…).
- Les marketplaces (Amazon, Cdiscount, Fnac, AliExpress…) comptent : marque-les
  `marketplace: true`.
- Seuils d'alerte : `thresholds_eur` dans `config.json`, par processeur et version.

## Où chercher

1. Ledenicheur : fiches Box et Tray de chaque processeur (liens dans
   `PRODUCTS` de `scripts/collect.py`, avec `&filters=price_inc_shipping` :
   offres les moins chères, livraison incluse).
2. Boutiques et marketplaces : LDLC, Materiel.net, Alternate, Grosbill,
   TopAchat, Amazon.fr, Cdiscount, Fnac, AliExpress.
3. Bons plans récents (moins de 48 h) sur dealabs.com.

## Règles de fiabilité

- `verified: true` seulement si le prix a été vu sur la page de la boutique ;
  un prix lu sur un comparateur porte `via: "Ledenicheur"`.
- Stock : `in_stock`, `on_order`, `out_of_stock` ou `unknown`.
- N'invente jamais un prix : chaque offre vient d'une page consultée.

## Enregistrer un relevé

Écris le relevé hors du dépôt au format décrit en tête de `scripts/record.py`
(champs `version`, `price_eur`, `shop`…), puis lance
`python3 scripts/record.py /tmp/run.json --dry-run` pour le valider.
