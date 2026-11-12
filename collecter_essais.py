"""Étape 2 — Collecte d'un ÉCHANTILLON d'essais ClinicalTrials.gov.

Lancement :  python collecter_essais.py

Le programme récupère 10 essais variés (différentes phases déclarées, un essai
« non applicable », une étude observationnelle, un essai avec résultats déposés),
les enregistre dans data/local/essais/ (dossier de test, ignoré par Git) et
affiche un tableau. À la deuxième exécution, il reconnaît les essais déjà vus
et signale ceux qui ont changé.

Option :  --dossier CHEMIN   pour enregistrer ailleurs (utile pour les tests)

La collecte complète de l'historique n'est PAS faite ici (étape suivante).
"""
import argparse
import sys
import time
from pathlib import Path

import requests

# Le Python du poste (installé par WAPT) ne cherche pas les modules à côté du
# script : on lui indique explicitement le dossier du projet.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from veille import historique  # noqa: E402
from veille.sources import clinicaltrials as ct

# Composition de l'échantillon : (description, filtre de l'API, nombre d'essais)
# Les filtres portent sur ce que la SOURCE déclare ; on ne déduit aucune phase.
PLAN_ECHANTILLON = [
    ("Phase précoce 1 déclarée", "AREA[Phase]EARLY_PHASE1", 1),
    ("Phase 1 déclarée", "AREA[Phase]PHASE1", 1),
    ("Phase 2 déclarée", "AREA[Phase]PHASE2", 1),
    ("Phase 3 déclarée", "AREA[Phase]PHASE3", 2),
    ("Phase 4 déclarée", "AREA[Phase]PHASE4", 1),
    ("Phase « non applicable » déclarée", "AREA[Phase]NA", 2),
    ("Étude observationnelle", "AREA[StudyType]OBSERVATIONAL", 1),
    ("Résultats déposés au registre", "AREA[HasResults]true", 1),
]
DOSSIER_TEST = Path(__file__).parent / "data" / "local" / "essais"

ETATS = {
    "nouveau": "Nouveau",
    "inchange": "Déjà vu, inchangé",
    "modifie": "Déjà vu, MODIFIÉ",
    "resultats_ajoutes": "Déjà vu, RÉSULTATS AJOUTÉS",
}


def construire_echantillon():
    """Récupère les essais du plan en évitant de prendre deux fois le même."""
    choisis = {}
    for description, filtre, nombre in PLAN_ECHANTILLON:
        # On demande quelques essais de plus pour pouvoir sauter les doublons
        candidats = ct.rechercher(filtre=filtre, max_resultats=nombre + 5)
        pris = 0
        for brut in candidats:
            essai = ct.normaliser(brut)
            if essai["nct"] in choisis:
                continue
            choisis[essai["nct"]] = (description, essai)
            pris += 1
            if pris == nombre:
                break
    return list(choisis.values())


def couper(texte, largeur):
    texte = texte or "Non rapporté"
    return texte if len(texte) <= largeur else texte[: largeur - 1] + "…"


def afficher_tableau(lignes):
    colonnes = [("N°", 2), ("NCT", 11), ("Phase déclarée", 24), ("Type", 17), ("Statut", 26),
                ("Participants", 14), ("Résultats", 9), ("Promoteur", 28)]
    print(" | ".join(nom.ljust(l) for nom, l in colonnes))
    print("-+-".join("-" * l for _, l in colonnes))
    for n, (_, essai, _, _) in enumerate(lignes, 1):
        valeurs = [
            str(n), essai["nct"], ct.libelle_phase(essai), ct.libelle_type_etude(essai),
            ct.libelle_statut(essai), ct.libelle_participants(essai),
            "Oui" if essai["resultats_deposes"] else "Non", essai["promoteur"],
        ]
        print(" | ".join(couper(v, l).ljust(l) for v, (_, l) in zip(valeurs, colonnes)))


def afficher_details(lignes):
    for n, (description, essai, etat, changements) in enumerate(lignes, 1):
        print(f"\n[{n}] {essai['nct']} — {essai['titre'] or 'Titre non rapporté'}")
        print(f"    Pourquoi dans l'échantillon : {description}")
        print(f"    Lien : {essai['lien']}")
        print(f"    Conditions déclarées : {', '.join(essai['conditions'] or ['Non rapporté'])}")
        print(f"    Première publication : {essai['date_premiere_publication'] or 'Non rapportée'}"
              f" · Dernière mise à jour : {essai['date_derniere_mise_a_jour'] or 'Non rapportée'}")
        print(f"    Promoteur : {essai['promoteur'] or 'Non rapporté'}"
              f" ({essai['type_promoteur'] or 'catégorie non rapportée'})")
        if essai["raison_arret"]:
            print(f"    Raison d'arrêt déclarée : {essai['raison_arret']}")
        print("    Interventions :")
        for ligne in ct.libelle_interventions(essai):
            print(f"      - {ligne}")
        print("    Critère(s) principal(aux) :")
        for c in essai["criteres_principaux"] or [{"critere": "Non rapporté", "delai": None}]:
            delai = f" [{c['delai']}]" if c.get("delai") else ""
            print(f"      - {couper(c['critere'], 110)}{delai}")
        print(f"    Résultats déposés au registre : {ct.libelle_resultats(essai)}")
        print(f"    Mémoire de l'outil : {ETATS[etat]}")
        for champ, valeurs in changements.items():
            print(f"      · {champ} : {couper(str(valeurs['avant']), 50)} → {couper(str(valeurs['apres']), 50)}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Collecte d'un échantillon d'essais ClinicalTrials.gov")
    parser.add_argument("--dossier", type=Path, default=DOSSIER_TEST,
                        help="dossier où mémoriser les essais (défaut : data/local/essais)")
    parser.add_argument("--nct", nargs="+", default=[],
                        help="ajouter des essais précis à la mémoire (ex. --nct NCT04620135)")
    parser.add_argument("--actualiser", action="store_true",
                        help="relire depuis le registre tous les essais déjà en mémoire (un seul appel)")
    args = parser.parse_args()

    aujourd_hui = time.strftime("%Y-%m-%d")
    print(f"Collecte ClinicalTrials.gov — {aujourd_hui}")
    print(f"Mémoire : {args.dossier}\n")

    try:
        if args.nct or args.actualiser:
            en_memoire = [f.stem for f in Path(args.dossier).glob("NCT*.json")] if args.actualiser else []
            bruts = ct.par_nct(sorted(set(args.nct) | set(en_memoire)))
            echantillon = [("Ajouté à la demande" if e["nct"] in args.nct else "Actualisation de la mémoire", e)
                           for e in map(ct.normaliser, bruts)]
        else:
            echantillon = construire_echantillon()
    except requests.exceptions.RequestException as erreur:
        print(f"[ERREUR] ClinicalTrials.gov ne répond pas correctement : {erreur}")
        return 1

    lignes = []
    for description, essai in echantillon:
        etat, changements = historique.enregistrer(args.dossier, essai, aujourd_hui, cle="nct")
        lignes.append((description, essai, etat, changements))

    afficher_tableau(lignes)
    afficher_details(lignes)

    bilan = {ETATS[e]: sum(1 for l in lignes if l[2] == e) for e in ETATS}
    print("\nBilan : " + " · ".join(f"{nom} : {n}" for nom, n in bilan.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
