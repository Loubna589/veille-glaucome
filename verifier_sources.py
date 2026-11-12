"""Étape 1 — Vérifie que les trois sources de la veille sont accessibles.

Lancement :  python verifier_sources.py

Pour chaque source, le programme fait une petite recherche réelle sur le
glaucome et affiche [OK] ou [ERREUR] avec l'explication.
Code de sortie : 0 si les trois sources répondent, 1 sinon
(utile plus tard pour GitHub Actions).
"""
import os
import sys
import time
from pathlib import Path

import requests

DELAI_MAX = 30  # secondes avant d'abandonner une requête


def charger_env(chemin=Path(__file__).with_name(".env")):
    """Lit le fichier .env (facultatif) sans bibliothèque supplémentaire.

    Les variables déjà définies (par exemple les secrets GitHub) sont prioritaires.
    """
    if not chemin.exists():
        return
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        valeur = valeur.strip().strip('"').strip("'")
        if valeur:
            os.environ.setdefault(cle.strip(), valeur)


def appeler(url, params):
    """Envoie une requête GET et renvoie (réponse JSON, durée en secondes)."""
    contact = os.getenv("CONTACT_EMAIL")
    agent = "veille-glaucome/0.1" + (f" (mailto:{contact})" if contact else "")
    debut = time.perf_counter()
    reponse = requests.get(url, params=params, headers={"User-Agent": agent}, timeout=DELAI_MAX)
    reponse.raise_for_status()
    return reponse.json(), time.perf_counter() - debut


# ---------------------------------------------------------------- les 3 tests

def verifier_clinicaltrials():
    donnees, duree = appeler(
        "https://clinicaltrials.gov/api/v2/studies",
        {
            "query.cond": 'glaucoma OR "ocular hypertension"',
            "countTotal": "true",
            "pageSize": 1,
            "sort": "LastUpdatePostDate:desc",
            "fields": "NCTId,BriefTitle,LastUpdatePostDate",
        },
    )
    etude = donnees["studies"][0]["protocolSection"]
    ident = etude["identificationModule"]
    maj = etude.get("statusModule", {}).get("lastUpdatePostDateStruct", {}).get("date", "non rapportée")
    return [
        f"{donnees['totalCount']} essais trouvés (réponse en {duree:.1f} s)",
        f"Dernier essai mis à jour : {ident['nctId']} ({maj})",
        f"  « {ident['briefTitle']} »",
        f"  https://clinicaltrials.gov/study/{ident['nctId']}",
    ]


def verifier_pubmed():
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    communs = {"db": "pubmed", "retmode": "json", "tool": "veille-glaucome"}
    if os.getenv("CONTACT_EMAIL"):
        communs["email"] = os.getenv("CONTACT_EMAIL")
    if os.getenv("NCBI_API_KEY"):
        communs["api_key"] = os.getenv("NCBI_API_KEY")

    # 1) recherche : combien d'articles, et le plus récent
    recherche, duree = appeler(f"{base}/esearch.fcgi", {
        **communs,
        "term": 'glaucoma[mh] OR "ocular hypertension"[mh] OR glaucoma[tiab] OR "ocular hypertension"[tiab]',
        "sort": "pub_date",
        "retmax": 1,
    })
    resultat = recherche["esearchresult"]
    pmid = resultat["idlist"][0]

    # 2) détail de cet article (vérifie un deuxième service de PubMed)
    resume, _ = appeler(f"{base}/esummary.fcgi", {**communs, "id": pmid})
    article = resume["result"][pmid]
    return [
        f"{int(resultat['count'])} articles trouvés (réponse en {duree:.1f} s)",
        f"Article le plus récent : PMID {pmid} ({article.get('pubdate') or 'date non rapportée'})",
        f"  « {article.get('title', 'titre non rapporté')} »",
        f"  https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    ]


def verifier_openalex():
    aujourd_hui = time.strftime("%Y-%m-%d")
    params = {
        # Guillemets obligatoires autour de l'expression, sinon chaque mot est cherché
        # séparément ; on exclut aussi les dates de publication dans le futur.
        "filter": f'title_and_abstract.search:glaucoma OR "ocular hypertension",'
                  f"to_publication_date:{aujourd_hui}",
        "sort": "publication_date:desc",
        "per-page": 1,
        "select": "id,display_name,publication_date,doi",
    }
    if os.getenv("CONTACT_EMAIL"):
        params["mailto"] = os.getenv("CONTACT_EMAIL")
    if os.getenv("OPENALEX_API_KEY"):
        params["api_key"] = os.getenv("OPENALEX_API_KEY")

    donnees, duree = appeler("https://api.openalex.org/works", params)
    travail = donnees["results"][0]
    lignes = [
        f"{donnees['meta']['count']} publications trouvées (réponse en {duree:.1f} s)",
        f"Publication la plus récente : {travail['id'].rsplit('/', 1)[-1]} ({travail.get('publication_date') or 'date non rapportée'})",
        f"  « {travail.get('display_name') or 'titre non rapporté'} »",
        f"  {travail.get('doi') or travail['id']}",
    ]
    if "cost_usd" in donnees["meta"]:
        lignes.append(f"Note : OpenAlex indique un coût de {donnees['meta']['cost_usd']} $ par requête "
                      "(décompté d'un quota ; à surveiller quand la collecte grossira).")
    return lignes


# ---------------------------------------------------------------- programme

def expliquer_erreur(erreur):
    """Traduit les erreurs techniques les plus courantes en français simple."""
    if isinstance(erreur, requests.exceptions.Timeout):
        return f"pas de réponse après {DELAI_MAX} s (service lent ou connexion coupée)"
    if isinstance(erreur, requests.exceptions.ConnectionError):
        return "connexion impossible (pas d'Internet, pare-feu ou proxy de l'entreprise ?)"
    if isinstance(erreur, requests.exceptions.HTTPError):
        code = erreur.response.status_code
        indices = {403: "accès refusé", 429: "trop de requêtes, réessayer plus tard",
                   400: "requête mal formée"}
        return f"le service a répondu avec le code HTTP {code} ({indices.get(code, 'erreur du service')})"
    if isinstance(erreur, (KeyError, IndexError, ValueError)):
        return f"réponse inattendue du service, son format a peut-être changé ({erreur!r})"
    return repr(erreur)


def main():
    # Affichage correct des accents dans le terminal Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    charger_env()

    verifications = [
        ("ClinicalTrials.gov", verifier_clinicaltrials),
        ("PubMed", verifier_pubmed),
        ("OpenAlex", verifier_openalex),
    ]
    print("Vérification de l'accès aux sources de la veille glaucome")
    print("=" * 60)
    reussites = 0
    for nom, verifier in verifications:
        try:
            lignes = verifier()
        except Exception as erreur:  # on veut tester les 3 sources même si l'une échoue
            print(f"\n[ERREUR] {nom} : {expliquer_erreur(erreur)}")
            continue
        reussites += 1
        print(f"\n[OK] {nom}")
        for ligne in lignes:
            print(f"     {ligne}")

    print("\n" + "=" * 60)
    print(f"Bilan : {reussites}/{len(verifications)} sources accessibles")
    return 0 if reussites == len(verifications) else 1


if __name__ == "__main__":
    sys.exit(main())
