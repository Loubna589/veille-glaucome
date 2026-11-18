"""Réponses rédigées PRÉPARÉES pour le site en ligne (GitHub Pages est statique : pas de clé dans le navigateur).

À chaque mise à jour, l'assistant RAG (veille/rag.py, mêmes règles : extraits retrouvés, citations vérifiées,
journal echanges_rag) répond aux questions de config/questions_preparees.txt avec Gemini. Seules les réponses
VALIDÉES (statut « ok » ou « je_ne_sais_pas ») sont publiées dans site/data/reponses_preparees.json.
Sans clé IA, rien n'est écrit et l'ancien fichier est conservé.
"""
import json
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent
QUESTIONS = RACINE / "config" / "questions_preparees.txt"
SORTIE = RACINE / "site" / "data" / "reponses_preparees.json"


def questions():
    return [l.strip() for l in QUESTIONS.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from veille import base, fournisseur_ia, semantique
    from veille.rag import Assistant
    if not fournisseur_ia.actif("MODELE_RAG").cle:
        print("  [SAUTÉ] Réponses préparées : pas de clé IA")
        return 0
    with base.connecter() as conn:
        semantique.construire_index(conn)
    assistant = Assistant()
    reponses = []
    for q in questions():
        s = assistant.repondre(q)
        print(f"  {s['statut']:<15} {s['duree_ms']:>6} ms · {q}")
        if s["statut"] in ("ok", "je_ne_sais_pas") and s.get("reponse"):
            reponses.append({k: s[k] for k in ("question", "reponse", "citations", "sources", "modele", "version_prompt", "statut")})
        time.sleep(4)
    if not reponses:
        print("  [PARTIELLE] Réponses préparées : aucune réponse validée, ancien fichier conservé")
        return 0
    SORTIE.write_text(json.dumps({"genere_le": time.strftime("%Y-%m-%d"), "reponses": reponses}, ensure_ascii=False),
                      encoding="utf-8")
    print(f"  [OK] Réponses préparées : {len(reponses)}/{len(questions())} publiées → {SORTIE.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
