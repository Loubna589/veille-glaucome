"""Construit les données du site local à partir de la mémoire (data/historique/).

Lancement :  python construire_site.py        (aucun appel réseau)

Produit :
- site/data/veille.js : toutes les études, les laboratoires et les nouveautés, lus par les
  pages du site (un fichier .js plutôt que .json pour que le site marche aussi par double-clic) ;
- site/fiches/<identifiant>.html : la fiche détaillée de chaque essai et article PubMed.

Laboratoires : les noms sont regroupés automatiquement (suffixes juridiques retirés,
ex. « Santen Pharmaceutical Co., Ltd. » → « Santen ») et les regroupements manuels se
déclarent dans config/laboratoires.ini. Les trois rôles restent SÉPARÉS :
promoteur d'essai, financeur d'une publication, affiliation des auteurs.
"""
import configparser
import json
import re
import sys
import time
from pathlib import Path

# Le Python du poste (installé par WAPT) ne cherche pas les modules à côté du
# script : on lui indique explicitement le dossier du projet.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from veille import base, etiquettes, export, fiches, laboratoires_marche, resumer_ia, rubriques  # noqa: E402
from veille.sources import clinicaltrials as ct  # noqa: E402

RACINE = Path(__file__).resolve().parent
HIST = RACINE / "data" / "historique"
SITE = RACINE / "site"
CONFIG_LABOS = RACINE / "config" / "laboratoires.ini"

SUFFIXES = re.compile(
    r"\b(inc|incorporated|ltd|limited|co|corp|corporation|company|llc|plc|gmbh|ag|s\.?a|k\.?k|b\.?v|n\.?v|"
    r"s\.?p\.?a|pharmaceuticals?|pharma|global development|holdings?)\b\.?", re.IGNORECASE)


def titre_simple(titre):
    return " ".join(re.sub(r"[^\w]", " ", (titre or "").lower()).split())


PAGES_PUBLIQUES = ["index.html", "recherche.html", "assistant.html", "carte.html", "etudes.html", "laboratoires.html",
                   "marche.html", "alertes.html", "fonctionnement.html"]


def referencement(nb_fiches):
    """SEO : met à jour canonical / og:url des pages, puis écrit sitemap.xml et robots.txt.

    L'adresse publique se règle dans config/site.ini (GitHub Pages ou nom de domaine)."""
    config = configparser.ConfigParser(interpolation=None)
    config.read(RACINE / "config" / "site.ini", encoding="utf-8")
    base = config.get("publication", "url_publique", fallback="").strip()
    if not base:
        return
    base = base.rstrip("/") + "/"
    jour = time.strftime("%Y-%m-%d")
    for nom in PAGES_PUBLIQUES:
        page = SITE / nom
        if not page.exists():
            continue
        url = base if nom == "index.html" else base + nom
        html = page.read_text(encoding="utf-8")
        html2 = re.sub(r'(<link rel="canonical" href=")[^"]*(")', rf"\g<1>{url}\g<2>", html)
        html2 = re.sub(r'(<meta property="og:url" content=")[^"]*(")', rf"\g<1>{url}\g<2>", html2)
        if html2 != html:
            page.write_text(html2, encoding="utf-8")
    urls = [(base, "daily", "1.0")] + [(base + n, "daily", "0.8") for n in PAGES_PUBLIQUES[1:]]
    urls += [(base + "fiches/" + f.name, "weekly", "0.5") for f in sorted((SITE / "fiches").glob("*.html"))]
    (SITE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><lastmod>{jour}</lastmod><changefreq>{c}</changefreq><priority>{p}</priority></url>\n"
                  for u, c, p in urls) + "</urlset>\n", encoding="utf-8")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {base}sitemap.xml\n", encoding="utf-8")


def bloc_resume_ia(r):
    """Section « Résumé en français » d'une fiche, clairement marquée comme générée par IA."""
    if not r:
        return None
    lignes = "".join(f"<li>{fiches.e(l)}</li>" for l in r.get("resume") or [])
    categorie = (f"<p><strong>Catégorie : {fiches.e(r.get('categorie_libelle'))}</strong>"
                 f" — {fiches.e(r.get('justification') or '')}</p>") if r.get("categorie") else ""
    origine = (f"<p><small>Modèle {fiches.e(r.get('modele'))} · prompt {fiches.e(r.get('version_prompt'))} · "
               f"le {fiches.e(r.get('genere_le'))} · statut : {fiches.e(r.get('statut_validation'))} · "
               f"à partir du titre et du résumé de la source uniquement.</small></p>")
    return fiches.section("Résumé et classification (IA)", f"<ul>{lignes}</ul>{categorie}{origine}",
                          fiches.badge(r.get("mention") or resumer_ia.MENTION, "verifier"))


def lire(dossier):
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(Path(dossier).glob("*.json"))]


# ------------------------------------------------------------ laboratoires

def charger_alias():
    """config/laboratoires.ini, rubrique [alias] : « Nom affiché = variante 1 | variante 2 »."""
    config = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    config.optionxform = str  # garder les majuscules des noms
    config.read(CONFIG_LABOS, encoding="utf-8")
    alias = {}
    if config.has_section("alias"):
        for nom, variantes in config["alias"].items():
            for v in [nom, *variantes.split("|")]:
                alias[cle_brute(v)] = nom.strip()
    return alias


def nettoyer(nom):
    n = re.sub(r"\(.*?\)", "", nom or "").split(",")[0]
    n = SUFFIXES.sub("", n)
    return " ".join(re.sub(r"[^\w&' -]", " ", n).split()) or (nom or "").strip()


def cle_brute(nom):
    return nettoyer(nom).lower()


class Laboratoires:
    def __init__(self):
        self.alias = charger_alias()
        self.labos = {}

    def ajouter(self, nom, role, etude_id, industriel=False, statut=None):
        if not nom:
            return
        cle = cle_brute(nom)
        affiche = self.alias.get(cle) or nettoyer(nom)
        cle = affiche.lower()
        labo = self.labos.setdefault(cle, {"nom": affiche, "variantes": [], "industriel": False,
                                           "regroupement": "manuel (config/laboratoires.ini)" if cle_brute(nom) in self.alias
                                           else "automatique",
                                           "promoteur": [], "financeur": [], "affiliation": []})
        if nom not in labo["variantes"]:
            labo["variantes"].append(nom)
        labo["industriel"] = labo["industriel"] or industriel
        entree = {"id": etude_id, "statut": statut} if statut else {"id": etude_id}
        if entree not in labo[role]:
            labo[role].append(entree)
        return affiche

    def liste(self):
        # Un organisme repéré comme industriel dans un rôle l'est aussi dans les autres
        return sorted(self.labos.values(),
                      key=lambda l: (-(len(l["promoteur"]) + len(l["financeur"]) + len(l["affiliation"])), l["nom"]))


# ------------------------------------------------------------ études

def etude_essai(m, regles_rub, labos):
    d = m["donnees"]
    rub = rubriques.classer_essai(d, regles_rub)
    experimentaux = [n.split(": ", 1)[-1] for b in d.get("bras") or [] if b.get("type") == "EXPERIMENTAL"
                     for n in b.get("interventions") or []]
    comparateurs = [n.split(": ", 1)[-1] for b in d.get("bras") or []
                    if b.get("type") in ("ACTIVE_COMPARATOR", "PLACEBO_COMPARATOR", "SHAM_COMPARATOR")
                    for n in b.get("interventions") or []]
    industriel = d.get("type_promoteur") == "INDUSTRY"
    noms_labos = []
    if d.get("promoteur"):
        noms_labos.append({"nom": labos.ajouter(d["promoteur"], "promoteur", d["nct"], industriel),
                           "role": "promoteur", "industriel": industriel})
    for c in d.get("collaborateurs") or []:
        noms_labos.append({"nom": labos.ajouter(c, "promoteur", d["nct"]), "role": "collaborateur"})
    return {
        "id": d["nct"], "type": "essai", "source": "ClinicalTrials.gov",
        "titre": d["titre"], "lien_source": d["lien"], "fiche": f"fiches/{d['nct']}.html",
        "date_source": d.get("date_derniere_mise_a_jour"), "date_detection": m["premiere_detection"],
        "modifications": [{"date": x["date_detection"], "champs": sorted(x["champs"]),
                           "resultats_ajoutes": x["resultats_ajoutes"]} for x in m["modifications"]],
        "niveau": "Résultats déposés au registre" if d["resultats_deposes"] else "Essai enregistré (sans résultats)",
        "phase": ct.libelle_phase(d), "statut": ct.libelle_statut(d),
        "rubriques": [r["nom"] for r in rub], "rubrique": rub[0]["nom"],
        "raison_rubrique": "; ".join(rub[0]["raisons"][:2]),
        # Le registre déclare des BRAS (expérimental, comparateur) : on indique le bras, pas un rôle par produit
        "produits": [{"nom": p, "role": "bras expérimental (registre)"} for p in dict.fromkeys(experimentaux)]
                    + [{"nom": p, "role": "bras comparateur (registre)"} for p in dict.fromkeys(comparateurs)],
        "labos": noms_labos, "resume": d.get("resume_source"),
    }


def niveau_article(d):
    types = d.get("types_publication") or []
    if "Clinical Trial Protocol" in types:
        return "Protocole publié"
    if re.search(r"^(RESULTS|FINDINGS)\s*:", d.get("resume") or "", re.MULTILINE):
        return "Publication (résultats dans le résumé)"
    return "Publication"


def etude_article(m, regles_rub, regles_et, labos):
    d = m["donnees"]
    a = m.get("annexes", {})
    et = a.get("etiquettes") or etiquettes.etiqueter(d, regles_et)
    rub = rubriques.classer_publication(d, et, regles_rub)
    types = d.get("types_publication") or []
    phase = next((t.replace("Clinical Trial, ", "") for t in types if t.startswith("Clinical Trial, Phase")), None)
    noms_labos = []
    for f in a.get("financements") or []:
        statut = "confirmé" if f["statut"].startswith("CONFIRMÉ") else "à vérifier"
        noms_labos.append({"nom": labos.ajouter(f["nom"], "financeur", d["pmid"], statut=statut),
                           "role": f"financeur ({statut})"})
    for i in (a.get("openalex") or {}).get("institutions") or []:
        if i.get("type") == "company":
            noms_labos.append({"nom": labos.ajouter(i["nom"], "affiliation", d["pmid"], industriel=True),
                               "role": "affiliation d'auteurs", "industriel": True})
    produits = [{"nom": p["produit"], "role": f"{p['role']} (suggéré, à vérifier)" if p["role"] != "non déterminé"
                 else "cité, rôle non déterminé"} for p in et.get("produits_suivis") or []]
    produits += [{"nom": x["molecule"], "role": f"{x['role'] or 'non déterminé'} — molécule hors liste (à vérifier)"}
                 for x in et.get("molecules_hors_liste") or []]
    return {
        "id": d["pmid"], "type": "article", "source": "PubMed",
        "titre": d["titre"], "lien_source": d["lien"], "fiche": f"fiches/{d['pmid']}.html",
        "date_source": d.get("date_entree_pubmed"), "date_detection": m["premiere_detection"], "modifications": [],
        "niveau": niveau_article(d),
        "phase": f"{phase} (type de publication)" if phase else f"Stade : {et.get('stade', 'non renseigné')}",
        "statut": None, "rubriques": [r["nom"] for r in rub], "rubrique": rub[0]["nom"],
        "raison_rubrique": "; ".join(rub[0]["raisons"][:2]),
        "produits": produits, "labos": noms_labos, "resume": d.get("resume"),
        "revue": d.get("revue"), "base": "résumé seulement" if d.get("resume_present") else "métadonnées seulement",
    }


def etude_openalex(m, regles_rub, regles_et, labos):
    d = m["donnees"]
    et = m.get("annexes", {}).get("etiquettes") or etiquettes.etiqueter(d, regles_et)
    rub = rubriques.classer_publication(d, et, regles_rub)
    noms_labos = [{"nom": labos.ajouter(f["nom"], "financeur", d["openalex_id"], statut="à vérifier"),
                   "role": "financeur (à vérifier)"} for f in d.get("financeurs") or []]
    noms_labos += [{"nom": labos.ajouter(i["nom"], "affiliation", d["openalex_id"], industriel=True),
                    "role": "affiliation d'auteurs", "industriel": True}
                   for i in d.get("institutions") or [] if i.get("type") == "company"]
    return {
        "id": d["openalex_id"], "type": "publication", "source": "OpenAlex (absent de PubMed)",
        "titre": d["titre"], "lien_source": f"https://doi.org/{d['doi']}" if d.get("doi") else d["lien"], "fiche": None,
        "date_source": d.get("date_publication"), "date_detection": m["premiere_detection"], "modifications": [],
        "niveau": "Preprint (non évalué par des pairs)" if d.get("type") == "preprint" else "Publication hors PubMed",
        "phase": f"Stade : {et.get('stade', 'non renseigné')}", "statut": None,
        "rubriques": [r["nom"] for r in rub], "rubrique": rub[0]["nom"], "raison_rubrique": "; ".join(rub[0]["raisons"][:2]),
        "produits": [{"nom": p["produit"], "role": "suggéré, à vérifier"} for p in et.get("produits_suivis") or []],
        "labos": noms_labos, "resume": d.get("resume"), "revue": d.get("revue"),
    }


# ------------------------------------------------------------ programme

def main(conn=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    conn = conn or base.connecter()
    regles_rub, regles_et = rubriques.charger(), etiquettes.charger_regles()
    # Source de vérité : la base SQLite (data/veille.db)
    essais = base.memoires_essais(conn)
    articles = base.memoires_articles(conn, "pubmed")
    decouvertes = base.memoires_articles(conn, "openalex")
    etat = {"derniere_execution": base.lire_meta(conn, "derniere_execution"),
            "dernier_bilan": base.lire_meta(conn, "dernier_bilan")}
    labos = Laboratoires()

    # OpenAlex contient parfois deux notices pour une même publication : on n'en garde qu'une par titre
    titres_vus = {titre_simple(m["donnees"]["titre"]) for m in articles}
    uniques = []
    for m in decouvertes:
        cle = titre_simple(m["donnees"]["titre"])
        if cle and cle not in titres_vus:
            titres_vus.add(cle)
            uniques.append(m)
    etudes = ([etude_essai(m, regles_rub, labos) for m in essais]
              + [etude_article(m, regles_rub, regles_et, labos) for m in articles]
              + [etude_openalex(m, regles_rub, regles_et, labos) for m in uniques])

    # DOI de chaque publication (contrôle qualité : pas deux études avec le même DOI)
    doi_par_id = {m["pmid"]: m["donnees"].get("doi") for m in articles}
    doi_par_id.update({m["openalex_id"]: m["donnees"].get("doi") for m in uniques})
    for e in etudes:
        e["doi"] = doi_par_id.get(e["id"])

    # Traitements IA (resumer_ia.py) : rattachés aux études, toujours avec leur traçabilité et la mention « à vérifier »
    resumes_ia = resumer_ia.charger(conn)
    for e in etudes:
        if e["id"] in resumes_ia:
            e["resume_ia"] = resumes_ia[e["id"]]

    # Nouveautés : ce que la DERNIÈRE mise à jour a détecté (nouvelle étude ou modification)
    # Avant la première mise à jour automatique, rien n'est « nouveau » : c'est le chargement initial.
    derniere = etat.get("derniere_execution")
    for e in etudes:
        e["nouveau"] = bool(derniere) and e["date_detection"] == derniere
        e["modifie"] = bool(derniere) and any(x["date"] == derniere for x in e["modifications"])

    # Contrôles qualité AVANT export : une étude invalide est écartée et listée dans qualite.json
    etudes, rapport = export.controler(etudes)
    export.ecrire("qualite.json", rapport)

    donnees = {
        "genere_le": time.strftime("%Y-%m-%d %H:%M"),
        "derniere_mise_a_jour": derniere,
        "bilan": etat.get("dernier_bilan"),
        "ordre_rubriques": [regles_rub["rubriques"][c]["nom"] for c in regles_rub["ordre"]]
                           + [rubriques.NOM_AUTRES, regles_rub["rubriques"]["veterinaire"]["nom"]],
        "etudes": etudes,
        "laboratoires": labos.liste(),
        # Accès au marché (collecter_marche.py) : repris tel quel, la page marche.html le met en forme
        # + laboratoire déclaré par chaque source (veille/laboratoires_marche.py), regroupé pour le filtre
        "marche": laboratoires_marche.enrichir(json.loads((HIST / "marche.json").read_text(encoding="utf-8")))
        if (HIST / "marche.json").exists() else None,
    }
    # Export JSON lu par le tableau de bord (GitHub Pages = hébergement statique, pas de SQLite en ligne)
    export.ecrire("veille.json", donnees)
    export.ecrire("meta.json", {"genere_le": donnees["genere_le"], "derniere_mise_a_jour": derniere})  # pied de page
    tables = export.exporter_tables(conn)
    # Performances : résultats des évaluations (eval/), ou état « en attente des jugements »
    def lire_json(chemin):
        return json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else None

    def compter_jugements(chemin, colonne):
        if not chemin.exists():
            return {"lignes": 0, "jugees": 0}
        import csv
        lignes = list(csv.DictReader(chemin.open(encoding="utf-8-sig"), delimiter=";"))
        return {"lignes": len(lignes), "jugees": sum(1 for l in lignes if (l.get(colonne) or "").strip())}

    dossier_eval = RACINE / "eval"
    export.ecrire("performances.json", {
        "classification": lire_json(dossier_eval / "resultats.json"),
        "classification_jugements": compter_jugements(dossier_eval / "jeu_etiquete.csv", "etiquette_loubna"),
        "recherche": lire_json(dossier_eval / "resultats_recherche.json"),
        "recherche_jugements": compter_jugements(dossier_eval / "questions_recherche.csv", "pertinent_loubna"),
        "verif_marche": lire_json(dossier_eval / "resultats_verif_marche.json"),
        "verif_marche_jugements": compter_jugements(dossier_eval / "verif_marche.csv", "verifie_loubna"),
        "rag": [dict(r) for r in conn.execute("SELECT statut, COUNT(*) AS n FROM echanges_rag GROUP BY statut")]
               if conn.execute("SELECT name FROM sqlite_master WHERE name = 'echanges_rag'").fetchone() else [],
        "ia": [dict(r) for r in conn.execute("SELECT categorie, statut_validation, COUNT(*) AS n FROM traitements_ia "
                                             "GROUP BY categorie, statut_validation")],
    })

    # Frise des délais d'accès au marché (uniquement des dates déclarées par les sources)
    from veille import delais
    export.ecrire("delais.json", delais.calculer(donnees["marche"]))

    # Cartographie (Cytoscape.js) : uniquement des liens déclarés par les sources
    from veille import graphe as module_graphe
    g = module_graphe.construire(conn)
    export.ecrire("graphe.json", {**g, "statistiques": module_graphe.statistiques(g)})
    print(f"Carte : {len(g['noeuds'])} nœuds, {len(g['liens'])} liens")
    # Vecteurs pour la recherche sémantique dans le navigateur (quantifiés en int8)
    from veille import semantique
    if (semantique.DOSSIER_INDEX / "vecteurs.npy").exists():
        index = semantique.Index.charger()
        taille = semantique.exporter_site(index, SITE / "data" / "semantique.json")
        print(f"Recherche sémantique : index exporté pour le site ({taille // 1024} Ko)")
        # Résultats de la question d'exemple, affichés tout de suite (le modèle met un peu de temps à charger dans le navigateur)
        try:
            question = "Quels traitements du glaucome sans conservateur font actuellement l'objet de recherches cliniques ?"
            resultats, etendue = semantique.rechercher(index, semantique.Encodeur(), question, k=5)
            export.ecrire("recherche_exemple.json", {"question": question, "question_etendue": etendue, "resultats": [
                {k: r.get(k) for k in ("id", "type", "titre", "fiche", "lien", "date", "score", "score_dense", "score_lexical")}
                for r in resultats]})
        except Exception as erreur:  # noqa: BLE001 — modèle indisponible : la page fonctionne sans l'exemple
            print(f"Exemple de recherche non calculé : {erreur}")
    ancien = SITE / "data" / "veille.js"
    if ancien.exists():
        ancien.unlink()  # ancien format (remplacé par veille.json)

    # Fiches détaillées (essais et articles PubMed)
    (SITE / "fiches").mkdir(parents=True, exist_ok=True)
    genere_le = donnees["genere_le"]
    for m in essais:
        rub = rubriques.classer_essai(m["donnees"], regles_rub)
        entete, blocs, manquants = fiches.fiche_essai(m, articles, rub)
        if bloc_resume_ia(resumes_ia.get(m["nct"])):
            blocs.insert(0, bloc_resume_ia(resumes_ia[m["nct"]]))
        (SITE / "fiches" / f"{m['nct']}.html").write_text(fiches.page(
            f"{m['nct']} — fiche essai", entete, blocs, manquants, fiches.texte_copie_essai(m), genere_le, retour=True),
            encoding="utf-8")
    for m in articles:
        m.setdefault("annexes", {}).setdefault("etiquettes", etiquettes.etiqueter(m["donnees"], regles_et))
        rub = rubriques.classer_publication(m["donnees"], m["annexes"]["etiquettes"], regles_rub)
        entete, blocs, manquants = fiches.fiche_article(m, [x["donnees"] for x in essais], rub)
        if bloc_resume_ia(resumes_ia.get(m["pmid"])):
            blocs.insert(0, bloc_resume_ia(resumes_ia[m["pmid"]]))
        (SITE / "fiches" / f"{m['pmid']}.html").write_text(fiches.page(
            f"PMID {m['pmid']} — fiche article", entete, blocs, manquants, fiches.texte_copie_article(m), genere_le,
            retour=True), encoding="utf-8")

    referencement(len(essais) + len(articles))
    print(f"Contrôle qualité : {rapport['etudes_exportees']} étude(s) exportée(s), {rapport['etudes_rejetees']} rejetée(s)")
    print(f"Site reconstruit : {len(etudes)} études, {len(donnees['laboratoires'])} organismes, "
          f"{len(essais) + len(articles)} fiches → {SITE / 'index.html'} · base : {tables}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
