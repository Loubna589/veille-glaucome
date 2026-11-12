"""Étape 4 — OpenAlex sur un petit échantillon.

Lancement :  python enrichir_openalex.py              (utilise le cache quand il existe)
             python enrichir_openalex.py --rafraichir (redemande tout à OpenAlex)

1. ENRICHIT les articles PubMed déjà en mémoire (data/local/articles/) en les
   cherchant par PMID puis, à défaut, par DOI — en UN appel groupé (1 crédit) ;
   l'apport d'OpenAlex est rangé dans la partie « annexes » de chaque article.
2. DÉCOUVRE quelques publications récentes ABSENTES de PubMed (2 recherches,
   10 crédits chacune), vérifie leur absence dans PubMed par DOI, les étiquette
   et les enregistre dans data/local/openalex/.

Chaque échec HTTP est expliqué ; la partie « découverte » peut échouer sans
empêcher l'enrichissement.
"""
import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

# Le Python du poste (installé par WAPT) ne cherche pas les modules à côté du
# script : on lui indique explicitement le dossier du projet.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from veille import etiquettes, historique  # noqa: E402
from veille.financements import justifier_financements  # noqa: E402
from veille.sources import crossref  # noqa: E402
from veille.sources import openalex as oa  # noqa: E402
from veille.sources import pubmed as pm  # noqa: E402

RACINE = Path(__file__).resolve().parent
DOSSIER_ARTICLES = RACINE / "data" / "local" / "articles"
DOSSIER_OPENALEX = RACINE / "data" / "local" / "openalex"

TYPES_INSTITUTION = {
    "education": "enseignement/recherche", "healthcare": "santé/hôpital", "company": "ENTREPRISE",
    "government": "organisme public", "nonprofit": "fondation/association", "facility": "infrastructure",
    "archive": "archive", "funder": "financeur", "other": "autre",
}
STATUTS_ACCES = {
    "gold": "libre (revue en accès ouvert)", "diamond": "libre (revue gratuite pour auteurs et lecteurs)",
    "hybrid": "libre (article ouvert dans une revue payante)", "green": "libre (copie déposée dans une archive)",
    "bronze": "lisible gratuitement sur le site de l'éditeur (sans licence ouverte)", "closed": "fermé (payant)",
}
RECHERCHE = 'glaucoma OR "ocular hypertension"'


def couper(texte, largeur):
    texte = texte or "Non rapporté"
    return texte if len(texte) <= largeur else texte[: largeur - 1] + "…"


# ------------------------------------------------------------ 1. enrichissement

def enrichir(aujourd_hui, rafraichir):
    articles = {}
    for fichier in sorted(DOSSIER_ARTICLES.glob("*.json")):
        d = json.loads(fichier.read_text(encoding="utf-8"))["donnees"]
        articles[d["pmid"]] = d
    print(f"Articles PubMed en mémoire : {len(articles)}\n")

    if rafraichir:
        oa.CACHE.mkdir(parents=True, exist_ok=True)
        for f in oa.CACHE.glob("*.json"):
            f.unlink()
    trouves = {}
    for w in oa.par_identifiants(pmids=articles):
        n = oa.normaliser(w)
        if n["pmid"] in articles:
            trouves[n["pmid"]] = (n, "PMID")
    manquants = [p for p in articles if p not in trouves and articles[p]["doi"]]
    if manquants:
        par_doi = {articles[p]["doi"].lower(): p for p in manquants}
        for w in oa.par_identifiants(dois=list(par_doi)):
            n = oa.normaliser(w)
            if n["doi"] in par_doi:
                trouves[par_doi[n["doi"]]] = (n, "DOI")

    for n, pmid in enumerate(articles, 1):
        a = articles[pmid]
        print(f"[{n}] PMID {pmid} — {couper(a['titre'], 100)}")
        if pmid not in trouves:
            print("    OpenAlex : introuvable par PMID ni par DOI — aucun enrichissement\n")
            continue
        o, par = trouves[pmid]
        apports = []

        print(f"    OpenAlex : {o['openalex_id']} (retrouvé par {par}) · {o['lien']}")
        # Financements : chaque financeur avec la notice qui le justifie (jamais mélangé aux affiliations)
        financements = justifier_financements(a, o)
        print("    FINANCEMENTS (rubrique distincte des affiliations) :" + ("" if financements else " aucun trouvé"))
        for f in financements:
            print(f"      - {f['nom']} — {f['statut']}")
            if f["references"]:
                print(f"          référence(s) de subvention : {', '.join(f['references'])}")
            for libelle, url in f["notices"]:
                print(f"          {libelle} : {url}")
            if f["note"]:
                print(f"          note : {f['note']}")
        if financements and not a["financeurs_declares"]:
            apports.append("financeur(s)")

        inst = o["institutions"] or []
        print(f"    Institutions des auteurs (OpenAlex, noms normalisés) : {len(inst)}")
        for i in inst[:5]:
            print(f"      - {i['nom']} ({i['pays'] or 'pays ?'}, {TYPES_INSTITUTION.get(i['type'], i['type'] or 'type ?')})")
        if len(inst) > 5:
            print(f"      - … et {len(inst) - 5} autre(s)")
        if inst:
            apports.append("institutions normalisées (nom officiel, pays, type)")
        if any(i["type"] == "company" for i in inst):
            apports.append("au moins un auteur affilié à une ENTREPRISE")

        print(f"    Identifiants : DOI {o['doi'] or 'aucun'} · PMCID {o['pmcid'] or 'aucun'} · OpenAlex {o['openalex_id']}")
        if o["pmcid"]:
            apports.append("PMCID (texte intégral dans PubMed Central)")
        if a["doi"] and o["doi"] and a["doi"].lower() != o["doi"]:
            print(f"    ATTENTION : DOI différent entre PubMed ({a['doi']}) et OpenAlex ({o['doi']})")

        statut = STATUTS_ACCES.get(o["statut_acces"], o["statut_acces"] or "non rapporté")
        print(f"    Accès au texte : {statut}")
        if o["acces_ouvert"]:
            print(f"      lien : {o['url_pdf'] or o['url_texte']} · licence : {o['licence'] or 'non rapportée'}")
            apports.append("lien vers le texte en accès libre")
        print(f"    Citations reçues : {o['citations']} · Rétracté : {'OUI' if o['retracte'] else 'non'}"
              f" · Sujet principal (OpenAlex) : {o['sujet_principal'] or 'non rapporté'}")
        print(f"    Apport réel par rapport à PubMed : {', '.join(apports) or 'rien de nouveau'}\n")

        # On range l'apport d'OpenAlex en annexe (le résumé est déjà dans PubMed : inutile de le dupliquer)
        historique.annoter(DOSSIER_ARTICLES, pmid, {
            "openalex": {k: v for k, v in o.items() if k != "resume"},
            "openalex_verifie_le": aujourd_hui,
            "financements": [{k: v for k, v in f.items()} for f in financements],
        })
    return articles, trouves


# ------------------------------------------------------------ 2. découverte

def decouvrir(articles, aujourd_hui, regles):
    depuis = (date.today() - timedelta(days=180)).isoformat()
    communs = ["has_pmid:false", "is_paratext:false", f"from_publication_date:{depuis}",
               f"to_publication_date:{aujourd_hui}"]
    plans = [
        ("Article de revue récent absent de PubMed", ["type:article"]),
        ("Preprint récent (pas encore évalué par des pairs)", ["type:preprint"]),
    ]
    dois_connus = {a["doi"].lower() for a in articles.values() if a["doi"]}
    trouvees = []
    for description, filtres in plans:
        print(f"Recherche : {description}")
        try:
            resultats = oa.decouvrir(RECHERCHE, communs + filtres, nombre=5)
        except (oa.ErreurOpenAlex, requests.exceptions.RequestException) as erreur:
            print(f"    [ÉCHEC] {erreur}\n")
            continue
        print(f"    {len(resultats)} résultat(s)")
        for w in resultats:
            o = oa.normaliser(w)
            if o["doi"] and o["doi"] in dois_connus:
                print(f"    - déjà en mémoire (même DOI) : {couper(o['titre'], 80)}")
                continue
            # Vérification gratuite dans PubMed : OpenAlex ne connaît pas toujours le PMID
            dans_pubmed = bool(o["doi"]) and bool(pm.rechercher(f'"{o["doi"]}"[doi]', max_resultats=1))
            trouvees.append((description, o, dans_pubmed))
        print()

    print("=" * 70)
    print("PUBLICATIONS DÉCOUVERTES PAR OPENALEX")
    print("=" * 70)
    for n, (description, o, dans_pubmed) in enumerate(trouvees, 1):
        e = etiquettes.etiqueter(o, regles)
        etat, _ = historique.enregistrer(DOSSIER_OPENALEX, o, aujourd_hui, cle="openalex_id",
                                         annexes={"etiquettes": e, "present_dans_pubmed": dans_pubmed})
        print(f"\n[{n}] {o['titre']}")
        print(f"    Recherche : {description} · Lien : {o['lien']}")
        print(f"    DOI : {o['doi'] or 'aucun'} · Type : {o['type']} · Source : {o['revue'] or 'non rapportée'}"
              f" ({o['type_source'] or 'type ?'}) · Langue : {o['langue'] or '?'} · Publication : {o['date_publication']}")
        print(f"    Absent de PubMed : {'NON — trouvé dans PubMed par son DOI' if dans_pubmed else 'oui (vérifié par DOI)' if o['doi'] else 'probable (pas de DOI pour vérifier)'}")
        print(f"    Sujet principal (OpenAlex) : {o['sujet_principal'] or 'non rapporté'} · Résumé : {'Oui' if o['resume_present'] else 'Non'}")
        print(f"    Financeur déclaré (OpenAlex) : {', '.join(f['nom'] for f in o['financeurs'] or []) or 'aucun'}")
        inst = o["institutions"] or []
        noms = ", ".join(f"{i['nom']} ({i['pays'] or '?'})" for i in inst[:3]) or "non rapportées"
        print(f"    Institutions : {noms}" + (f" … +{len(inst) - 3}" if len(inst) > 3 else ""))
        print(f"    Accès au texte : {STATUTS_ACCES.get(o['statut_acces'], o['statut_acces'] or 'non rapporté')}")
        produits = ", ".join(f"{p['produit']} ({p['role']} — {p['statut_role']})"
                             for p in e["produits_suivis"] or []) or "aucun"
        print(f"    Produits suivis : {produits}")
        for m in e["molecules_hors_liste"] or []:
            print(f"    Molécule HORS liste ({m['reperage']}) : {m['molecule']}"
                  f" — {m['role'] or 'non déterminé'} — {m['statut_role']}")
        print(f"    Stade : {e['stade']}" + (f" ({e['stade_source']})" if e["stade_source"] else ""))
        print(f"    Mémoire de l'outil : {'Nouveau' if etat == 'nouveau' else 'Déjà vu'}")
    if not trouvees:
        print("\nAucune publication découverte lors de cette exécution.")
    return trouvees


# ------------------------------------------------------------ programme

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Enrichissement et découverte OpenAlex (petit échantillon)")
    parser.add_argument("--rafraichir", action="store_true", help="ignorer le cache et tout redemander")
    parser.add_argument("--plafond", type=int, default=6, help="nombre maximal d'appels réseau (défaut : 6)")
    args = parser.parse_args()
    oa.suivi["plafond"] = args.plafond
    aujourd_hui = time.strftime("%Y-%m-%d")
    regles = etiquettes.charger_regles()

    print(f"OpenAlex — {aujourd_hui}")
    print("=" * 70)
    print("ENRICHISSEMENT DES ARTICLES PUBMED")
    print("=" * 70)
    try:
        articles, trouves = enrichir(aujourd_hui, args.rafraichir)
    except (oa.ErreurOpenAlex, requests.exceptions.RequestException) as erreur:
        print(f"[ÉCHEC] Enrichissement impossible : {erreur}")
        return 1
    decouvrir(articles, aujourd_hui, regles)

    b = oa.suivi["budget"]
    print("\n" + "=" * 70)
    print(f"Bilan : {len(trouves)}/{len(articles)} articles PubMed retrouvés dans OpenAlex")
    print(f"Appels réseau à OpenAlex : {oa.suivi['appels_reseau']} (plafond {oa.suivi['plafond']})"
          f" · réponses réutilisées depuis le cache : {oa.suivi['depuis_cache']}")
    print(f"Appels réseau à Crossref (vérification des financements, gratuit) : {crossref.suivi['appels_reseau']}"
          f" · depuis le cache : {crossref.suivi['depuis_cache']}")
    if b:
        print(f"Budget OpenAlex restant aujourd'hui : {b.get('restant')} / {b.get('limite')} crédits"
              f" (réinitialisation dans {int(b['reinitialisation_s']) // 3600 if b.get('reinitialisation_s') else '?'} h)")
    else:
        print("Budget OpenAlex : non consulté (tout venait du cache)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
