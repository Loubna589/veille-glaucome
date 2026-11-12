"""Construit le jeu d'évaluation de la classification : eval/jeu_etiquete.csv (30 publications variées).

Lancement :  python eval/construire_jeu.py      (ne remplace pas un fichier déjà étiqueté)

Colonnes :
- id, titre, extrait (début du résumé), lien : pour juger ;
- etiquette_proposee : proposition AUTOMATIQUE par les règles de l'outil (config/rubriques.ini,
  ramenées aux 6 catégories fermées de l'IA) — c'est un point de départ, pas une vérité ;
- etiquette_loubna : VIDE, à remplir à la main avec l'une des 6 catégories (vérité terrain).

Sélection : jusqu'à 5 publications par catégorie proposée (ordre déterministe), complétées
pour atteindre 30, afin d'avoir un jeu varié et pas seulement des articles « médicaments ».
"""
import csv
import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from veille import base, etiquettes, resumer_ia, rubriques  # noqa: E402

FICHIER = RACINE / "eval" / "jeu_etiquete.csv"
COLONNES = ["id", "titre", "extrait", "lien", "etiquette_proposee", "etiquette_loubna"]
TAILLE = 30
DISPOSITIF = re.compile(r"\b(stent|shunt|valve|implant|device|tube|drainage)", re.I)
EPIDEMIO = re.compile(r"\b(prevalence|incidence|risk factors?|cohort|population|epidemiolog|burden|nationwide)", re.I)


def proposer(donnees, annexes, regles_rub, regles_et):
    """Règles de l'outil → une des 6 catégories fermées."""
    et = annexes.get("etiquettes") or etiquettes.etiqueter(donnees, regles_et)
    rubrique = rubriques.classer_publication(donnees, et, regles_rub)[0]["nom"]
    titre = donnees.get("titre") or ""
    if rubrique == "Médicaments":
        return "traitement_medicamenteux"
    if rubrique == "Dispositifs et chirurgie":
        return "dispositif" if DISPOSITIF.search(titre) else "chirurgie_laser"
    if rubrique == "Diagnostic et IA":
        return "diagnostic_imagerie"
    if EPIDEMIO.search(titre):
        return "epidemiologie"
    return "autre"


def construire(conn):
    regles_rub, regles_et = rubriques.charger(), etiquettes.charger_regles()
    par_categorie = {c: [] for c in resumer_ia.CATEGORIES}
    for a in conn.execute("SELECT pmid, donnees, annexes FROM articles WHERE origine = 'pubmed' ORDER BY pmid"):
        d, ann = json.loads(a["donnees"]), json.loads(a["annexes"])
        if not d.get("resume") or (ann.get("etiquettes") or {}).get("veterinaire"):
            continue
        par_categorie[proposer(d, ann, regles_rub, regles_et)].append((a["pmid"], d))
    choisis = [x for liste in par_categorie.values() for x in liste[:5]]   # jusqu'à 5 par catégorie
    reste = [x for liste in par_categorie.values() for x in liste[5:]]
    choisis += reste[:max(0, TAILLE - len(choisis))]                       # complément jusqu'à 30
    lignes = []
    for pmid, d in choisis[:TAILLE]:
        lignes.append({"id": pmid, "titre": d.get("titre"), "extrait": " ".join((d.get("resume") or "").split())[:350],
                       "lien": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                       "etiquette_proposee": proposer(d, {}, regles_rub, regles_et), "etiquette_loubna": ""})
    return lignes


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if FICHIER.exists() and any(l.get("etiquette_loubna") for l in csv.DictReader(FICHIER.open(encoding="utf-8-sig"))):
        print(f"{FICHIER.name} contient déjà des étiquettes : il n'est pas remplacé.")
        return 0
    lignes = construire(base.connecter())
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    with FICHIER.open("w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig : s'ouvre bien dans Excel
        ecriture = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        ecriture.writeheader()
        ecriture.writerows(lignes)
    repartition = {}
    for l in lignes:
        repartition[l["etiquette_proposee"]] = repartition.get(l["etiquette_proposee"], 0) + 1
    print(f"{len(lignes)} publications écrites dans {FICHIER} — répartition proposée : {repartition}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
