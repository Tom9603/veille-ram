# Veille RAM

Suivi automatique du prix d'un kit **DDR5 2×16 Go 6000 MHz** (CL30 en priorité,
CL32/CL36 en plan B), avec une appli mobile pour consulter l'état du marché.

**Appli :** https://tom9603.github.io/veille-ram/

## Comment ça marche

```
Routine Claude (11h58 et 19h58, heure de Paris)
  │  cherche les prix (Ledenicheur, LDLC, Materiel.net, Grosbill, Amazon, Dealabs…)
  │  python3 scripts/record.py  → data/latest.json + data/history.json
  │  git push sur gh-pages (la branche publiée par GitHub Pages)
  ├──────────────► GitHub Pages republie l'appli (1 à 2 min)
  └──────────────► notification push dans l'appli Claude (résumé + lien)
```

- `AGENT.md` : les consignes que l'agent suit à chaque passage.
- `config.json` : le produit, les **seuils d'alerte** et l'horaire affiché.
- `scripts/record.py` : valide le relevé de l'agent, calcule les meilleurs
  prix et les « bonnes affaires », met à jour les données.
- `index.html`, `app.js`, `style.css`, `sw.js`, `manifest.webmanifest` :
  l'appli (PWA installable, fonctionne hors ligne avec les dernières données).

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
