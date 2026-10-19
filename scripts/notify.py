#!/usr/bin/env python3
"""Envoie au téléphone (appli ntfy) la notification du dernier relevé.

Usage :
    python3 scripts/notify.py              # relevé de l'heure : toujours envoyée
    python3 scripts/notify.py --deals-only # relevé demandé depuis l'appli : seulement pour une nouvelle affaire

Lit le champ « push » de data/cpu/latest.json (écrit par scripts/record.py) et le
canal ntfy de config.json. Sans affaire, ou pour une affaire déjà annoncée, la
notification est discrète (priorité basse) ; une nouvelle affaire sonne (priorité maximale).
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
    if "--deals-only" in argv and push.get("priority", 0) < 5:
        print("Pas de nouvelle affaire : pas de notification pour ce relevé demandé depuis l'appli.")
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
