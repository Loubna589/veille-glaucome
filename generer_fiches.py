"""Étape 5 (prototype) — Génère des fiches HTML à partir de la mémoire locale.

Lancement :  python generer_fiches.py                         (les 3 fiches du prototype)
             python generer_fiches.py NCT04620135 42298273    (fiches choisies : NCT ou PMID)

Aucun appel réseau : tout vient de data/local/ (essais, articles, annexes OpenAlex/Crossref).
Les fiches sont écrites dans data/local/fiches/ et s'ouvrent par double-clic.
"""
import json
import sys
import time
from pathlib import Path

# Le Python du poste (installé par WAPT) ne cherche pas les modules à côté du
# script : on lui indique explicitement le dossier du projet.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from veille import etiquettes, fiches, rubriques  # noqa: E402

RACINE = Path(__file__).resolve().parent
ESSAIS = RACINE / "data" / "local" / "essais"
ARTICLES = RACINE / "data" / "local" / "articles"
SORTIE = RACINE / "data" / "local" / "fiches"
PROTOTYPE = ["NCT07075718", "NCT04620135", "42298273"]  # essai sans résultats, essai avec résultats, article


def lire(dossier):
    return {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in sorted(Path(dossier).glob("*.json"))}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    identifiants = sys.argv[1:] or PROTOTYPE
    essais, articles = lire(ESSAIS), lire(ARTICLES)
    regles_rub = rubriques.charger()
    regles_et = etiquettes.charger_regles()
    genere_le = time.strftime("%Y-%m-%d %H:%M")
    SORTIE.mkdir(parents=True, exist_ok=True)

    for ident in identifiants:
        if ident in essais:
            m = essais[ident]
            rub = rubriques.classer_essai(m["donnees"], regles_rub)
            entete, blocs, manquants = fiches.fiche_essai(m, list(articles.values()), rub)
            texte = fiches.texte_copie_essai(m)
            onglet = f"{ident} — fiche essai"
        elif ident in articles:
            m = articles[ident]
            # Étiquettes recalculées à la volée si elles manquent (article jamais ré-étiqueté)
            m.setdefault("annexes", {}).setdefault("etiquettes", etiquettes.etiqueter(m["donnees"], regles_et))
            rub = rubriques.classer_publication(m["donnees"], m["annexes"]["etiquettes"], regles_rub)
            entete, blocs, manquants = fiches.fiche_article(m, [x["donnees"] for x in essais.values()], rub)
            texte = fiches.texte_copie_article(m)
            onglet = f"PMID {ident} — fiche article"
        else:
            print(f"[ERREUR] {ident} : ni essai ni article dans la mémoire locale")
            continue
        fichier = SORTIE / f"{ident}.html"
        fichier.write_text(fiches.page(onglet, entete, blocs, manquants, texte, genere_le), encoding="utf-8")
        print(f"[OK] {fichier}")
        print(f"     rubrique : {', '.join(r['nom'] for r in rub)} · informations manquantes : {len(manquants)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
