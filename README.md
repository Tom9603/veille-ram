# Veille RAM

Suivi automatique du prix d'un kit **DDR5 2×16 Go** : **6000 MHz** (CL30 en priorité,
CL32/CL36 en plan B), **5600 MHz** (CL28 à CL36) et **6400 MHz et plus** quand
la latence réelle est au moins aussi bonne qu'en 5600 CL36 (6400 jusqu'à CL40,
7200 jusqu'à CL46…), avec une appli mobile pour consulter l'état du marché.

**Appli :** https://tom9603.github.io/veille-ram/

## Comment ça marche

```
GitHub Actions « Actualiser les prix » (un relevé par heure de 6h à 23h, et à la demande)
  │  GitHub lance les tâches programmées avec des heures de retard : le robot
  │  tourne donc en continu, fait lui-même un relevé à hh:13 (rien la nuit) et
  │  se passe le relais avant la limite de 6 h par job ; la programmation ne
  │  sert que de secours si la chaîne s'arrête
  │  scripts/collect.py : LDLC, Materiel.net, Alternate, Grosbill en direct,
  │                       Amazon, Cdiscount, Fnac… via les fiches Ledenicheur
  │  scripts/record.py  → data/latest.json + data/history.json
  │  scripts/notify.py  → notification ntfy (chaque heure ; sinon seulement si affaire)
  ├──────────────► GitHub Pages republie l'appli (moins d'une minute)
  └──────────────► notification sur le téléphone (appli ntfy, canal de config.json)

Bouton ↻ de l'appli
  │  publie une demande sur le canal ntfy « …-releve » (sans clé)
  └──────────────► le robot, qui surveille ce canal toutes les 15 s, fait un relevé
```

- `AGENT.md` : consignes pour une recherche complète par un agent IA (utilisables
  si une routine Claude a un accès en écriture au dépôt).
- `config.json` : le produit, les **seuils d'alerte** et l'horaire affiché.
- `scripts/record.py` : valide le relevé de l'agent, calcule les meilleurs
  prix et les « bonnes affaires », met à jour les données.
- `index.html`, `app.js`, `style.css`, `sw.js`, `manifest.webmanifest` :
  l'appli (PWA installable, fonctionne hors ligne avec les dernières données).

L'appli a quatre onglets :

- **Marché** : bonne affaire ou non, meilleur prix, écart au seuil, résumé par
  catégorie (6000 CL30, CL32, CL36, 5600, 6400+) et prochain relevé.
- **Offres** : toutes les offres relevées, filtrables par latence, triables
  (prix croissant ou décroissant, latence, boutique), avec filtres
  « disponibles » et « prix vérifiés » et des fiches détaillées (référence,
  prix au Go, écart au seuil, vendeur).
- **Historique** : courbe du meilleur prix par latence sur 7 jours, 30 jours ou
  tout, avec plus bas, plus haut et tous les relevés.
- **Réglages** : latence suivie, tri, thème clair/sombre, seuils, horaires.
  Ces préférences sont mémorisées sur le téléphone.

Une **bonne affaire** est une offre en stock (ou sur commande), dont le prix a
été vérifié sur la page de la boutique, et sous le seuil :
400 € ou moins pour tout kit au moins 5600 CL36 (5600 CL28 à CL36, 6000 CL30
à CL36, 6400 MHz et plus), modifiable dans `config.json` (`thresholds_eur`).

## Installer l'appli sur le téléphone

- **iPhone** : ouvre le lien dans **Safari** → bouton Partager → « Sur l'écran
  d'accueil ».
- **Android** : ouvre le lien dans **Chrome** → menu ⋮ → « Installer
  l'application » (ou « Ajouter à l'écran d'accueil »).

L'appli s'ouvre alors en plein écran comme une appli normale et se met à jour
à chaque ouverture.

## Recevoir les notifications

1. Installe l'appli gratuite **ntfy** (App Store ou Play Store), sans compte.
2. Touche **+**, entre le nom du canal (Réglages de l'appli Veille RAM, ou
   `ntfy.topic` dans `config.json`), puis « S'abonner ».

Une notification arrive à chaque relevé de l'heure (6h13 à 23h13) : discrète
s'il n'y a pas d'affaire, prioritaire dès qu'un kit passe sous le seuil.

Le bouton ↻ de l'appli lance un vrai relevé (1 à 2 minutes), sans clé : il
publie une demande sur le canal `ntfy.refresh_topic`, que le robot surveille.

## Modifier les réglages

- **Seuils** : change `thresholds_eur` dans `config.json` (ex. depuis l'appli
  GitHub ou github.com). Pris en compte au passage suivant.
- **Horaires** : un relevé par heure à hh:13 de 6h à 23h, réglés dans
  `.github/workflows/actualiser.yml` (et `schedule` dans `config.json` pour
  l'affichage).
- **Comportement de l'agent** : modifie `AGENT.md`.

## Tester en local

```sh
python3 -m http.server 8000      # puis ouvre http://localhost:8000
python3 scripts/record.py run.json --dry-run   # valide un relevé sans rien écrire
```
