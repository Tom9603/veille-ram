#!/usr/bin/env python3
"""Valide les relevés d'un passage de l'agent et met à jour les données de l'appli.

Usage :
    python3 scripts/record.py /chemin/vers/run.json [--dry-run]

Entrée (run.json, écrit par l'agent HORS du dépôt) :
{
  "checked_at": "2026-10-07T19:58:00+02:00",   # optionnel, défaut = maintenant
  "offers": [
    {
      "name": "Kingston Fury Beast",           # nom commercial du kit
      "ref": "KF560C30BBEK2-32",               # référence fabricant ("" si inconnue)
      "cl": 30,                                 # 30, 32 ou 36
      "price_eur": 529.99,                      # TTC, livraison incluse si affichée
      "shop": "Grosbill",
      "stock": "in_stock",                      # in_stock | on_order | out_of_stock | unknown
      "marketplace": false,                     # vendeur tiers ?
      "verified": true,                         # prix vu sur la page produit ?
      "via": "Ledenicheur",                     # optionnel : prix d'une boutique précise relevé par un comparateur
      "url": "https://..."
    }
  ],
  "trend": "Une phrase sur la tendance.",
  "blocked_sources": ["idealo.fr"]
}

Sorties : data/latest.json (état courant) et data/history.json (une ligne par
passage). Le texte de la notification est affiché sur la sortie standard et
enregistré dans data/latest.json (champ « notification »).
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.json"
LATEST = ROOT / "data" / "latest.json"
HISTORY = ROOT / "data" / "history.json"

STOCKS = {"in_stock", "on_order", "out_of_stock", "unknown"}
STOCK_LABELS = {
    "in_stock": "en stock",
    "on_order": "sur commande",
    "out_of_stock": "rupture",
    "unknown": "stock ?",
}
CLS = {30, 32, 36}


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
        if o.get("cl") not in CLS:
            errors.append(f"{where}.cl doit valoir 30, 32 ou 36 (reçu {o.get('cl')!r})")
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


def dedupe(offers):
    """Garde l'offre la moins chère par (boutique, kit, CL)."""
    best = {}
    for o in offers:
        key = (o["shop"].strip().lower(), (o.get("ref") or o["name"]).strip().lower(), o["cl"])
        if key not in best or o["price_eur"] < best[key]["price_eur"]:
            best[key] = o
    return sorted(best.values(), key=lambda o: (o["price_eur"], o["cl"]))


def migrate(entry):
    """Anciennes lignes d'historique : CL32 et CL36 étaient regroupés dans cl32_36."""
    if "cl32" not in entry or "cl36" not in entry:
        merged = entry.get("cl32_36")
        entry = {
            **entry,
            "cl32": merged if merged and merged["cl"] == 32 else None,
            "cl36": merged if merged and merged["cl"] == 36 else None,
        }
    return entry


def summary(offer):
    if offer is None:
        return None
    return {k: offer[k] for k in ("name", "ref", "cl", "price_eur", "shop", "stock", "url")}


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
        limit = thresholds["cl30"] if o["cl"] == 30 else thresholds["cl32_36"]
        # Bonne affaire : disponible, sous le seuil, et prix d'une boutique identifiée
        # (vu chez elle, ou relevé pour elle par un comparateur).
        o["deal"] = (
            o["stock"] in ("in_stock", "on_order")
            and (o["verified"] or bool(o.get("via")))
            and o["price_eur"] <= limit
        )
        offers.append(o)

    # Meilleur prix « listé » : tout sauf les ruptures confirmées.
    listed = [o for o in offers if o["stock"] != "out_of_stock"]
    best_cl30 = next((o for o in listed if o["cl"] == 30), None)
    best_cl32 = next((o for o in listed if o["cl"] == 32), None)
    best_cl36 = next((o for o in listed if o["cl"] == 36), None)
    best_cl32_36 = next((o for o in listed if o["cl"] in (32, 36)), None)
    best = {
        "cl30": summary(best_cl30),
        "cl32": summary(best_cl32),
        "cl36": summary(best_cl36),
        "cl32_36": summary(best_cl32_36),
    }
    deals = [o for o in offers if o["deal"]]

    history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []
    history = [migrate(h) for h in history if h["checked_at"] != checked_at]
    previous = history[-1] if history else None

    def change(key):
        now, before = best[key], (previous or {}).get(key)
        if now is None or before is None:
            return None
        return round(now["price_eur"] - before["price_eur"], 2)

    changes = {key: change(key) for key in best}

    if deals:
        top = deals[0]
        headline = (
            f"🚨 BONNE AFFAIRE RAM : {top['name']} CL{top['cl']} à {eur(top['price_eur'])} € "
            f"chez {top['shop']}"
        )
    else:
        def part(label, o):
            return f"meilleur {label} {eur(o['price_eur'])} € ({o['shop']})" if o else f"aucun {label} trouvé"

        first = part("CL30", best_cl30)
        headline = (
            "RAM DDR5 32 Go 6000 : pas d'affaire. "
            + first[0].upper() + first[1:]
            + ", "
            + part("CL32/36", best_cl32_36)
        )

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
        "blocked_sources": run.get("blocked_sources", []),
    }
    history.append(
        {
            "checked_at": checked_at,
            **best,
            "deal": bool(deals),
            "offers_count": len(offers),
        }
    )
    history.sort(key=lambda h: datetime.fromisoformat(h["checked_at"]))

    # Texte de la notification, prêt à recopier tel quel.
    lines = [headline]
    moves = [
        f"{label} {'+' if d > 0 else '−'}{eur(abs(d))} €"
        for label, d in (("CL30", changes["cl30"]), ("CL32", changes["cl32"]), ("CL36", changes["cl36"]))
        if d
    ]
    if moves:
        lines.append("Depuis le dernier passage : " + ", ".join(moves))
    lines += ["", "| Kit | CL | Prix | Boutique | Stock | Lien |", "|---|---|---|---|---|---|"]
    for o in offers[:5]:
        flags = (" (marketplace)" if o["marketplace"] else "") + (
            "" if o["verified"] else f" (via {o['via']})" if o.get("via") else " (non vérifié)")
        lines.append(
            f"| {o['name']} | {o['cl']} | {eur(o['price_eur'])} €{flags} | {o['shop']} "
            f"| {STOCK_LABELS[o['stock']]} | {o['url']} |"
        )
    if not offers:
        lines.append("| aucune offre trouvée | | | | | |")
    lines.append("")
    if latest["trend"]:
        lines.append(f"Tendance : {latest['trend']}")
    if latest["blocked_sources"]:
        lines.append("Sources bloquées : " + ", ".join(latest["blocked_sources"]))
    lines.append(f"Appli : {config['app_url']}")
    latest["notification"] = "\n".join(lines)

    if not dry_run:
        LATEST.parent.mkdir(parents=True, exist_ok=True)
        LATEST.write_text(json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(latest["notification"])
    if dry_run:
        print("\n(--dry-run : rien n'a été écrit)", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
