"""Recherche sémantique en ligne de commande.

    python chercher.py "traitements sans conservateur"          → 5 meilleurs résultats avec leur score
    python chercher.py "laser trabeculoplasty outcomes" -k 10
    python chercher.py --reconstruire                           → recalcule les embeddings manquants et l'index

La question peut être en français ou en anglais (modèle multilingue).
Score = similarité cosinus entre la question et le document (1 = identique, 0 = sans rapport).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from veille import base, semantique  # noqa: E402


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Recherche sémantique dans la veille glaucome")
    parser.add_argument("question", nargs="?", help="question en langage naturel")
    parser.add_argument("-k", type=int, default=5, help="nombre de résultats (5 par défaut)")
    parser.add_argument("--reconstruire", action="store_true", help="recalcule les embeddings et l'index")
    args = parser.parse_args()

    if args.reconstruire or not (semantique.DOSSIER_INDEX / "vecteurs.npy").exists():
        conn = base.connecter()
        n = semantique.mettre_a_jour(conn)
        index = semantique.construire_index(conn)
        print(f"Index construit : {len(index.ids)} documents ({n} encodé(s) maintenant), moteur {index.moteur}")
    if not args.question:
        return 0
    index = semantique.Index.charger()
    encodeur = semantique.Encodeur()
    resultats, etendue = semantique.rechercher(index, encodeur, args.question, k=args.k)
    print(f"\nQuestion : {args.question}")
    if etendue != args.question:
        print(f"Question encodée (glossaire FR→EN) : {etendue}")
    print(f"Index : {len(index.ids)} documents · modèle {semantique.MODELE} · moteur {index.moteur}")
    print(f"Score = cosinus + {semantique.POIDS_LEXICAL} × part des termes du glossaire trouvés\n")
    for rang, r in enumerate(resultats, 1):
        print(f"{rang}. [{r['score']:.3f} = {r['score_dense']:.3f} + {semantique.POIDS_LEXICAL}×{r['score_lexical']:.2f}] "
              f"{r['id']} ({r['type']}) — {(r['titre'] or '')[:100]}")
        if r.get("lien"):
            print(f"   {r['lien']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
