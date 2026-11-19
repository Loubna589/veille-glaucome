"""Vérifie chaque jour auprès de PubMed si un article déjà collecté a été rétracté ou corrigé (erratum).

Lancement :  python verifier_retractations.py   (puis python construire_site.py pour mettre à jour les fiches)
Détails : veille/retractations.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from veille import base, retractations  # noqa: E402


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    b = retractations.verifier(base.connecter())
    print(f"  Rétractations / erratums : {b['verifies']} articles vérifiés, {b['mis_a_jour']} fiches mises à jour, "
          f"{len(b['retractes'])} rétracté(s) {b['retractes']}, {len(b['erratums'])} erratum(s) {b['erratums']}")


if __name__ == "__main__":
    main()
