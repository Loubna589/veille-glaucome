"""Construit eval/questions_recherche.csv : 10 questions × 5 résultats de la recherche sémantique, à juger.

Lancement :  python eval/construire_questions_recherche.py   (ne remplace pas un fichier déjà jugé)

Une ligne par (question, rang). Colonne `pertinent_loubna` VIDE : mettre 1 (pertinent) ou 0 (non pertinent).
Ensuite : python eval/evaluer_recherche.py → précision@5 et MRR.
"""
import csv
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from veille import semantique  # noqa: E402

FICHIER = RACINE / "eval" / "questions_recherche.csv"
COLONNES = ["question_id", "question", "rang", "id", "titre", "score", "lien", "pertinent_loubna"]
QUESTIONS = [
    "Quels traitements du glaucome sans conservateur font actuellement l'objet de recherches cliniques ?",
    "Efficacité du netarsudil sur la pression intraoculaire",
    "Chirurgie mini-invasive du glaucome (MIGS) : résultats et sécurité",
    "Intelligence artificielle pour dépister le glaucome sur des photos du fond d'œil",
    "Trabéculoplastie au laser sélective (SLT) en première intention",
    "Implants à libération prolongée pour traiter le glaucome",
    "Neuroprotection des cellules ganglionnaires de la rétine",
    "Glaucome congénital chez l'enfant",
    "Facteurs de risque et prévalence du glaucome dans la population",
    "Effets indésirables des collyres et surface oculaire",
]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if FICHIER.exists() and any((l.get("pertinent_loubna") or "").strip()
                                for l in csv.DictReader(FICHIER.open(encoding="utf-8-sig"), delimiter=";")):
        print(f"{FICHIER.name} contient déjà des jugements : il n'est pas remplacé.")
        return 0
    index, encodeur = semantique.Index.charger(), semantique.Encodeur()
    lignes = []
    for q_id, question in enumerate(QUESTIONS, 1):
        resultats, _ = semantique.rechercher(index, encodeur, question, k=5)
        for rang, r in enumerate(resultats, 1):
            lignes.append({"question_id": q_id, "question": question, "rang": rang, "id": r["id"],
                           "titre": r.get("titre"), "score": f"{r['score']:.4f}", "lien": r.get("lien"), "pertinent_loubna": ""})
    with FICHIER.open("w", encoding="utf-8-sig", newline="") as f:
        ecriture = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        ecriture.writeheader()
        ecriture.writerows(lignes)
    print(f"{len(QUESTIONS)} questions × 5 résultats = {len(lignes)} lignes écrites dans {FICHIER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
