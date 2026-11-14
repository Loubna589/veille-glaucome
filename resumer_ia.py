"""Étape IA du pipeline : résumé + classification traçables (GitHub Models), puis reconstruction du site.

Lancement :  python resumer_ia.py
Nécessite MISTRAL_API_KEY ou GEMINI_API_KEY (.env en local, Secrets du dépôt en ligne).
Sans jeton, l'étape est sautée sans erreur (et notée « saute » dans le journal des exécutions).
Détails : veille/resumer_ia.py · prompts versionnés : config/prompts/.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import construire_site  # noqa: E402
from veille import base, resumer_ia  # noqa: E402


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    conn = base.connecter()
    debut = base.maintenant()
    bilan = resumer_ia.traiter(conn)
    statut = "saute" if bilan["saute"] else ("partielle" if bilan["erreur"] else "ok")
    conn.execute("INSERT INTO executions (execution_id, source, debut, fin, statut, nb_elements, erreurs) "
                 "VALUES (?, 'github_models', ?, ?, ?, ?, ?)",
                 (base.lire_meta(conn, "dernier_bilan", {}).get("execution") or "ia", debut, base.maintenant(), statut,
                  bilan["traites"], bilan["erreur"]))
    conn.commit()
    if bilan["saute"]:
        print("  [SAUTÉ] IA : pas de clé MISTRAL_API_KEY ni GEMINI_API_KEY")
        return 0
    print(f"  [{statut.upper()}] IA ({resumer_ia.fournisseur().nom} {resumer_ia.fournisseur().modele}, prompt {resumer_ia.VERSION_PROMPT}) : "
          f"{bilan['traites']} traité(s), {bilan['invalides']} sortie(s) invalide(s) rejetée(s), "
          f"{bilan['restants']} restant(s)" + (f" — {bilan['erreur']}" if bilan["erreur"] else ""))
    if bilan["traites"]:
        construire_site.main(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
