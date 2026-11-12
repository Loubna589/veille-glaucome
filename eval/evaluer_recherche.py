"""Évalue la recherche sémantique : précision@5 et MRR, à partir des jugements de eval/questions_recherche.csv.

Lancement :  python eval/evaluer_recherche.py

- précision@5 : part des 5 premiers résultats jugés pertinents, moyenne sur les questions ;
- MRR (Mean Reciprocal Rank) : moyenne de 1 / rang du PREMIER résultat pertinent (0 si aucun) ;
  1,0 = le premier résultat est toujours pertinent ; 0,5 = en moyenne au 2e rang.
Seules les questions dont les 5 résultats ont été jugés (0 ou 1) sont comptées.
"""
import csv
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
FICHIER = RACINE / "eval" / "questions_recherche.csv"
SORTIE = RACINE / "eval" / "resultats_recherche.json"


def precision_a_k(jugements, k=5):
    """jugements : liste de 0/1 dans l'ordre des rangs."""
    return sum(jugements[:k]) / k


def rang_reciproque(jugements):
    return next((1 / rang for rang, j in enumerate(jugements, 1) if j), 0.0)


def evaluer(lignes, k=5):
    par_question = {}
    for l in lignes:
        par_question.setdefault(l["question_id"], {"question": l["question"], "lignes": []})["lignes"].append(l)
    detail = []
    for q_id, q in par_question.items():
        valeurs = [(l.get("pertinent_loubna") or "").strip() for l in sorted(q["lignes"], key=lambda x: int(x["rang"]))]
        if len(valeurs) < k or any(v not in ("0", "1") for v in valeurs[:k]):
            continue  # question pas (entièrement) jugée
        jugements = [int(v) for v in valeurs]
        detail.append({"question_id": q_id, "question": q["question"], "precision_a_5": precision_a_k(jugements, k),
                       "rr": round(rang_reciproque(jugements), 3)})
    if not detail:
        return None
    return {"questions_jugees": len(detail), "questions_total": len(par_question),
            "precision_a_5": round(sum(d["precision_a_5"] for d in detail) / len(detail), 3),
            "mrr": round(sum(d["rr"] for d in detail) / len(detail), 3), "detail": detail}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    lignes = list(csv.DictReader(FICHIER.open(encoding="utf-8-sig"), delimiter=";"))
    resultat = evaluer(lignes)
    if resultat is None:
        print(f"Aucune question entièrement jugée dans {FICHIER.name} : mettez 1 ou 0 dans la colonne pertinent_loubna "
              f"({len(lignes)} lignes).")
        return 0
    print(f"Questions jugées : {resultat['questions_jugees']}/{resultat['questions_total']}")
    print(f"Précision@5 : {resultat['precision_a_5']:.3f} · MRR : {resultat['mrr']:.3f}")
    for d in resultat["detail"]:
        print(f"  Q{d['question_id']} P@5 {d['precision_a_5']:.1f} · RR {d['rr']:.2f} — {d['question'][:80]}")
    SORTIE.write_text(json.dumps(resultat, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Résultats enregistrés dans {SORTIE.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
