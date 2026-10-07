# Consignes de l'agent de veille

Ce fichier est lu par l'agent IA à chaque passage (2 fois par jour). Pour changer
son comportement, modifie ce fichier. Pour changer les seuils ou l'horaire
affiché, modifie `config.json`.

## Mission

Trouver le meilleur prix actuel **en France** pour le kit décrit dans
`config.json` (`product`), enregistrer le relevé dans ce dépôt pour que l'appli
se mette à jour, puis rendre un résumé court en français.

- RAM DDR5 desktop (DIMM), kit **2 x 16 Go** (32 Go), **6000 MHz** (6000 MT/s).
- Latence : **CL30** en priorité. Plan B : **CL32** ou **CL36**. Ignore CL38 et
  plus, les kits 1x32 et 2x32, et les autres fréquences.
- Neuf uniquement (pas d'occasion ni de reconditionné), livré en France.

Les seuils d'alerte sont dans `config.json` (`thresholds_eur`) : relis-les à
chaque passage, ils peuvent changer.

## Où chercher

1. Comparateurs : https://ledenicheur.fr/s/ddr5-32-go-6000-cl30/ et des
   recherches proches sur ledenicheur.fr (WebFetch fonctionne sur les URL
   `/s/...`). idealo.fr et amazon.fr bloquent souvent WebFetch : passe alors
   par WebSearch.
2. Boutiques : Grosbill (https://www.grosbill.com/memoire-pc-2/32go-ddr5
   fonctionne), LDLC, Materiel.net, TopAchat, Alternate.fr, Cdiscount,
   Rue du Commerce, Amazon.fr.
3. Bons plans : deals récents (moins de 48 h) sur dealabs.com pour
   « DDR5 6000 CL30 32 Go », « DDR5 6000 CL32 32Go » et « DDR5 6000 CL36 32Go ».

Utilise WebSearch (mode standard, puis extended si les résultats sont pauvres)
et WebFetch. Si une source est bloquée, passe à la suivante sans insister et
note-la dans `blocked_sources`.

## Règles de fiabilité

- Vérifie la référence exacte (ex. `KF560C30BBEK2-32`, `CMK32GX5M2B6000C30`)
  pour être sûr que c'est bien du 2x16 Go 6000 avec la bonne CL.
- Stock : `in_stock` (en stock), `on_order` (sur commande), `out_of_stock`
  (rupture) ou `unknown` (non affiché, ex. prix vu sur un comparateur).
- `marketplace: true` pour un vendeur tiers (Amazon, Cdiscount, Rue du
  Commerce…). N'inclus pas les vendeurs sans avis ou douteux.
- `verified: true` seulement si tu as vu le prix sur la page de la boutique.
  Un prix lu sur un comparateur ou dans un extrait de recherche est
  `verified: false`.
- N'invente jamais un prix : chaque offre doit venir d'une source consultée
  pendant ce passage. Mieux vaut une liste courte et juste.
- Vise 5 à 12 offres, les moins chères, en couvrant CL30 et CL32/36.

Le script décide seul de ce qui est une « bonne affaire » (en stock ou sur
commande, prix vérifié, sous le seuil). Ne retouche pas ce calcul.

## Étapes

1. Lis `config.json` et `data/latest.json` (le passage précédent, pour repérer
   les évolutions).
2. Fais les recherches ci-dessus.
3. Écris ton relevé dans un fichier **hors du dépôt**, par exemple
   `/tmp/run.json`, au format décrit en tête de `scripts/record.py` :

   ```json
   {
     "offers": [
       {"name": "Kingston Fury Beast", "ref": "KF560C30BBEK2-32", "cl": 30,
        "price_eur": 529.99, "shop": "LDLC", "stock": "in_stock",
        "marketplace": false, "verified": true, "url": "https://..."}
     ],
     "trend": "Une phrase factuelle sur la tendance (comparée au passage précédent ou aux historiques vus).",
     "blocked_sources": ["idealo.fr"]
   }
   ```

   Laisse `checked_at` vide : le script met l'heure de Paris.
4. Lance `python3 scripts/record.py /tmp/run.json`. S'il affiche des erreurs,
   corrige le relevé et relance. Il met à jour `data/latest.json` et
   `data/history.json`, et affiche le texte de la notification.
5. Publie le relevé (voir le prompt de la routine pour l'accès au dépôt) :
   `git add data/latest.json data/history.json`, puis
   `git commit -m "Relevé du <date> <heure>"` et `git push origin gh-pages`.
   Si le push est refusé parce que la branche a avancé : `git pull --rebase origin gh-pages`
   puis relance le push.
6. Ton message final est **exactement** la sortie de `record.py` (titre,
   tableau, tendance, lien vers l'appli). Rien d'autre : c'est le texte de la
   notification.

## Interdits

- Ne modifie aucun autre fichier que `data/latest.json` et `data/history.json`.
- Pas de branche, pas de pull request, pas d'issue.
- Ne touche à aucun autre dépôt.
