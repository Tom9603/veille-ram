#!/usr/bin/env python3
"""Valide un relevé de prix du Ryzen 7 7800X3D et met à jour les données de l'appli.

Usage :
    python3 scripts/record.py /chemin/vers/run.json [--dry-run]

Entrée (run.json, écrit par scripts/collect.py HORS du dépôt) :
{
  "checked_at": "2026-10-16T19:13:00+02:00",   # optionnel, défaut = maintenant
  "offers": [
    {
      "name": "AMD Ryzen 7 7800X3D",            # libellé court
      "ref": "100-100000910WOF",                # référence fabricant ("" si inconnue)
      "version": "box",                          # box (en boîte) | tray (sans boîte, OEM)
      "price_eur": 309.0,                        # TTC, livraison incluse si affichée
      "shop": "Fnac Marketplace",
      "stock": "in_stock",                       # in_stock | on_order | out_of_stock | unknown
      "marketplace": true,                       # vendeur tiers ?
      "verified": false,                         # prix vu sur la page de la boutique ?
      "via": "Ledenicheur",                      # optionnel : prix d'une boutique relevé par un comparateur
      "shipping": "included",                    # optionnel : included (port compris) | unknown (port inconnu)
      "url": "https://..."
    }
  ],
  "trend": "Une phrase sur le relevé.",
  "blocked_sources": ["amazon.fr"]
}

Sorties : data/cpu/latest.json (état courant) et data/cpu/history.json (une ligne
par relevé). data/latest.json et data/history.json sont les données figées de
l'ancienne veille RAM, gardées pour les appareils qui ont encore l'ancienne appli. Le texte de la notification est affiché sur la sortie standard et
enregistré dans data/latest.json (champ « notification ») ; sa version courte
pour le téléphone (ntfy) est dans le champ « push », envoyée par scripts/notify.py.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.json"
LATEST = ROOT / "data" / "cpu" / "latest.json"
HISTORY = ROOT / "data" / "cpu" / "history.json"
NOTIFIED_HOURS = 24   # une affaire absente des relevés plus longtemps sera annoncée de nouveau

VERSIONS = {"box": "Box", "tray": "Tray"}
STOCKS = {"in_stock", "on_order", "out_of_stock", "unknown"}
STOCK_LABELS = {
    "in_stock": "en stock",
    "on_order": "sur commande",
    "out_of_stock": "rupture",
    "unknown": "stock ?",
}


def fail(errors):
    print("ERREUR : relevé invalide, rien n'a été écrit.", file=sys.stderr)
    for e in errors:
        print(f"  - {e}", file=sys.stderr)
    sys.exit(2)


def eur(value):
    if value is None:
        return "—"
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return text[:-3] if text.endswith(",00") else text


def validate(run):
    errors = []
    if not isinstance(run, dict):
        fail(["le fichier doit contenir un objet JSON"])
    offers = run.get("offers")
    if not isinstance(offers, list):
        fail(["'offers' doit être une liste (vide si rien trouvé)"])
    for i, o in enumerate(offers):
        where = f"offers[{i}]"
        if not isinstance(o, dict):
            errors.append(f"{where} doit être un objet")
            continue
        for key in ("name", "shop", "url"):
            if not isinstance(o.get(key), str) or not o[key].strip():
                errors.append(f"{where}.{key} doit être un texte non vide")
        if not isinstance(o.get("ref", ""), str):
            errors.append(f"{where}.ref doit être un texte")
        if o.get("version") not in VERSIONS:
            errors.append(f"{where}.version doit valoir box ou tray (reçu {o.get('version')!r})")
        price = o.get("price_eur")
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not 50 <= price <= 2000:
            errors.append(f"{where}.price_eur doit être un nombre entre 50 et 2000 (reçu {price!r})")
        if o.get("stock") not in STOCKS:
            errors.append(f"{where}.stock doit être l'un de {sorted(STOCKS)} (reçu {o.get('stock')!r})")
        for key in ("marketplace", "verified"):
            if not isinstance(o.get(key), bool):
                errors.append(f"{where}.{key} doit être true ou false")
        if not isinstance(o.get("via", ""), str):
            errors.append(f"{where}.via doit être un texte")
        if o.get("shipping", "included") not in ("included", "unknown"):
            errors.append(f"{where}.shipping doit valoir included ou unknown (reçu {o.get('shipping')!r})")
        if isinstance(o.get("url"), str) and not o["url"].startswith("https://"):
            errors.append(f"{where}.url doit commencer par https://")
    if not isinstance(run.get("trend", ""), str):
        errors.append("'trend' doit être un texte")
    blocked = run.get("blocked_sources", [])
    if not isinstance(blocked, list) or not all(isinstance(b, str) for b in blocked):
        errors.append("'blocked_sources' doit être une liste de textes")
    checked_at = run.get("checked_at")
    if checked_at is not None:
        try:
            if datetime.fromisoformat(checked_at).tzinfo is None:
                errors.append("'checked_at' doit inclure le fuseau (ex. +02:00)")
        except (TypeError, ValueError):
            errors.append(f"'checked_at' n'est pas une date ISO 8601 valide (reçu {checked_at!r})")
    if errors:
        fail(errors)


def offer_key(o):
    return (o["shop"].strip().lower(), o["version"], o["url"].strip())


def dedupe(offers):
    """Une seule fois chaque offre (même boutique, même version, même lien) : la moins chère."""
    best = {}
    for o in offers:
        key = offer_key(o)
        if key not in best or o["price_eur"] < best[key]["price_eur"]:
            best[key] = o
    return sorted(best.values(), key=lambda o: (o["price_eur"], o["version"]))


def summary(offer):
    if offer is None:
        return None
    return {k: offer[k] for k in ("name", "ref", "version", "price_eur", "shop", "stock", "url")}


def limit_for(offer, thresholds):
    return thresholds.get(offer["version"], thresholds.get("box"))


def deal_key(o):
    """Une affaire = une boutique et une version, quel que soit le lien (direct ou via Ledenicheur)."""
    return f"{o['shop'].strip().lower().replace(' marketplace', '')}|{o['version']}"


def announce(deals, previous_latest, checked_at):
    """Affaires à annoncer (jamais annoncées, ou moins chères qu'à l'annonce) et mémoire des annonces.

    La mémoire survit à un relevé incomplet (source bloquée une heure) : une affaire n'est
    annoncée de nouveau qu'après NOTIFIED_HOURS sans la voir, ou si son prix baisse encore.
    """
    now = datetime.fromisoformat(checked_at)
    notified = {}
    for key, n in ((previous_latest or {}).get("notified") or {}).items():
        try:
            if (now - datetime.fromisoformat(n["seen"])).total_seconds() < NOTIFIED_HOURS * 3600:
                notified[key] = n
        except (KeyError, TypeError, ValueError):
            pass   # entrée illisible : oubliée
    new = []
    for o in deals:   # du moins cher au plus cher
        n = notified.get(deal_key(o))
        if n is None or o["price_eur"] < n["price"] - 0.5:
            new.append(o)
            notified[deal_key(o)] = {"price": o["price_eur"], "seen": checked_at}
        else:
            notified[deal_key(o)] = {**n, "seen": checked_at}
    return new, notified


def push_message(deals, new, best, changes, thresholds, blocked, app_url):
    """Notification courte pour le téléphone : titre, texte, priorité ntfy, lien."""
    if deals:
        top = new[0] if new else deals[0]
        lines = [f"{top['name']} {VERSIONS[top['version']]} chez {top['shop']} ({STOCK_LABELS[top['stock']]}), "
                 f"seuil {eur(limit_for(top, thresholds))} €."]
        if top.get("shipping") == "unknown":
            lines.append("Frais de port inconnus : vérifie le total avant d'acheter.")
        if len(deals) > 1:
            lines.append(f"{len(deals) - 1} autre{'s' if len(deals) > 2 else ''} offre{'s' if len(deals) > 2 else ''} sous le seuil.")
        return {
            "title": f"{'Bonne affaire' if new else 'Toujours en cours'} : 7800X3D {VERSIONS[top['version']]} à {eur(top['price_eur'])} €",
            "message": "\n".join(lines),
            # Nouvelle affaire : alerte. Affaire déjà annoncée : rappel silencieux, comme « pas d'affaire ».
            "priority": 5 if new else 2,
            "tags": ["rotating_light"] if new else ["moneybag"],
            "click": top["url"],
        }
    lines = []
    for version, label in VERSIONS.items():
        o = best.get(version)
        if o:
            gap = o["price_eur"] - limit_for(o, thresholds)
            note = f"{eur(gap)} € au-dessus du seuil" if gap > 0 else "sous le seuil, mais stock ou prix non confirmé"
            lines.append(f"{label} {eur(o['price_eur'])} € chez {o['shop']} ({note})")
        else:
            lines.append(f"{label} : aucune offre disponible")
    moves = [f"{label} {'+' if changes[v] > 0 else '−'}{eur(abs(changes[v]))} €" for v, label in VERSIONS.items() if changes.get(v)]
    if moves:
        lines.append("Depuis le relevé précédent : " + ", ".join(moves))
    if blocked:
        lines.append(f"Source{'s' if len(blocked) > 1 else ''} inaccessible{'s' if len(blocked) > 1 else ''} : "
                     f"{', '.join(blocked)} (prix peut-être incomplets)")
    tops = [o for o in best.values() if o]
    top = min(tops, key=lambda o: o["price_eur"]) if tops else None
    return {
        "title": f"Pas d'affaire : {eur(top['price_eur'])} € au mieux ({VERSIONS[top['version']]})" if top
        else "Pas d'affaire : aucune offre disponible",
        "message": "\n".join(lines),
        "priority": 2,
        "tags": [],
        "click": app_url,
    }


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    dry_run = "--dry-run" in argv
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    tz = ZoneInfo(config["schedule"]["timezone"])
    run = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    validate(run)

    thresholds = config["thresholds_eur"]
    checked_at = run.get("checked_at") or datetime.now(tz).isoformat(timespec="minutes")

    offers = []
    for o in dedupe(run["offers"]):
        o = {**o, "ref": o.get("ref", "").strip(), "price_eur": round(float(o["price_eur"]), 2)}
        # Bonne affaire : disponible, sous le seuil, et prix d'une boutique identifiée
        # (vu chez elle, ou relevé pour elle par un comparateur).
        o["deal"] = (
            o["stock"] in ("in_stock", "on_order")
            and (o["verified"] or bool(o.get("via")))
            and o["price_eur"] <= limit_for(o, thresholds)
        )
        offers.append(o)

    # Meilleur prix « listé » par version : tout sauf les ruptures confirmées.
    listed = [o for o in offers if o["stock"] != "out_of_stock"]
    best = {v: summary(next((o for o in listed if o["version"] == v), None)) for v in VERSIONS}
    deals = [o for o in offers if o["deal"]]

    previous_latest = json.loads(LATEST.read_text(encoding="utf-8")) if LATEST.exists() else None
    history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []
    history = [h for h in history if h["checked_at"] != checked_at]
    previous = next((h for h in reversed(history) if not h.get("partial")), None)   # dernier relevé complet

    def change(key):
        now, before = best[key], (previous or {}).get(key)
        if now is None or before is None:
            return None
        return round(now["price_eur"] - before["price_eur"], 2)

    # Relevé incomplet (source bloquée) : pas de « depuis le relevé précédent », ce serait une fausse variation.
    blocked = run.get("blocked_sources", [])
    changes = {key: None if blocked else change(key) for key in best}
    new, notified = announce(deals, previous_latest, checked_at)

    if deals:
        top = deals[0]
        headline = (f"🚨 BONNE AFFAIRE : {top['name']} {VERSIONS[top['version']]} à {eur(top['price_eur'])} € "
                    f"chez {top['shop']}")
    else:
        parts = [f"meilleur {label} {eur(best[v]['price_eur'])} € ({best[v]['shop']})" if best[v] else f"aucun {label} disponible"
                 for v, label in VERSIONS.items()]
        text = ", ".join(parts)
        headline = "Ryzen 7 7800X3D : pas d'affaire. " + text[0].upper() + text[1:]

    latest = {
        "checked_at": checked_at,
        "product": config["product"],
        "thresholds_eur": thresholds,
        "deal": bool(deals),
        "headline": headline,
        "best": best,
        "change_since_previous_eur": changes,
        "offers": offers,
        "trend": run.get("trend", "").strip(),
        "blocked_sources": blocked,
        "notified": notified,
    }
    row = {"checked_at": checked_at, **best, "deal": bool(deals), "offers_count": len(offers)}
    if blocked:
        row["partial"] = True   # meilleurs prix peut-être faussés : l'appli ne les trace pas
    history.append(row)
    history.sort(key=lambda h: datetime.fromisoformat(h["checked_at"]))

    # Texte complet du relevé, prêt à recopier tel quel.
    lines = [headline]
    moves = [f"{label} {'+' if changes[v] > 0 else '−'}{eur(abs(changes[v]))} €" for v, label in VERSIONS.items() if changes[v]]
    if moves:
        lines.append("Depuis le relevé précédent : " + ", ".join(moves))
    lines += ["", "| Version | Prix | Boutique | Stock | Lien |", "|---|---|---|---|---|"]
    for o in offers[:6]:
        flags = (" (marketplace)" if o["marketplace"] else "") + (
            "" if o["verified"] else f" (via {o['via']})" if o.get("via") else " (non vérifié)")
        lines.append(f"| {VERSIONS[o['version']]} | {eur(o['price_eur'])} €{flags} | {o['shop']} "
                     f"| {STOCK_LABELS[o['stock']]} | {o['url']} |")
    if not offers:
        lines.append("| aucune offre trouvée | | | | |")
    lines.append("")
    if latest["trend"]:
        lines.append(f"Relevé : {latest['trend']}")
    if latest["blocked_sources"]:
        lines.append("Sources bloquées : " + ", ".join(latest["blocked_sources"]))
    lines.append(f"Appli : {config['app_url']}")
    latest["notification"] = "\n".join(lines)
    latest["push"] = push_message(deals, new, best, changes, thresholds, blocked, config["app_url"])

    if not dry_run:
        LATEST.parent.mkdir(parents=True, exist_ok=True)
        LATEST.write_text(json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(latest["notification"])
    if dry_run:
        print("\n(--dry-run : rien n'a été écrit)", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
