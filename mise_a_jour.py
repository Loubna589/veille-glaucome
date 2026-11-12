"""Pipeline QUOTIDIEN de la veille : collecte → SQLite → export JSON contrôlé → site.

Lancement :  python mise_a_jour.py

Étapes (chacune journalisée dans la table `executions` ; une source en panne n'arrête pas les autres) :
1. ClinicalTrials.gov : essais créés ou mis à jour depuis la dernière exécution
   → nouvelle version + événements (nouveau, statut, recrutement, date de fin, phase, résultats) ;
2. PubMed : articles entrés depuis la dernière exécution (dédupliqués par PMID / DOI) ;
3. OpenAlex + Crossref : enrichissement des nouveaux articles et justification des financeurs ;
4. OpenAlex : publications récentes ABSENTES de PubMed (dédupliquées par DOI / OpenAlex) ;
5. Accès au marché : BDPM, EMA, openFDA (data/historique/marche.json) ;
6. export JSON contrôlé + reconstruction du site (construire_site.py) ;
7. alertes : nouveaux événements → site/alertes.html + alertes.md (jamais deux fois le même).

Statut global de l'exécution : « ok », « partielle » (au moins une source en échec) ou « echec ».
Les résumés IA sont une étape séparée (resumer_ia.py), lancée par GitHub Actions.
"""
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import collecter_marche  # noqa: E402
import construire_site  # noqa: E402
from veille import alertes, base, etiquettes, reseau  # noqa: E402
from veille.financements import justifier_financements  # noqa: E402
from veille.sources import clinicaltrials as ct  # noqa: E402
from veille.sources import openalex as oa  # noqa: E402
from veille.sources import pubmed as pm  # noqa: E402

MAX_ESSAIS = 300     # garde-fous : au-delà, on s'arrête et on le signale
MAX_ARTICLES = 300
RECHERCHE_OPENALEX = 'glaucoma OR "ocular hypertension"'


def maj_essais(conn, ex, depuis, jour, bilan):
    bruts = ct.rechercher(filtre=f"AREA[LastUpdatePostDate]RANGE[{depuis},MAX]", max_resultats=MAX_ESSAIS)
    if len(bruts) >= MAX_ESSAIS:
        bilan["alertes"].append(f"ClinicalTrials.gov : plafond de {MAX_ESSAIS} essais atteint, relancer")
    for brut in bruts:
        etat, _, n = base.enregistrer_essai(conn, ct.normaliser(brut), jour, ex.id)
        bilan["essais"][etat] = bilan["essais"].get(etat, 0) + 1
        bilan["evenements"] += n
    conn.commit()
    return len(bruts)


def maj_articles(conn, ex, depuis, jour, regles, bilan, nouveaux):
    requetes = pm.construire_requetes()
    jours = (date.today() - date.fromisoformat(depuis)).days + 1
    pmids = pm.rechercher(requetes["large"], max_resultats=MAX_ARTICLES, tri="pub_date", jours=jours)
    if len(pmids) >= MAX_ARTICLES:
        bilan["alertes"].append(f"PubMed : plafond de {MAX_ARTICLES} articles atteint, relancer")
    inconnus = [p for p in pmids if not base.trouver_article(conn, pmid=p)]
    for i in range(0, len(inconnus), 100):
        for notice in pm.telecharger(inconnus[i:i + 100]):
            a = pm.normaliser(notice)
            etat, _ = base.enregistrer_article(conn, a, jour, "pubmed", "pubmed",
                                               {"etiquettes": etiquettes.etiqueter(a, regles)}, ex.id)
            if etat == "nouveau":
                nouveaux.append(a)
    conn.commit()
    bilan["articles_nouveaux"] = len(nouveaux)
    return len(nouveaux)


def enrichir(conn, jour, bilan, nouveaux):
    """Enrichit les nouveaux articles ET ceux des 30 derniers jours qu'OpenAlex ne connaissait pas encore."""
    limite = (date.today() - timedelta(days=30)).isoformat()
    par_pmid = {a["pmid"]: a for a in nouveaux}
    for ligne in conn.execute("SELECT donnees, annexes FROM articles WHERE origine = 'pubmed' AND premiere_detection >= ?",
                              (limite,)):
        if "openalex" not in json.loads(ligne["annexes"]):
            d = json.loads(ligne["donnees"])
            par_pmid.setdefault(d["pmid"], d)
    if not par_pmid:
        return 0
    for w in oa.par_identifiants(pmids=list(par_pmid)):
        o = oa.normaliser(w)
        a = par_pmid.get(o["pmid"])
        if a:
            base.annoter_article(conn, a["pmid"], {"openalex": {k: v for k, v in o.items() if k != "resume"},
                                                   "openalex_verifie_le": jour,
                                                   "financements": justifier_financements(a, o)}, jour)
            bilan["articles_enrichis"] += 1
    conn.commit()
    return bilan["articles_enrichis"]


def decouvrir(conn, ex, depuis, jour, regles, bilan):
    debut = (date.fromisoformat(depuis) - timedelta(days=30)).isoformat()
    communs = ["has_pmid:false", "is_paratext:false", f"from_publication_date:{debut}", f"to_publication_date:{jour}"]
    erreurs = []
    for filtres in (["type:article"], ["type:preprint"]):
        try:
            resultats = oa.decouvrir(RECHERCHE_OPENALEX, communs + filtres, nombre=10)
        except (oa.ErreurOpenAlex, reseau.ErreurSource) as erreur:
            erreurs.append(f"{filtres[0]} : {erreur}")
            continue
        for w in resultats:
            o = oa.normaliser(w)
            if base.trouver_article(conn, doi=o["doi"], openalex_id=o["openalex_id"]):
                continue  # déjà connu (même DOI ou même identifiant OpenAlex) : déduplication
            if o["doi"] and pm.rechercher(f'"{o["doi"]}"[doi]', max_resultats=1):
                continue  # présent dans PubMed : il sera collecté par la recherche PubMed
            etat, _ = base.enregistrer_article(conn, o, jour, "openalex", "openalex",
                                               {"etiquettes": etiquettes.etiqueter(o, regles), "present_dans_pubmed": False},
                                               ex.id)
            bilan["decouvertes_openalex"] += etat == "nouveau"
    conn.commit()
    if erreurs and len(erreurs) == 2:
        raise oa.ErreurOpenAlex(" ; ".join(erreurs))  # les deux recherches ont échoué : étape en échec
    bilan["alertes"] += [f"OpenAlex (découverte) {e}" for e in erreurs]
    return bilan["decouvertes_openalex"]


def marche(source, module):
    """Une source d'accès au marché (BDPM, EMA ou openFDA), journalisée séparément."""
    try:
        donnees, info = module.collecter(collecter_marche.mc.charger_molecules())
    except Exception as erreur:
        if getattr(erreur, "saute", False):  # clé facultative absente : on l'indique sur la page, sans panne
            collecter_marche.noter_saute(source, source, erreur)
        raise
    collecter_marche.enregistrer_source(source, donnees, info)
    return sum(len(v) for v in donnees.values())


def embeddings(conn):
    """Embeddings des documents nouveaux ou modifiés (modèle local), puis reconstruction de l'index."""
    from veille import semantique
    n = semantique.mettre_a_jour(conn)
    semantique.construire_index(conn)
    return n


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:  # clés facultatives (OPENALEX_API_KEY, PBS_API_KEY…) depuis .env en local ; secrets GitHub en ligne
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent / ".env")
    except ImportError:
        pass
    log = reseau.journal()
    conn = base.connecter()
    ex = base.Execution(conn)
    jour = time.strftime("%Y-%m-%d")
    depuis = base.lire_meta(conn, "derniere_execution") or (date.today() - timedelta(days=2)).isoformat()
    regles = etiquettes.charger_regles()
    bilan = {"date": jour, "depuis": depuis, "execution": ex.id, "essais": {}, "articles_nouveaux": 0,
             "articles_enrichis": 0, "decouvertes_openalex": 0, "evenements": 0, "alertes": [], "sources_en_echec": []}
    print(f"Mise à jour de la veille — {jour} (nouveautés depuis le {depuis}) — exécution {ex.id}")
    log.info("=== Exécution %s : nouveautés depuis le %s ===", ex.id, depuis)

    nouveaux = []
    from veille.sources import bdpm, canada, ema, espagne, italie, openfda, pbs, suisse
    etapes = [
        ("clinicaltrials", lambda: maj_essais(conn, ex, depuis, jour, bilan)),
        ("pubmed", lambda: maj_articles(conn, ex, depuis, jour, regles, bilan, nouveaux)),
        ("openalex_enrichissement", lambda: enrichir(conn, jour, bilan, nouveaux)),
        ("openalex_decouverte", lambda: decouvrir(conn, ex, depuis, jour, regles, bilan)),
        ("bdpm", lambda: marche("france", bdpm)),
        ("ema", lambda: marche("ue", ema)),
        ("openfda", lambda: marche("usa", openfda)),
        ("canada_dpd", lambda: marche("canada", canada)),
        ("espagne_cima", lambda: marche("espagne", espagne)),
        ("italie_aifa", lambda: marche("italie", italie)),
        ("suisse_swissmedic", lambda: marche("suisse", suisse)),
        ("australie_pbs", lambda: marche("australie", pbs)),   # sautée proprement sans PBS_API_KEY
        ("embeddings", lambda: embeddings(conn)),
    ]
    for nom, etape in etapes:
        statut, erreur = ex.etape(nom, etape)
        if statut == "echec":
            conn.rollback()
            bilan["sources_en_echec"].append(nom)
            print(f"  [ÉCHEC] {nom} : {erreur}")
            log.error("Étape %s en échec : %s", nom, erreur)
        elif statut == "saute":
            print(f"  [SAUTÉ] {nom} : {erreur.split(': ', 1)[-1]}")
        else:
            print(f"  [OK] {nom} ({ex.etapes[-1]['nb']} élément(s))")
    bilan["appels_openalex"] = oa.suivi["appels_reseau"]
    bilan["statut"] = ex.terminer()

    # La date de reprise n'avance que si les sources principales ont répondu
    if not {"clinicaltrials", "pubmed"} & set(bilan["sources_en_echec"]):
        base.ecrire_meta(conn, "derniere_execution", jour)
    base.ecrire_meta(conn, "dernier_bilan", bilan)
    conn.commit()

    e = bilan["essais"]
    print(f"Essais : {e.get('nouveau', 0)} nouveau(x), {e.get('modifie', 0) + e.get('resultats_ajoutes', 0)} modifié(s), "
          f"{e.get('inchange', 0)} inchangé(s) · événements détectés : {bilan['evenements']}")
    print(f"Articles PubMed nouveaux : {bilan['articles_nouveaux']} (enrichis : {bilan['articles_enrichis']})"
          f" · découvertes OpenAlex : {bilan['decouvertes_openalex']}")
    for alerte in bilan["alertes"]:
        print(f"  ! {alerte}")
    print(f"Statut de l'exécution : {bilan['statut'].upper()}")
    log.info("=== Exécution %s terminée : %s ===", ex.id, bilan["statut"])

    construire_site.main(conn)
    alertes.publier(conn)
    return 1 if bilan["statut"] == "echec" else 0


if __name__ == "__main__":
    sys.exit(main())
