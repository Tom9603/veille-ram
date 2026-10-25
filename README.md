# Veille PC

Suivi automatique du prix de pièces neuves, avec une appli mobile et des
notifications seulement quand il y a du nouveau :

- processeurs **AMD Ryzen 7 7800X3D** et **9800X3D**, en version **Box** (en
  boîte, garantie AMD 3 ans) et **Tray** (sans boîte, OEM, garantie du vendeur) ;
- carte mère **MSI B850M GAMING PLUS WIFI6E** (pas la version WIFI sans 6E, ni
  la B850 au format ATX).

**Appli :** https://tom9603.github.io/veille-ram/

(Le dépôt s'appelle encore `veille-ram` : il suivait avant le prix d'un kit de
RAM DDR5. Les données de cette époque restent figées dans `data/latest.json` et
`data/history.json`, pour les téléphones qui auraient encore l'ancienne appli
ouverte : elles leur demandent de la fermer et de la rouvrir.)

## Comment ça marche

```
GitHub Actions « Actualiser les prix » (un relevé par heure de 6h à 23h, et à la demande)
  │  GitHub lance les tâches programmées avec des heures de retard : le robot
  │  tourne donc en continu, fait lui-même un relevé à hh:13 (rien la nuit) et
  │  se passe le relais avant la limite de 6 h par job ; la programmation ne
  │  sert que de secours si la chaîne s'arrête
  │  scripts/collect.py : pour chaque produit (PRODUCTS), boutiques lues en
  │                       direct (scripts/sources/ : LDLC, Materiel.net, Alternate,
  │                       TopAchat, Grosbill, et AliExpress pour les processeurs),
  │                       puis les fiches Ledenicheur (Amazon, Cdiscount, Fnac,
  │                       Kaufland…, livraison incluse si connue)
  │  scripts/record.py  → data/cpu/latest.json + data/cpu/history.json, et l'alerte
  │  scripts/notify.py  → notification ntfy, seulement s'il y a une alerte
  ├──────────────► GitHub Pages republie l'appli (moins d'une minute)
  └──────────────► notification sur le téléphone (appli ntfy, canal de config.json)

Bouton ↻ de l'appli
  │  publie une demande sur le canal ntfy « …-releve » (sans clé)
  └──────────────► le robot, qui surveille ce canal toutes les 15 s, fait un relevé
```

- `config.json` : les produits suivis (et leurs versions : `box`/`tray` pour un
  processeur, `std` pour la carte mère), les **seuils d'alerte** par produit et
  version (`thresholds_eur["9800x3d"].box`, `thresholds_eur.b850m.std`…),
  l'horaire et le canal ntfy.
- `scripts/collect.py` : le relevé, et la liste des produits suivis
  (`PRODUCTS` : références, titres reconnus, recherches, fiches Ledenicheur) ;
  `scripts/sources/` : un module par boutique lue en direct
  (`collect(fetch, product)` renvoie ses offres).
- `scripts/record.py` : valide le relevé, calcule les meilleurs prix, les
  « bonnes affaires » et les baisses significatives, met à jour les données et
  prépare l'alerte.
- `index.html`, `app.js`, `style.css`, `sw.js`, `manifest.webmanifest` :
  l'appli (PWA installable, fonctionne hors ligne avec les dernières données).

L'appli a quatre onglets :

- **Marché** : choix du produit (7800X3D, 9800X3D ou B850M), bonne affaire ou
  non (y compris sur un autre produit), meilleur prix, écart au seuil, résumé
  par version, prochain relevé.
- **Offres** : toutes les offres relevées, filtrables (Box, Tray, disponibles,
  prix confirmés) et triables, avec des fiches détaillées.
- **Historique** : courbe du meilleur prix (Box et Tray pour un processeur) sur
  7 jours, 30 jours ou tout, avec plus bas, plus haut et tous les relevés.
- **Réglages** : notifications, produit et version affichés, tri, thème,
  seuils, prix habituels et prix d'alerte de baisse.

Une **bonne affaire** est une offre neuve, en stock (ou sur commande), dont le
prix est confirmé (vu chez la boutique, ou relevé pour elle par Ledenicheur) et
sous le seuil de sa version.

Une **baisse significative** : le prix sûr le plus bas d'un produit (en stock ou
sur commande, boutique identifiée, frais de port connus) passe au moins **5 % et
10 €** sous son **prix habituel**, la médiane des relevés complets des 7 derniers
jours (il en faut au moins 12, soit environ une journée). Une baisse n'est
annoncée qu'une fois ; il faut qu'elle s'accentue d'au moins 5 € (et 2 %) pour
une nouvelle alerte. Elle est oubliée quand le prix revient à la normale, au
plus tôt 24 h après l'alerte.

## Recevoir les notifications

1. Installe l'appli gratuite **ntfy** (App Store ou Play Store), sans compte.
2. Touche **+**, entre le nom du canal (Réglages de l'appli, ou `ntfy.topic`
   dans `config.json`), puis « S'abonner ».

Les prix sont relevés chaque heure (6h13 à 23h13), mais une notification
n'arrive que pour une **nouvelle bonne affaire** ou une **baisse significative**
(processeurs comme carte mère). Une affaire déjà annoncée ne l'est de nouveau
que si son prix baisse encore d'au moins 5 € (et 2 %), ou après 24 h sans la voir.

## Installer l'appli sur le téléphone

- **iPhone** : ouvre le lien dans **Safari** → bouton Partager → « Sur l'écran
  d'accueil ».
- **Android** : ouvre le lien dans **Chrome** → menu ⋮ → « Installer
  l'application ».

## Modifier les réglages

- **Seuils** : change `thresholds_eur` dans `config.json` (depuis l'appli
  GitHub ou github.com). Pris en compte au relevé suivant.
- **Horaires** : un relevé par heure à hh:13 de 6h à 23h, réglés dans
  `.github/workflows/actualiser.yml` (et `schedule` dans `config.json` pour
  l'affichage).

## Tester en local

```sh
python3 -m http.server 8000                    # puis ouvre http://localhost:8000
python3 scripts/collect.py /tmp/run.json       # relevé réel, sans rien publier
python3 scripts/record.py /tmp/run.json --dry-run
```
