#!/usr/bin/env python3
"""Envoie au téléphone (appli ntfy) l'alerte du dernier relevé, s'il y en a une.

Usage :
    python3 scripts/notify.py

Lit le champ « push » de data/cpu/latest.json (écrit par scripts/record.py) et le
canal ntfy de config.json. Seules les alertes (priorité 5) partent : nouvelle bonne
affaire sous le seuil, ou baisse de prix significative. Le résumé d'un relevé sans
alerte reste dans les données (et dans l'appli) sans notification.
L'option --deals-only (ancien relevé « à la demande ») est acceptée et ne change rien.
"""

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv):
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    latest = json.loads((ROOT / "data" / "cpu" / "latest.json").read_text(encoding="utf-8"))
    ntfy, push = config.get("ntfy"), latest.get("push")
    if not ntfy or not push:
        print("Pas de canal ntfy ou pas de notification : rien à envoyer.")
        return
    if push.get("priority", 0) < 5:
        print(f"Pas d'alerte (ni nouvelle affaire, ni baisse significative) : pas de notification. ({push['title']})")
        return
    body = {
        "topic": ntfy["topic"],
        "title": push["title"],
        "message": push["message"],
        "priority": push["priority"],
        "tags": push.get("tags", []),
        "click": push["click"],
        "actions": [{"action": "view", "label": "Ouvrir l'appli", "url": config["app_url"]}],
    }
    req = urllib.request.Request(ntfy["server"].rstrip("/") + "/", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            print(f"Notification envoyée ({res.status}) : {push['title']}")
    except Exception as err:  # ntfy injoignable ou quota atteint : le relevé, lui, est publié
        print(f"Notification non envoyée : {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
