# Veille RAM

Suivi automatique du prix d'un kit **DDR5 2×16 Go 6000 MHz** (CL30 en priorité,
CL32/CL36 en plan B), avec une appli mobile pour consulter l'état du marché.

**Appli :** https://tom9603.github.io/veille-ram/

## Comment ça marche

```
GitHub Actions « Actualiser les prix » (11h40, 19h40, et à chaque ↻ dans l'appli)
  │  scripts/collect.py : LDLC, Materiel.net, Alternate, Grosbill en direct,
  │                       Amazon, Cdiscount, Fnac… via les fiches Ledenicheur
  │  scripts/record.py  → data/latest.json + data/history.json
  └──────────────► GitHub Pages republie l'appli (moins d'une minute)

Routine Claude (11h58 et 19h58, heure de Paris)
  │  lit le dernier relevé + cherche les bons plans récents sur Dealabs
  └──────────────► notification push dans l'appli Claude (résumé + lien)
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
  latence (CL30, CL32, CL36) et prochaine analyse.
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
CL30 ≤ 400 €, CL32/CL36 ≤ 360 € (modifiable dans `config.json`).

## Installer l'appli sur le téléphone

- **iPhone** : ouvre le lien dans **Safari** → bouton Partager → « Sur l'écran
  d'accueil ».
- **Android** : ouvre le lien dans **Chrome** → menu ⋮ → « Installer
  l'application » (ou « Ajouter à l'écran d'accueil »).

L'appli s'ouvre alors en plein écran comme une appli normale et se met à jour
à chaque ouverture.

## Activer l'actualisation à la demande

Le bouton ↻ de l'appli lance une vraie recherche de prix. Il lui faut une clé
GitHub, à créer une seule fois :

1. Sur https://github.com/settings/personal-access-tokens/new : nom
   « Veille RAM », expiration au choix (1 an par exemple).
2. **Repository access** : « Only select repositories » → `veille-ram`.
3. **Permissions** → **Actions** : « Read and write ».
4. Génère la clé, copie-la (`github_pat_…`) et colle-la dans l'appli :
   Réglages → Actualisation des prix → Enregistrer.

La clé reste sur ton téléphone et n'est envoyée qu'à api.github.com.

## Modifier les réglages

- **Seuils** : change `thresholds_eur` dans `config.json` (ex. depuis l'appli
  GitHub ou github.com). Pris en compte au passage suivant.
- **Horaires** : se règlent dans la routine Claude (claude.ai → Routines), puis
  mets à jour `schedule.times` dans `config.json` pour l'affichage.
- **Comportement de l'agent** : modifie `AGENT.md`.

## Tester en local

```sh
python3 -m http.server 8000      # puis ouvre http://localhost:8000
python3 scripts/record.py run.json --dry-run   # valide un relevé sans rien écrire
```
