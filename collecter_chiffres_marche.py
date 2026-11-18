"""Chiffres de marché publics des antiglaucomateux : Open Medic (France) et Medicare Part D (États-Unis).

Lancement :  python collecter_chiffres_marche.py
Résultat  :  data/historique/chiffres_marche.json (repris par construire_site.py pour la page Marché).

Mise à jour automatique et légère : une année Open Medic déjà enregistrée n'est jamais retéléchargée ;
chaque jour, on regarde seulement si l'année suivante est publiée. Medicare n'est retéléchargé que si CMS
publie une nouvelle version. Une source en panne garde les chiffres de la collecte précédente.
Pour retirer cette partie du site : supprimer ce fichier, son étape dans .github/workflows/veille-quotidienne.yml,
la section « Chiffres de marché » de site/marche.html et site/js/chiffres_marche.js.
"""
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from veille.sources import chiffres_marche as cm  # noqa: E402

FICHIER = Path(__file__).resolve().parent / "data" / "historique" / "chiffres_marche.json"


def main():
    ancien = json.loads(FICHIER.read_text(encoding="utf-8")) if FICHIER.exists() else {}
    france = ancien.get("france") or {"source": "Open Medic — Assurance Maladie (tous régimes)", "url": cm.OPEN_MEDIC_PAGE,
                                      "classe": "S01E — antiglaucomateux et myotiques", "annees": {}}
    for annee in range(cm.PREMIERE_ANNEE, datetime.date.today().year + 1):
        if str(annee) in france["annees"]:
            continue
        try:
            r = cm.open_medic_annee(annee)
        except Exception as e:  # une année en panne n'empêche pas les autres
            print(f"Open Medic {annee} : échec ({e})")
            continue
        if r is None:
            print(f"Open Medic {annee} : pas encore publiée")
            continue
        france["annees"][str(annee)] = r
        print(f"Open Medic {annee} : {r['boites']:,} boîtes, {len(r['molecules'])} molécules".replace(",", " "))
    france["annees"] = dict(sorted(france["annees"].items()))
    try:
        usa = cm.medicare(ancien.get("usa"))
        print(f"Medicare Part D : {len(usa['lignes'])} médicaments, années {usa['annees']}")
    except Exception as e:
        usa = ancien.get("usa")
        print(f"Medicare Part D : échec ({e}), chiffres précédents gardés")
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    FICHIER.write_text(json.dumps({"verifie_le": datetime.date.today().isoformat(), "france": france, "usa": usa},
                                  ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
