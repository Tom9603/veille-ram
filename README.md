# Veille X3D

Suivi automatique du prix des **AMD Ryzen 7 7800X3D** et **9800X3D** neufs, en
version **Box** (en boîte, garantie AMD 3 ans) et **Tray** (sans boîte, OEM,
garantie du vendeur), avec une appli mobile et une notification chaque heure.

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
  │  scripts/collect.py : pour chaque processeur (PRODUCTS), boutiques lues en
  │                       direct (scripts/sources/), puis les fiches Box et Tray
  │                       de Ledenicheur (Amazon, Cdiscount,
  │                       Fnac, AliExpress…, livraison incluse si connue)
  │  scripts/record.py  → data/cpu/latest.json + data/cpu/history.json
  │  scripts/notify.py  → notification ntfy (chaque heure ; sinon seulement si affaire)
  ├──────────────► GitHub Pages republie l'appli (moins d'une minute)
  └──────────────► notification sur le téléphone (appli ntfy, canal de config.json)

Bouton ↻ de l'appli
  │  publie une demande sur le canal ntfy « …-releve » (sans clé)
  └──────────────► le robot, qui surveille ce canal toutes les 15 s, fait un relevé
```

- `config.json` : les processeurs suivis, les **seuils d'alerte** par processeur
  et version (`thresholds_eur["9800x3d"].box`…), l'horaire et le canal ntfy.
- `scripts/collect.py` : le relevé, et la liste des processeurs suivis
  (`PRODUCTS` : références AMD, fiches Ledenicheur) ; `scripts/sources/` : un
  module par boutique lue en direct (`collect(fetch, product)` renvoie ses offres).
- `scripts/record.py` : valide le relevé, calcule les meilleurs prix et les
  « bonnes affaires », met à jour les données et prépare la notification.
- `index.html`, `app.js`, `style.css`, `sw.js`, `manifest.webmanifest` :
  l'appli (PWA installable, fonctionne hors ligne avec les dernières données).

L'appli a quatre onglets :

- **Marché** : choix du processeur (7800X3D ou 9800X3D), bonne affaire ou non
  (y compris sur l'autre processeur), meilleur prix, écart au seuil, résumé Box
  et Tray, prochain relevé.
- **Offres** : toutes les offres relevées, filtrables (Box, Tray, disponibles,
  prix confirmés) et triables, avec des fiches détaillées.
- **Historique** : courbe du meilleur prix Box et Tray sur 7 jours, 30 jours ou
  tout, avec plus bas, plus haut et tous les relevés.
- **Réglages** : notifications, version affichée, tri, thème, seuils.

Une **bonne affaire** est une offre neuve, en stock (ou sur commande), dont le
prix est confirmé (vu chez la boutique, ou relevé pour elle par Ledenicheur) et
sous le seuil de sa version.

## Recevoir les notifications

1. Installe l'appli gratuite **ntfy** (App Store ou Play Store), sans compte.
2. Touche **+**, entre le nom du canal (Réglages de l'appli, ou `ntfy.topic`
   dans `config.json`), puis « S'abonner ».

Une notification arrive à chaque relevé de l'heure (6h13 à 23h13) : discrète
s'il n'y a pas d'affaire, prioritaire pour une nouvelle affaire.

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
