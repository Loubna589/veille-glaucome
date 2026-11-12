"""Taux de concordance de nos extractions « accès au marché » avec les sources officielles.

Lancement :  python eval/evaluer_verif_marche.py

Lit eval/verif_marche.csv (colonne `verifie_loubna` : 1 = exact, 0 = faux) et calcule :
- le taux de concordance global = valeurs exactes / valeurs vérifiées ;
- le taux par type de valeur (date d'AMM, SMR, ASMR, taux de remboursement, prix…) ;
- la liste des écarts, pour corriger l'extraction.
Les lignes non vérifiées sont ignorées (et comptées).
"""
import csv
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
FICHIER = RACINE / "eval" / "verif_marche.csv"
SORTIE = RACINE / "eval" / "resultats_verif_marche.json"


def concordance(lignes):
    """Renvoie le bilan, ou None si aucune ligne n'est vérifiée."""
    verifiees = [l for l in lignes if (l.get("verifie_loubna") or "").strip() in ("0", "1")]
    if not verifiees:
        return None
    par_champ = {}
    for l in verifiees:
        c = par_champ.setdefault(l["champ"], {"verifiees": 0, "exactes": 0})
        c["verifiees"] += 1
        c["exactes"] += l["verifie_loubna"].strip() == "1"
    for c in par_champ.values():
        c["taux"] = round(c["exactes"] / c["verifiees"], 3)
    exactes = sum(c["exactes"] for c in par_champ.values())
    return {"valeurs_verifiees": len(verifiees), "valeurs_total": len(lignes), "exactes": exactes,
            "taux_concordance": round(exactes / len(verifiees), 3), "par_champ": par_champ,
            "ecarts": [{k: l.get(k) for k in ("medicament", "champ", "valeur_outil", "commentaire")}
                       for l in verifiees if l["verifie_loubna"].strip() == "0"]}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    lignes = list(csv.DictReader(FICHIER.open(encoding="utf-8-sig"), delimiter=";"))
    bilan = concordance(lignes)
    if bilan is None:
        print(f"Aucune valeur vérifiée dans {FICHIER.name} ({len(lignes)} lignes) : mettez 1 (exact) ou 0 (faux) "
              "dans la colonne verifie_loubna.")
        return 0
    print(f"Concordance : {bilan['taux_concordance']:.1%} ({bilan['exactes']}/{bilan['valeurs_verifiees']} valeurs vérifiées "
          f"sur {bilan['valeurs_total']})")
    for champ, c in sorted(bilan["par_champ"].items()):
        print(f"  {champ:20} {c['taux']:.0%} ({c['exactes']}/{c['verifiees']})")
    for e in bilan["ecarts"]:
        print(f"  ÉCART — {e['medicament'][:50]} · {e['champ']} = {e['valeur_outil']} · {e['commentaire']}")
    SORTIE.write_text(json.dumps(bilan, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
