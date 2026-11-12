"""Étape 3 — Collecte d'un ÉCHANTILLON de 10 articles PubMed + liens avec les essais.

Lancement :
  python collecter_articles.py                 choisit 10 articles, cherche les liens, enregistre
  python collecter_articles.py --reetiqueter   recalcule seulement les étiquettes des articles
                                               déjà en mémoire (aucun appel réseau)

1. Construit les deux recherches décrites dans config/recherches_pubmed.ini ;
2. choisit 10 articles variés (types d'études différents, produits suivis,
   innovation hors liste) parmi les articles entrés récemment dans PubMed ;
3. cherche les articles associés aux essais mémorisés à l'étape 2, en séparant
   « lien confirmé », « lien possible à vérifier » et « aucun lien identifié » ;
4. enregistre chaque article UNE seule fois dans data/local/articles/ (nom = PMID),
   avec ses étiquettes rangées à part des données PubMed (partie « annexes »).

Aucune collecte massive n'est faite ici.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import requests

# Le Python du poste (installé par WAPT) ne cherche pas les modules à côté du
# script : on lui indique explicitement le dossier du projet.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from veille import etiquettes, historique  # noqa: E402
from veille.sources import pubmed as pm  # noqa: E402

RACINE = Path(__file__).resolve().parent
DOSSIER_ARTICLES = RACINE / "data" / "local" / "articles"
DOSSIER_ESSAIS = RACINE / "data" / "local" / "essais"

# Composition de l'échantillon : (description, recherche de base, filtre ajouté).
# On cherche d'abord dans les 180 derniers jours, puis sur 2 ans si rien n'est trouvé.
PLAN_ECHANTILLON = [
    ("Essai randomisé sur un produit suivi", "ciblee", "randomized controlled trial[pt]"),
    ("Essai de phase III (type déclaré par PubMed)", "large", '"clinical trial, phase iii"[pt]'),
    ("Protocole d'essai publié", "large", '"clinical trial protocol"[pt]'),
    ("Méta-analyse sur un produit suivi", "ciblee", "meta-analysis[pt]"),
    ("Recherche préclinique (indexée animaux, sans humains)", "ciblee", "animals[mh] NOT humans[mh]"),
    ("Dispositif ou chirurgie (hors études animales et vétérinaires)", "large",
     '("Glaucoma Drainage Implants"[mh] OR "minimally invasive glaucoma surgery"[tiab] OR MIGS[tiab])'
     ' NOT (animals[mh] NOT humans[mh]) NOT "Vet Ophthalmol"[ta]'),
    ("Étude observationnelle", "large", "observational study[pt]"),
    ("Molécules d'une association fixe citées ensemble", "ciblee", "netarsudil[tiab] AND latanoprost[tiab]"),
    ("Nouvelle formulation / voie d'administration", "ciblee",
     '"sustained release"[tiab] OR "sustained-release"[tiab] OR intracameral[tiab] OR "Drug Implants"[mh]'),
    ("Innovation HORS liste ciblée (trouvée par la recherche large seule)", "large_seule",
     'neuroprotect*[tiab] OR "gene therapy"[tiab]'),
]

ETATS = {"nouveau": "Nouveau", "inchange": "Déjà vu, inchangé", "modifie": "Déjà vu, MODIFIÉ"}


# ------------------------------------------------------------ collecte

def choisir_echantillon(requetes):
    choisis = {}  # PMID -> description (un article n'est pris qu'une fois)
    for description, base, filtre in PLAN_ECHANTILLON:
        if base == "large_seule":
            requete = f"{requetes['large']} AND ({filtre}) NOT ({requetes['ciblee']})"
        else:
            requete = f"{requetes[base]} AND ({filtre})"
        for jours in (180, 730):
            candidats = [p for p in pm.rechercher(requete, max_resultats=5, jours=jours) if p not in choisis]
            if candidats:
                choisis[candidats[0]] = description
                break
        else:
            print(f"  (aucun article trouvé pour : {description})")
    return choisis


def liens_essais(dossier_essais, articles_echantillon):
    """Pour chaque essai mémorisé : liens confirmés, possibles, ou aucun."""
    liens = {}
    for fichier in sorted(Path(dossier_essais).glob("NCT*.json")):
        essai = json.loads(fichier.read_text(encoding="utf-8"))["donnees"]
        nct = essai["nct"]
        confirmes, possibles = {}, {}

        # 1) Métadonnée PubMed officielle : le NCT est déclaré dans la notice (champ [si])
        for pmid in pm.rechercher(f"{nct}[si]", max_resultats=50):
            confirmes[pmid] = "NCT déclaré dans la notice PubMed (DataBankList)"
        # 2) Référence déclarée par le registre ClinicalTrials.gov
        for ref in essai.get("publications_declarees") or []:
            confirmes.setdefault(ref["pmid"], f"PMID déclaré par le registre (type : {ref['type']})")
        # 3) Numéro NCT trouvé ailleurs dans PubMed (texte) : à vérifier
        for pmid in pm.rechercher(nct, max_resultats=50):
            if pmid not in confirmes:
                possibles[pmid] = "numéro NCT présent dans le texte, pas dans la métadonnée"
        # 4) Articles de l'échantillon
        for a in articles_echantillon:
            if nct in (a.get("nct_declares") or []):
                confirmes.setdefault(a["pmid"], "NCT déclaré dans la notice PubMed (DataBankList)")
            elif nct in (a.get("nct_mentionnes_texte") or []):
                possibles.setdefault(a["pmid"], "numéro NCT cité dans le résumé seulement")

        liens[nct] = {"titre": essai["titre"], "confirmes": confirmes, "possibles": possibles}
    return liens


# ------------------------------------------------------------ affichage

def couper(texte, largeur):
    texte = texte or "Non rapporté"
    return texte if len(texte) <= largeur else texte[: largeur - 1] + "…"


def afficher_etiquettes(e, retrait="    "):
    produits = e["produits_suivis"] or []
    print(f"{retrait}Produits suivis : " + ("aucun" if not produits else ""))
    for p in produits:
        print(f"{retrait}  - {p['produit']} : {p['role']} — {p['statut_role']}")
    for m in e["molecules_hors_liste"] or []:
        print(f"{retrait}Molécule HORS liste ({m['reperage']}) : {m['molecule']}"
              f" — {m['role'] or 'non déterminé'} — {m['statut_role']}")
    if e["molecules_citees_ensemble"]:
        print(f"{retrait}Molécules d'une association fixe citées ensemble : {', '.join(e['molecules_citees_ensemble'])}")
    print(f"{retrait}Formulation / voie d'administration : {', '.join(e['formulations_voies'] or ['aucune citée'])}")
    print(f"{retrait}Stade : {e['stade']}" + (f" ({e['stade_source']})" if e["stade_source"] else ""))
    niveau = ("Oui — produit suivi étudié (rôle suggéré, à vérifier)" if e["produit_suivi_etudie_suggere"]
              else "Oui — produit suivi seulement comparateur ou cité" if e["ciblee"] else "Non")
    print(f"{retrait}Ciblé : {niveau}"
          + (" · HORS VEILLE PRINCIPALE" if e["hors_veille_principale"] else ""))


def afficher(lignes):
    colonnes = [("N°", 2), ("PMID", 8), ("Entrée PubMed", 13), ("Type(s) de publication", 42),
                ("Résumé", 6), ("Ciblé", 11), ("Stade", 14)]
    print(" | ".join(n.ljust(l) for n, l in colonnes))
    print("-+-".join("-" * l for _, l in colonnes))
    for n, (_, a, e, _) in enumerate(lignes, 1):
        valeurs = [str(n), a["pmid"], a["date_entree_pubmed"], ", ".join(a["types_publication"] or []),
                   "Oui" if a["resume_present"] else "Non",
                   "Oui, étudié?" if e["produit_suivi_etudie_suggere"] else "Oui, cité" if e["ciblee"] else "Non",
                   e["stade"]]
        print(" | ".join(couper(v, l).ljust(l) for v, (_, l) in zip(valeurs, colonnes)))

    for n, (description, a, e, etat) in enumerate(lignes, 1):
        print(f"\n[{n}] PMID {a['pmid']} — {a['titre']}")
        if description:
            print(f"    Pourquoi dans l'échantillon : {description}")
        print(f"    Lien : {a['lien']}")
        print(f"    DOI : {'https://doi.org/' + a['doi'] if a['doi'] else 'aucun DOI dans la notice'}")
        print(f"    Revue : {a['revue'] or 'Non rapportée'} · Entrée dans PubMed : {a['date_entree_pubmed']}"
              f" · Publication : {a['date_publication'] or 'Non rapportée'}")
        print(f"    Type(s) de publication : {', '.join(a['types_publication'] or ['Non rapporté'])}")
        print(f"    Résumé disponible : {'Oui' if a['resume_present'] else 'Non'}")
        afficher_etiquettes(e)
        if a["financeurs_declares"]:
            for f in a["financeurs_declares"]:
                print(f"    Financeur déclaré (PubMed) : {f['organisme'] or 'Non rapporté'}"
                      f" ({f['pays'] or 'pays non rapporté'})")
        else:
            print("    Financeur déclaré (PubMed) : aucun dans la notice (peut figurer dans le texte de l'article)")
        affs = a["affiliations_auteurs"] or []
        print(f"    Affiliations des auteurs : {len(affs)} déclarée(s)" + (" — non rapportées" if not affs else ""))
        for aff in affs[:3]:
            print(f"      - {couper(aff, 120)}")
        if len(affs) > 3:
            print(f"      - … et {len(affs) - 3} autre(s)")
        print(f"    NCT déclarés : {', '.join(a['nct_declares'] or ['aucun'])}"
              f" · NCT cités dans le texte seulement : {', '.join(a['nct_mentionnes_texte'] or ['aucun'])}")
        print(f"    Mémoire de l'outil : {ETATS[etat]}")


def afficher_liens(liens, titres, articles):
    print("\n" + "=" * 70)
    print("LIENS ENTRE LES ESSAIS MÉMORISÉS ET PUBMED")
    print("=" * 70)
    inconnus = [(a["pmid"], nct) for a in articles for nct in a["nct_declares"] or [] if nct not in liens]
    if inconnus:
        print("\nNCT déclarés par des articles, mais essais absents de notre mémoire (à collecter plus tard) :")
        for pmid, nct in inconnus:
            print(f"    PMID {pmid} → {nct} (déclaré dans la notice PubMed)")
    for nct, l in liens.items():
        print(f"\n{nct} — {couper(l['titre'], 90)}")
        if not l["confirmes"] and not l["possibles"]:
            print("    Aucun lien identifié")
        for pmid, preuve in l["confirmes"].items():
            print(f"    Lien confirmé : PMID {pmid} — {couper(titres.get(pmid), 80)}")
            print(f"        Preuve : {preuve}")
        for pmid, raison in l["possibles"].items():
            print(f"    Lien possible à vérifier : PMID {pmid} — {couper(titres.get(pmid), 80)}")
            print(f"        Raison : {raison}")


# ------------------------------------------------------------ modes

def reetiqueter(dossier, regles):
    """Recalcule les étiquettes des articles en mémoire, sans appel réseau."""
    lignes = []
    for fichier in sorted(Path(dossier).glob("*.json")):
        article = json.loads(fichier.read_text(encoding="utf-8"))["donnees"]
        e = etiquettes.etiqueter(article, regles)
        historique.annoter(dossier, article["pmid"], {"etiquettes": e})
        lignes.append((None, article, e, "inchange"))
    afficher(lignes)
    print(f"\nÉtiquettes recalculées pour {len(lignes)} article(s) — aucun appel réseau.")
    return 0


def collecter(args, regles, aujourd_hui):
    requetes = pm.construire_requetes()
    try:
        print(f"Recherche large : {pm.compter(requetes['large'])} articles au total")
        print(f"Recherche ciblée : {pm.compter(requetes['ciblee'])} articles au total (tous inclus dans la large)\n")

        choix = choisir_echantillon(requetes)
        articles = [pm.normaliser(n) for n in pm.telecharger(list(choix))]
        par_pmid = {a["pmid"]: a for a in articles}

        liens = liens_essais(args.essais, articles)
        # Articles associés aux essais mais absents de l'échantillon : on les récupère aussi
        associes = {p for l in liens.values() for p in (*l["confirmes"], *l["possibles"])} - set(par_pmid)
        articles_associes = [pm.normaliser(n) for n in pm.telecharger(sorted(associes))]
    except requests.exceptions.RequestException as erreur:
        print(f"[ERREUR] PubMed ne répond pas correctement : {erreur}")
        return 1

    lignes = []
    for pmid, description in choix.items():
        if pmid not in par_pmid:  # notice non lisible comme article (ex. chapitre de livre)
            print(f"  (PMID {pmid} ignoré : ce n'est pas un article de revue)")
            continue
        a = par_pmid[pmid]
        e = etiquettes.etiqueter(a, regles)
        etat, _ = historique.enregistrer(args.dossier, a, aujourd_hui, cle="pmid", annexes={"etiquettes": e})
        lignes.append((description, a, e, etat))
    for a in articles_associes:
        historique.enregistrer(args.dossier, a, aujourd_hui, cle="pmid",
                               annexes={"etiquettes": etiquettes.etiqueter(a, regles)})

    afficher(lignes)
    titres = {a["pmid"]: a["titre"] for a in articles + articles_associes}
    afficher_liens(liens, titres, articles)

    nb_fichiers = len(list(Path(args.dossier).glob("*.json")))
    bilan = {ETATS[e]: sum(1 for l in lignes if l[3] == e) for e in ETATS}
    print("\nBilan échantillon : " + " · ".join(f"{k} : {v}" for k, v in bilan.items()))
    print(f"Articles associés aux essais récupérés en plus : {len(articles_associes)}")
    print(f"Fichiers d'articles en mémoire : {nb_fichiers} (un fichier par PMID, donc aucun doublon possible)")
    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Échantillon de 10 articles PubMed")
    parser.add_argument("--dossier", type=Path, default=DOSSIER_ARTICLES)
    parser.add_argument("--essais", type=Path, default=DOSSIER_ESSAIS)
    parser.add_argument("--reetiqueter", action="store_true",
                        help="recalculer les étiquettes des articles en mémoire, sans appel réseau")
    args = parser.parse_args()
    aujourd_hui = time.strftime("%Y-%m-%d")
    regles = etiquettes.charger_regles()

    print(f"Échantillon PubMed — {aujourd_hui}")
    if args.reetiqueter:
        return reetiqueter(args.dossier, regles)
    return collecter(args, regles, aujourd_hui)


if __name__ == "__main__":
    sys.exit(main())
