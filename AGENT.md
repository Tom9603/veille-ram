# Consignes pour un agent de veille

Les relevés de l'heure sont faits sans IA par `scripts/collect.py`. Ce fichier
sert si un agent IA doit faire une recherche complète à la main. Pour changer
les seuils, modifie `config.json`.

## Mission

Trouver le meilleur prix actuel **en France** de l'**AMD Ryzen 7 7800X3D neuf**,
en version **Box** (en boîte, réf. 100-100000910WOF, garantie AMD 3 ans) et
**Tray** (sans boîte, OEM/MPK, réf. 100-000000910, garantie du vendeur).

- Ignore l'occasion, le reconditionné, les lots (processeur + carte mère…), les
  PC complets et les autres processeurs (9800X3D, 7900X3D, 7800X…).
- Les marketplaces (Amazon, Cdiscount, Fnac, AliExpress…) comptent : marque-les
  `marketplace: true`.
- Seuils d'alerte : `thresholds_eur.box` et `thresholds_eur.tray` dans
  `config.json`.

## Où chercher

1. Ledenicheur : fiches Box https://ledenicheur.fr/product.php?p=8053700&filters=price_inc_shipping et
   Tray https://ledenicheur.fr/product.php?p=8053713&filters=price_inc_shipping (offres les moins chères,
   livraison incluse).
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
