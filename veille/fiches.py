"""Fiches HTML d'étude (essai ClinicalTrials.gov ou article PubMed).

Principes :
- chaque information porte sa SOURCE (registre, résumé PubMed, OpenAlex, Crossref,
  règle automatique de l'outil) ;
- les extraits des sources restent dans leur langue d'origine (anglais) ; seuls les
  titres de rubriques sont en français ;
- ce qui manque est listé explicitement ;
- aucune conclusion, limite ni analyse marketing n'est rédigée : ces rubriques
  renvoient au bouton « Copier pour Claude / ChatGPT » ;
- promoteur, financeur et affiliation sont présentés dans trois blocs distincts.
"""
import html
import re

from veille.sources import clinicaltrials as ct

# ------------------------------------------------------------ vocabulaire

TYPES_BRAS = {
    "EXPERIMENTAL": "Expérimental (traitement étudié)",
    "ACTIVE_COMPARATOR": "Comparateur actif",
    "PLACEBO_COMPARATOR": "Comparateur placebo",
    "SHAM_COMPARATOR": "Comparateur simulé (sham)",
    "NO_INTERVENTION": "Sans intervention",
    "OTHER": "Autre",
}
REPARTITION = {"RANDOMIZED": "randomisée", "NON_RANDOMIZED": "non randomisée", "NA": "sans objet (un seul groupe)"}
MODELES = {"PARALLEL": "groupes parallèles", "CROSSOVER": "croisé", "SINGLE_GROUP": "groupe unique",
           "FACTORIAL": "factoriel", "SEQUENTIAL": "séquentiel"}
INSU = {"NONE": "ouvert (sans insu)", "SINGLE": "simple insu", "DOUBLE": "double insu",
        "TRIPLE": "triple insu", "QUADRUPLE": "quadruple insu"}
BUTS = {"TREATMENT": "traitement", "PREVENTION": "prévention", "DIAGNOSTIC": "diagnostic",
        "SUPPORTIVE_CARE": "soins de support", "SCREENING": "dépistage", "BASIC_SCIENCE": "recherche fondamentale",
        "HEALTH_SERVICES_RESEARCH": "organisation des soins", "DEVICE_FEASIBILITY": "faisabilité d'un dispositif",
        "OTHER": "autre"}
MESURES = {"LEAST_SQUARES_MEAN": "moyenne des moindres carrés", "MEAN": "moyenne", "MEDIAN": "médiane",
           "GEOMETRIC_MEAN": "moyenne géométrique", "COUNT_OF_PARTICIPANTS": "nombre de participants",
           "COUNT_OF_UNITS": "nombre d'unités (ex. yeux)", "NUMBER": "nombre", "GEOMETRIC_LEAST_SQUARES_MEAN":
           "moyenne géométrique des moindres carrés", "LOG_MEAN": "moyenne logarithmique"}
ETAPES = {"STARTED": "Ont commencé", "COMPLETED": "Ont terminé", "NOT COMPLETED": "N'ont pas terminé"}
ROLES_RESPONSABLE = {"PRINCIPAL_INVESTIGATOR": "investigateur principal", "STUDY_DIRECTOR": "directeur d'étude",
                     "STUDY_CHAIR": "président de l'étude"}
TYPES_CRITERE = {"PRIMARY": "Critère principal", "SECONDARY": "Critère secondaire",
                 "OTHER_PRE_SPECIFIED": "Autre critère prédéfini", "POST_HOC": "Analyse post hoc"}
TYPES_REFERENCE = {
    "RESULT": "déclarée par le promoteur comme publication des résultats de l'essai",
    "DERIVED": "lien établi par PubMed à partir du NCT déclaré dans l'article",
    "BACKGROUND": "citée par le registre comme référence de contexte (pas une publication de l'essai)",
}
TYPES_INSTITUTION = {"education": "enseignement/recherche", "healthcare": "santé/hôpital", "company": "entreprise",
                     "government": "organisme public", "nonprofit": "fondation/association",
                     "facility": "infrastructure", "other": "autre"}
CLASSES_PROMOTEUR = {"INDUSTRY": "industriel", "OTHER": "académique ou autre", "NIH": "NIH (public, États-Unis)",
                     "FED": "agence fédérale (États-Unis)", "NETWORK": "réseau", "INDIV": "individu",
                     "OTHER_GOV": "autre organisme public", "UNKNOWN": "inconnu"}
SECTIONS_RESUME = {
    "question": ("PURPOSE", "OBJECTIVE", "OBJECTIVES", "AIM", "AIMS", "INTRODUCTION", "BACKGROUND", "IMPORTANCE",
                 "PRECIS", "BACKGROUND/AIMS", "BACKGROUND AND AIMS", "BACKGROUND AND OBJECTIVE"),
    "methode": ("METHODS", "METHOD", "STUDY DESIGN", "DESIGN", "SETTING", "PARTICIPANTS", "PATIENTS AND METHODS",
                "MATERIALS AND METHODS", "DESIGN, SETTING, AND PARTICIPANTS", "INTERVENTIONS", "MAIN OUTCOME MEASURES",
                "MAIN OUTCOMES AND MEASURES", "SUBJECTS AND METHODS"),
    "resultats": ("RESULTS", "FINDINGS", "MAIN RESULTS"),
    "conclusion": ("CONCLUSION", "CONCLUSIONS", "CONCLUSIONS AND RELEVANCE", "INTERPRETATION", "DISCUSSION"),
}

MOTIF_TOLERANCE = r"adverse|safety|tolerab|hyperaemia|hyperemia|side effect|\bADRs?\b|complication"
STATUTS_ACCES = {"gold": "libre (revue en accès ouvert)", "diamond": "libre (revue gratuite)",
                 "hybrid": "libre (article ouvert dans une revue payante)", "green": "libre (copie déposée dans une archive)",
                 "bronze": "lisible gratuitement chez l'éditeur (sans licence ouverte)", "closed": "fermé (payant)"}

ANALYSE_NON_REDIGEE = ("Non rédigé automatiquement : les données extraites ne suffisent pas à produire "
                       "une analyse fiable sans interprétation. Utilisez le bouton « Copier pour Claude / "
                       "ChatGPT » pour obtenir une proposition, à vérifier.")

e = lambda texte: html.escape(str(texte), quote=False)  # noqa: E731


# ------------------------------------------------------------ petits éléments

def badge(texte, genre="source"):
    return f'<span class="badge {genre}">{e(texte)}</span>'


def manque(texte="Non rapporté"):
    return f'<span class="manque">{e(texte)}</span>'


def chiffres(texte):
    """Met en évidence les valeurs chiffrées d'un extrait (le texte reste inchangé)."""
    return re.sub(r"(?<![\w.])([<>≤≥=±]\s*)?-?\d+(?:[.,]\d+)?(?:\s?(?:%|mmHg|mm Hg))?",
                  lambda m: f"<mark>{m.group(0)}</mark>", e(texte))


def section(titre, contenu, sources=""):
    return f'<section><h2>{e(titre)} {sources}</h2>{contenu}</section>'


def tableau(entetes, lignes):
    tete = "".join(f"<th>{e(h)}</th>" for h in entetes)
    corps = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in l) + "</tr>" for l in lignes)
    return f'<div class="defile"><table><thead><tr>{tete}</tr></thead><tbody>{corps}</tbody></table></div>'


def lien(url, texte=None):
    return f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{e(texte or url)}</a>'


def liste(elements):
    return "<ul>" + "".join(f"<li>{x}</li>" for x in elements) + "</ul>"


def rubriques_html(rubriques):
    blocs = []
    for r in rubriques:
        raisons = "; ".join(r["raisons"][:3]) + (" …" if len(r["raisons"]) > 3 else "")
        blocs.append(f'<span class="rubrique">{e(r["nom"])}</span> <small>{e(raisons)}</small>')
    return "<br>".join(blocs) + f' {badge("classement automatique — règles dans config/rubriques.ini", "regle")}'


# ------------------------------------------------------------ fiche ESSAI

def _valeur_mesure(v, dispersion_type):
    morceaux = [f"<mark>{e(v['valeur'])}</mark>" if v.get("valeur") not in (None, "NA") else manque()]
    if v.get("dispersion"):
        morceaux.append(f"± {e(v['dispersion'])} <small>({e(dispersion_type or 'dispersion')})</small>")
    if v.get("borne_basse") or v.get("borne_haute"):
        morceaux.append(f"[{e(v.get('borne_basse') or '?')} ; {e(v.get('borne_haute') or '?')}]"
                        f" <small>({e(dispersion_type or 'intervalle')})</small>")
    return " ".join(morceaux)


def fiche_essai(memoire, articles_memoire, rubriques):
    d = memoire["donnees"]
    nct = d["nct"]
    src_reg = badge("Registre ClinicalTrials.gov")
    manquants, blocs = [], []
    res = d.get("resultats")

    # --- En-tête
    if d["resultats_deposes"]:
        niveau = badge(f"RÉSULTATS DÉPOSÉS AU REGISTRE (le {d.get('date_depot_resultats') or 'date non rapportée'})", "confirme")
    else:
        niveau = badge("ESSAI ENREGISTRÉ — AUCUN RÉSULTAT DÉPOSÉ AU REGISTRE", "attente")
    entete = f"""
    <header>
      <p class="surtitre">Fiche essai clinique · {e(nct)} · {lien(d['lien'], 'voir sur ClinicalTrials.gov')}</p>
      <h1>{e(d['titre'] or 'Titre non rapporté')}</h1>
      <p>{niveau}</p>
      <dl class="grille">
        <dt>Phase (déclarée)</dt><dd>{e(ct.libelle_phase(d))}</dd>
        <dt>Statut</dt><dd>{e(ct.libelle_statut(d))}</dd>
        <dt>Type d'étude</dt><dd>{e(ct.libelle_type_etude(d))}</dd>
        <dt>Participants</dt><dd>{e(ct.libelle_participants(d))}</dd>
        <dt>Première publication au registre</dt><dd>{e(d['date_premiere_publication'] or 'non rapportée')}</dd>
        <dt>Dernière mise à jour au registre</dt><dd>{e(d['date_derniere_mise_a_jour'] or 'non rapportée')}</dd>
        <dt>Début · fin principale</dt><dd>{e(d.get('date_debut') or '?')} · {e(d.get('date_fin_principale') or '?')}</dd>
        <dt>Détecté par l'outil le</dt><dd>{e(memoire['premiere_detection'])} · {len(memoire['modifications'])} modification(s) repérée(s) depuis</dd>
      </dl>
      <p class="rubriques"><strong>Rubrique :</strong> {rubriques_html(rubriques)}</p>
    </header>"""

    # --- Question étudiée
    contenu = f"<p><strong>Titre officiel :</strong> {e(d.get('titre_officiel') or 'non rapporté')}</p>"
    if d.get("resume_source"):
        contenu += f'<blockquote lang="en">{e(d["resume_source"])}</blockquote>'
    else:
        manquants.append("description de l'essai")
        contenu += f"<p>{manque('Description non rapportée')}</p>"
    blocs.append(section("Question étudiée", contenu, src_reg))

    # --- Traitement / technologie et comparateur (rôles CONFIRMÉS par le registre)
    if d.get("bras"):
        lignes = [[f"<strong>{e(b['libelle'])}</strong>", e(TYPES_BRAS.get(b["type"], b["type"] or "non rapporté")),
                   "<br>".join(e(i) for i in b.get("interventions") or []) or manque(),
                   f'<small lang="en">{e(b.get("description") or "")}</small>'] for b in d["bras"]]
        contenu = tableau(["Bras", "Rôle déclaré", "Interventions", "Description (registre)"], lignes)
        sources = src_reg + badge("rôles CONFIRMÉS : type de bras déclaré au registre", "confirme")
    else:
        contenu = liste([e(x) for x in ct.libelle_interventions(d)])
        contenu += f"<p>{manque('Bras de l’étude non déclarés : rôle étudié / comparateur non confirmé')}</p>"
        manquants.append("bras de l'étude (rôles étudié / comparateur)")
        sources = src_reg
    blocs.append(section("Traitement ou technologie, et comparateur", contenu, sources))

    # --- Type d'étude
    plan = d.get("plan") or {}
    elements = [f"Type : {e(ct.libelle_type_etude(d))} · phase déclarée : {e(ct.libelle_phase(d))}"]
    if plan.get("repartition"):
        elements.append(f"Répartition : {e(REPARTITION.get(plan['repartition'], plan['repartition']))}")
    if plan.get("modele"):
        elements.append(f"Modèle : {e(MODELES.get(plan['modele'], plan['modele']))}")
    if plan.get("insu"):
        qui = ", ".join(plan.get("insu_pour") or [])
        elements.append(f"Insu : {e(INSU.get(plan['insu'], plan['insu']))}" + (f" <small>({e(qui)})</small>" if qui else ""))
    if plan.get("but_principal"):
        elements.append(f"But principal : {e(BUTS.get(plan['but_principal'], plan['but_principal']))}")
    contenu = liste(elements)
    if plan.get("insu_description"):
        contenu += (f'<details><summary>Description de l\'insu (texte du registre)</summary>'
                    f'<p lang="en">{e(plan["insu_description"])}</p>'
                    '<p class="def">À comparer avec le niveau d\'insu déclaré ci-dessus : '
                    'le registre peut être incohérent.</p></details>')
    blocs.append(section("Type d'étude", contenu, src_reg))

    # --- Population
    el = d.get("eligibilite") or {}
    elements = [
        f"Conditions déclarées : {e(', '.join(d.get('conditions') or [])) or manque()}",
        f"Âge : {e(el.get('age_min') or 'min. non rapporté')} → {e(el.get('age_max') or 'max. non rapporté')}",
        f"Sexe : {e({'ALL': 'tous', 'FEMALE': 'femmes', 'MALE': 'hommes'}.get(el.get('sexe'), el.get('sexe') or 'non rapporté'))}",
        f"Volontaires sains acceptés : {e({True: 'oui', False: 'non'}.get(el.get('volontaires_sains'), 'non rapporté'))}",
        f"Nombre de participants : <mark>{e(ct.libelle_participants(d))}</mark>",
    ]
    contenu = liste(elements)
    if el.get("criteres"):
        contenu += f'<details><summary>Critères d\'inclusion et d\'exclusion (texte du registre)</summary><pre lang="en">{e(el["criteres"])}</pre></details>'
    else:
        manquants.append("critères d'inclusion")
    blocs.append(section("Population et participants", contenu, src_reg))

    # --- Critères évalués (tels que prévus)
    prevus = [f"<strong>Principal :</strong> {e(c['critere'])} <small>[{e(c.get('delai') or 'délai non rapporté')}]</small>"
              for c in d.get("criteres_principaux") or []]
    prevus += [f"Secondaire : {e(c['critere'])} <small>[{e(c.get('delai') or 'délai non rapporté')}]</small>"
               for c in d.get("criteres_secondaires") or []]
    if not prevus:
        manquants.append("critères d'évaluation")
    blocs.append(section("Critères évalués (tels que déclarés)", liste(prevus) if prevus else f"<p>{manque()}</p>", src_reg))

    # --- Résultats
    if res and res.get("criteres"):
        src_res = badge(f"Résultats déposés au registre le {d.get('date_depot_resultats') or '?'}", "confirme")
        contenu = f'<p>Valeurs recopiées telles quelles depuis {lien(d["lien"] + "?tab=results", "l’onglet Résultats du registre")}.</p>'
        if res.get("flux_participants"):
            lignes = [[e(ETAPES.get(etape["etape"], etape["etape"])), "<br>".join(f"{e(g['groupe'])} : <mark>{e(g['nombre'])}</mark>"
                                                    for g in etape["par_groupe"])] for etape in res["flux_participants"]]
            contenu += "<h3>Flux des participants</h3>" + tableau(["Étape", "Par groupe"], lignes)
        for c in sorted(res["criteres"], key=lambda c: c["type"] != "PRIMARY"):
            contenu += (f'<h3>{e(TYPES_CRITERE.get(c["type"], c["type"]))} — <span lang="en">{e(c["titre"])}</span></h3>'
                        f'<p><small>Délai : {e(c.get("delai") or "?")} · Mesure : {e(MESURES.get(c.get("parametre"), c.get("parametre") or "?"))}'
                        f' · Unité : {e(c.get("unite") or "?")}</small></p>')
            if c.get("valeurs"):
                lignes = [[e(v["groupe"]) + (f" <small>({e(v['sous_groupe'])})</small>" if v.get("sous_groupe") else ""),
                           e(v.get("effectif_analyse") or "?"), _valeur_mesure(v, c.get("dispersion_type"))]
                          for v in c["valeurs"]]
                contenu += tableau(["Groupe", "Effectif analysé", "Valeur"], lignes)
            else:
                contenu += f"<p>{manque('Aucune valeur déposée pour ce critère')}</p>"
            for a in c.get("analyses") or []:
                ic = (f" · IC {e(a['ic_pct'])} % : [{e(a['ic_bas'])} ; {e(a['ic_haut'])}]"
                      if a.get("ic_bas") is not None else "")
                contenu += (f'<p class="analyse">Comparaison ({e(" vs ".join(a["groupes"]))}) : '
                            f'{e(a.get("parametre") or "estimation")} = <mark>{e(a.get("estimation") or "non rapportée")}</mark>{ic}'
                            f' · p = <mark>{e(a.get("p") or "non rapporté")}</mark>'
                            f' · méthode : {e(a.get("methode") or "?")} · hypothèse : {e(a.get("hypothese") or "?")}</p>')
            if c.get("population"):
                contenu += f'<details><summary>Population analysée (registre)</summary><p lang="en">{e(c["population"])}</p></details>'
        blocs.append(section("Résultats disponibles", contenu, src_res))
    else:
        manquants.append("résultats (aucun résultat déposé au registre)")
        texte = ("Aucun résultat n'est déposé au registre à ce jour."
                 + (" L'essai est terminé : des résultats pourraient être publiés ou déposés plus tard."
                    if d.get("statut") == "COMPLETED" else f" Statut actuel : {ct.libelle_statut(d)}."))
        blocs.append(section("Résultats disponibles", f"<p>{manque(texte)}</p>", src_reg))

    # --- Tolérance
    ei = (res or {}).get("evenements_indesirables")
    if ei:
        lignes = [[e(g["groupe"]), f"<mark>{e(g['exposes'])}</mark>", f"<mark>{e(g['graves'])}</mark>",
                   f"<mark>{e(g['autres'])}</mark>", f"<mark>{e(g['deces'])}</mark>"] for g in ei["par_groupe"]]
        contenu = tableau(["Groupe", "Exposés", "Événements graves (participants)", "Autres événements (participants)",
                           "Décès"], lignes)
        autres = sorted(ei.get("autres") or [], key=lambda x: -sum(s["touches"] or 0 for s in x["par_groupe"]))[:5]
        if autres:
            lignes = [[f'<span lang="en">{e(x["terme"])}</span>', "<br>".join(
                f"{e(s['groupe'])} : <mark>{e(s['touches'])}</mark>/{e(s['exposes'])}" for s in x["par_groupe"])]
                for x in autres]
            contenu += f"<h3>Événements non graves les plus fréquents (seuil déclaré : {e(ei.get('seuil_frequence_pct') or '?')} %)</h3>"
            contenu += tableau(["Événement", "Participants touchés / exposés"], lignes)
        graves = ei.get("graves") or []
        if graves:
            lignes = [[f'<span lang="en">{e(x["terme"])}</span>', "<br>".join(
                f"{e(s['groupe'])} : <mark>{e(s['touches'])}</mark>/{e(s['exposes'])}" for s in x["par_groupe"])]
                for x in graves]
            contenu += "<h3>Événements graves</h3>" + tableau(["Événement", "Participants touchés / exposés"], lignes)
        if ei.get("periode"):
            contenu += f'<details><summary>Période de recueil (registre)</summary><p lang="en">{e(ei["periode"])}</p></details>'
        blocs.append(section("Données de tolérance", contenu, badge("Résultats déposés au registre", "confirme")))
    else:
        manquants.append("données de tolérance")
        blocs.append(section("Données de tolérance", f"<p>{manque('Non disponibles : aucun résultat déposé au registre')}</p>", src_reg))

    # --- Publications liées
    elements = []
    for c in d.get("citations_declarees") or []:
        nature = TYPES_REFERENCE.get(c.get("type"), c.get("type") or "type non précisé")
        statut = badge("lien confirmé", "confirme") if c.get("type") in ("RESULT", "DERIVED") else badge("contexte", "regle")
        ref = lien(f"https://pubmed.ncbi.nlm.nih.gov/{c['pmid']}/", f"PMID {c['pmid']}") if c.get("pmid") else "sans PMID"
        elements.append(f"{statut} {ref} — {e(nature)}<br><small lang=\"en\">{e(c.get('citation') or '')}</small>")
    for a in articles_memoire:
        if nct in (a["donnees"].get("nct_declares") or []):
            elements.append(f"{badge('lien confirmé', 'confirme')} PMID {e(a['pmid'])} — NCT déclaré dans la notice PubMed")
        elif nct in (a["donnees"].get("nct_mentionnes_texte") or []):
            elements.append(f"{badge('lien possible, à vérifier', 'verifier')} PMID {e(a['pmid'])} — NCT cité dans le résumé seulement")
    if not elements:
        elements.append(manque("Aucune publication liée identifiée"))
        manquants.append("publication liée")
    blocs.append(section("Publications liées", liste(elements), src_reg))

    # --- Promoteur, financeur, affiliations
    classe = CLASSES_PROMOTEUR.get(d.get("type_promoteur"), d.get("type_promoteur") or "catégorie non rapportée")
    collab = ", ".join(d.get("collaborateurs") or []) or "aucun déclaré"
    resp = [f"{e(r['nom'] or '?')} — {e(ROLES_RESPONSABLE.get(r['role'], r['role'] or 'rôle ?'))}"
            f" — affiliation : {e(r['affiliation'] or 'non rapportée')}"
            for r in d.get("responsables") or []]
    contenu = f"""<div class="acteurs">
      <div><h3>Promoteur</h3><p class="def">Organisme responsable de l'essai, déclaré au registre.</p>
        <p><strong>{e(d.get('promoteur') or 'non rapporté')}</strong> ({e(classe)})</p>
        <p>Collaborateurs déclarés : {e(collab)}</p></div>
      <div><h3>Financeur</h3><p class="def">Organisme qui finance la recherche.</p>
        <p>{manque("Non déclaré séparément dans le registre.")} Le promoteur n'est pas présenté ici comme financeur : le registre ne le précise pas.</p></div>
      <div><h3>Affiliations</h3><p class="def">Établissement des responsables de l'étude.</p>
        {liste(resp) if resp else '<p>' + manque('Aucun responsable déclaré au registre') + '</p>'}</div>
    </div>"""
    if not resp:
        manquants.append("responsables de l'étude et leur affiliation")
    blocs.append(section("Promoteur, financeur et affiliations", contenu, src_reg))

    return entete, blocs, manquants


def texte_copie_essai(memoire):
    d = memoire["donnees"]
    res = d.get("resultats") or {}
    lignes = [
        f"SOURCE : registre ClinicalTrials.gov, essai {d['nct']} — {d['lien']}",
        f"NIVEAU DE PREUVE : {'résultats déposés au registre le ' + str(d.get('date_depot_resultats')) if d['resultats_deposes'] else 'essai enregistré, AUCUN résultat déposé au registre'}",
        f"Titre : {d['titre']}", f"Titre officiel : {d.get('titre_officiel')}",
        f"Phase déclarée : {ct.libelle_phase(d)} · Statut : {ct.libelle_statut(d)} · Type : {ct.libelle_type_etude(d)}",
        f"Promoteur (déclaré) : {d.get('promoteur')} ({d.get('type_promoteur')}) · Collaborateurs : {', '.join(d.get('collaborateurs') or []) or 'aucun'}",
        "Financeur : non déclaré séparément dans le registre",
        f"Participants : {ct.libelle_participants(d)} · Conditions : {', '.join(d.get('conditions') or [])}",
        f"Plan : {d.get('plan')}",
        "Bras (rôle déclaré) :",
        *[f"  - {b['libelle']} [{b['type']}] : {', '.join(b.get('interventions') or [])}" for b in d.get("bras") or []],
        "Critères principaux : " + "; ".join(f"{c['critere']} [{c.get('delai')}]" for c in d.get("criteres_principaux") or []),
        "Critères secondaires : " + ("; ".join(f"{c['critere']} [{c.get('delai')}]" for c in d.get("criteres_secondaires") or []) or "non rapportés"),
        "", "DESCRIPTION (registre, texte source) :", d.get("resume_source") or "non rapportée",
    ]
    if res.get("criteres"):
        lignes += ["", "RÉSULTATS DÉPOSÉS AU REGISTRE (valeurs exactes) :"]
        for c in res["criteres"]:
            lignes.append(f"* {c['type']} — {c['titre']} [{c.get('delai')}] ({c.get('parametre')}, {c.get('unite')}, dispersion : {c.get('dispersion_type')})")
            for v in c.get("valeurs") or []:
                lignes.append(f"    {v['groupe']}{' / ' + v['sous_groupe'] if v.get('sous_groupe') else ''} : {v['valeur']}"
                              f"{' ± ' + v['dispersion'] if v.get('dispersion') else ''} (n={v.get('effectif_analyse')})")
            for a in c.get("analyses") or []:
                lignes.append(f"    Comparaison : {a.get('parametre')} = {a.get('estimation')} (IC {a.get('ic_pct')} % {a.get('ic_bas')} ; {a.get('ic_haut')}), p = {a.get('p')}, {a.get('methode')}, {a.get('hypothese')}")
        ei = res.get("evenements_indesirables") or {}
        for g in ei.get("par_groupe") or []:
            lignes.append(f"  Tolérance — {g['groupe']} : exposés {g['exposes']}, graves {g['graves']}, autres {g['autres']}, décès {g['deces']}")
    else:
        lignes += ["", "RÉSULTATS : aucun résultat déposé au registre."]
    return "\n".join(lignes)


# ------------------------------------------------------------ fiche ARTICLE

def decouper_resume(resume):
    """Répartit un résumé structuré (« LABEL: texte ») dans les rubriques de la fiche."""
    parties = {"question": [], "methode": [], "resultats": [], "conclusion": [], "autre": []}
    structure = False
    for ligne in (resume or "").splitlines():
        m = re.match(r"^([A-Z][A-Z ,/&-]{2,}):\s*(.*)$", ligne)
        if m:
            structure = True
            label, texte = m.group(1).strip(), m.group(2)
            cle = next((k for k, labels in SECTIONS_RESUME.items() if label in labels), "autre")
            parties[cle].append((label, texte))
        elif ligne.strip():
            parties["autre"].append((None, ligne))
    return parties, structure


def phrases(texte, motif):
    return [p for p in re.split(r"(?<=[.;])\s+(?=[A-Z(])", texte or "") if re.search(motif, p, re.IGNORECASE)]


def _extraits(liste_parties):
    if not liste_parties:
        return None
    return "".join(f'<blockquote lang="en">{f"<strong>{e(l)}</strong> " if l else ""}{chiffres(t)}</blockquote>'
                   for l, t in liste_parties)


def fiche_article(memoire, essais_memoire, rubriques):
    d = memoire["donnees"]
    annexes = memoire.get("annexes", {})
    et = annexes.get("etiquettes", {})
    oa = annexes.get("openalex") or {}
    src_pm = badge("Résumé PubMed (texte source)")
    manquants, blocs = [], []
    parties, structure = decouper_resume(d.get("resume"))
    types = d.get("types_publication") or []

    # --- Niveau de preuve
    if "Clinical Trial Protocol" in types:
        niveau = badge("PROTOCOLE PUBLIÉ — pas de résultats", "attente")
    elif parties["resultats"]:
        niveau = badge("PUBLICATION — le résumé rapporte des résultats", "confirme")
    else:
        niveau = badge("PUBLICATION — résultats non identifiés dans le résumé", "attente")
    base = ("Synthèse fondée UNIQUEMENT sur le résumé PubMed : le texte intégral n'a pas été lu."
            if d.get("resume_present") else "Aucun résumé disponible : seules les métadonnées sont connues.")

    acces = oa.get("statut_acces")
    lien_texte = oa.get("url_pdf") or oa.get("url_texte")
    entete = f"""
    <header>
      <p class="surtitre">Fiche article · PMID {e(d['pmid'])} · {lien(d['lien'], 'voir sur PubMed')}
        {' · ' + lien('https://doi.org/' + d['doi'], 'DOI ' + d['doi']) if d.get('doi') else ''}</p>
      <h1 lang="en">{e(d['titre'])}</h1>
      <p>{niveau} {badge(base, 'verifier')}</p>
      <dl class="grille">
        <dt>Revue</dt><dd>{e(d.get('revue') or 'non rapportée')}</dd>
        <dt>Entrée dans PubMed</dt><dd>{e(d.get('date_entree_pubmed') or '?')} · publication : {e(d.get('date_publication') or '?')}</dd>
        <dt>Type(s) de publication (PubMed)</dt><dd lang="en">{e(', '.join(types) or 'non rapporté')}</dd>
        <dt>Stade</dt><dd>{e(et.get('stade') or 'non calculé')}{' <small>(' + e(et['stade_source']) + ')</small>' if et.get('stade_source') else ''}</dd>
        <dt>Accès au texte (OpenAlex)</dt><dd>{e(STATUTS_ACCES.get(acces, acces or 'non rapporté'))}{' · ' + lien(lien_texte, 'ouvrir le texte') if lien_texte else ''}</dd>
        <dt>Détecté par l'outil le</dt><dd>{e(memoire['premiere_detection'])}</dd>
      </dl>
      <p class="rubriques"><strong>Rubrique :</strong> {rubriques_html(rubriques)}</p>
    </header>"""

    # --- Question
    contenu = _extraits(parties["question"])
    if not contenu:
        manquants.append("question / objectif (pas de paragraphe dédié dans le résumé)")
        contenu = f"<p>{manque('Pas de paragraphe « objectif » identifié dans le résumé')}</p>"
    blocs.append(section("Question étudiée", contenu, src_pm))

    # --- Traitement et comparateur (rôles SUGGÉRÉS)
    elements = []
    for p in et.get("produits_suivis") or []:
        genre = "verifier" if p["role"] != "non déterminé" else "regle"
        elements.append(f"<strong>{e(p['produit'])}</strong> — {e(p['role'])} {badge(p['statut_role'], genre)}")
    for m in et.get("molecules_hors_liste") or []:
        elements.append(f"<strong>{e(m['molecule'])}</strong> (molécule hors liste — {e(m['reperage'])}) — "
                        f"{e(m['role'] or 'non déterminé')} {badge(m['statut_role'], 'verifier')}")
    for f in et.get("formulations_voies") or []:
        elements.append(f"Formulation / voie d'administration citée : {e(f)} {badge('repérage automatique', 'regle')}")
    if not elements:
        elements.append(manque("Aucun produit suivi ni molécule repérés automatiquement"))
    contenu = liste(elements) + ('<p class="def">Aucun rôle n\'est confirmé : PubMed ne décrit pas les bras '
                                 "d'une étude. Un rôle pourrait être confirmé par le registre d'un essai lié de façon confirmée.</p>")
    blocs.append(section("Traitement ou technologie, et comparateur", contenu, badge("règle automatique de l'outil", "regle")))

    # --- Méthode / type d'étude
    contenu = f"<p>Type(s) de publication déclaré(s) par PubMed : <span lang=\"en\">{e(', '.join(types) or 'non rapporté')}</span></p>"
    contenu += _extraits(parties["methode"]) or f"<p>{manque('Pas de paragraphe « méthodes » dans le résumé')}</p>"
    if not parties["methode"]:
        manquants.append("méthodes (pas de paragraphe dédié dans le résumé)")
    blocs.append(section("Type d'étude et méthode", contenu, src_pm + badge("PubMed (types de publication)")))

    # --- Population (phrases sur l'inclusion ; les phrases sur les effets indésirables vont en tolérance)
    texte_complet = " ".join(t for k in ("methode", "resultats", "autre") for _, t in parties[k])
    extraits_pop = [p for p in phrases(texte_complet, r"\b(randomi[sz]ed|enrolled|included|recruited|n\s*=)|"
                                                      r"\b\d+\s+(patients|participants|subjects|eyes)\b")
                    if not re.search(MOTIF_TOLERANCE, p, re.IGNORECASE)]
    if extraits_pop:
        contenu = "".join(f'<blockquote lang="en">{chiffres(p)}</blockquote>' for p in extraits_pop[:4])
    else:
        contenu = f"<p>{manque('Nombre de participants non rapporté dans le résumé')}</p>"
        manquants.append("population et nombre de participants")
    blocs.append(section("Population et participants (phrases du résumé)", contenu, src_pm))

    # --- Résultats
    if parties["resultats"]:
        contenu = ('<p class="def">Valeurs chiffrées surlignées telles qu\'elles figurent dans le résumé. '
                   "Elles n'ont pas été vérifiées dans le texte intégral.</p>" + _extraits(parties["resultats"]))
    else:
        contenu = f"<p>{manque('Aucune partie « résultats » dans le résumé')}</p>"
        if not structure and d.get("resume"):
            contenu += "<h3>Résumé complet (non structuré)</h3>" + _extraits([(None, d["resume"])])
        manquants.append("résultats chiffrés")
    blocs.append(section("Résultats disponibles", contenu, src_pm))

    # --- Tolérance
    # Uniquement dans les méthodes et résultats : l'objectif et la conclusion ne sont pas des données
    extraits_tol = phrases(texte_complet, MOTIF_TOLERANCE)
    if extraits_tol:
        contenu = "".join(f'<blockquote lang="en">{chiffres(p)}</blockquote>' for p in extraits_tol[:4])
    else:
        contenu = f"<p>{manque('Aucune donnée de tolérance dans le résumé')}</p>"
        manquants.append("données de tolérance")
    blocs.append(section("Données de tolérance (phrases du résumé)", contenu, src_pm))

    # --- Conclusion des auteurs (citée, non évaluée)
    if parties["conclusion"]:
        blocs.append(section("Conclusion des auteurs (citée telle quelle, non évaluée par l'outil)",
                             _extraits(parties["conclusion"]), src_pm))

    # --- Essai lié
    elements = []
    for nct in d.get("nct_declares") or []:
        present = next((x for x in essais_memoire if x["nct"] == nct), None)
        elements.append(f"{badge('lien confirmé', 'confirme')} {lien('https://clinicaltrials.gov/study/' + nct, nct)} — déclaré dans la notice PubMed"
                        + ("" if present else " (essai pas encore dans la mémoire de l'outil)"))
    for nct in d.get("nct_mentionnes_texte") or []:
        present = next((x for x in essais_memoire if x["nct"] == nct), None)
        elements.append(f"{badge('lien possible, à vérifier', 'verifier')} {lien('https://clinicaltrials.gov/study/' + nct, nct)}"
                        " — numéro cité dans le résumé seulement, pas dans la métadonnée"
                        + ("" if present else " (essai pas encore dans la mémoire de l'outil)"))
    if not elements:
        elements.append(manque("Aucun essai lié identifié"))
    blocs.append(section("Essai clinique lié", liste(elements), badge("PubMed (DataBankList et texte)")))

    # --- Promoteur, financeur, affiliations
    confirmes = [x for x in essais_memoire if x["nct"] in (d.get("nct_declares") or [])]
    if confirmes:
        promoteur = "".join(f"<p><strong>{e(x['promoteur'])}</strong> — essai {e(x['nct'])} (lien confirmé)</p>" for x in confirmes)
    else:
        possibles = ", ".join(d.get("nct_mentionnes_texte") or [])
        promoteur = (f"<p>{manque('Non affiché : aucun essai lié de façon confirmée')}</p>"
                     + (f"<p><small>L'essai {e(possibles)} est seulement cité dans le résumé ; son promoteur "
                        "sera affiché si le lien est confirmé.</small></p>" if possibles else ""))
    financements = annexes.get("financements")
    if financements:
        fin = []
        for f in financements:
            genre = "confirme" if f["statut"].startswith("CONFIRMÉ") else "verifier"
            notices = " · ".join(lien(url, libelle) for libelle, url in f["notices"])
            refs = f" · réf. {e(', '.join(f['references']))}" if f.get("references") else ""
            note = f"<br><small>{e(f['note'])}</small>" if f.get("note") else ""
            fin.append(f"<strong>{e(f['nom'])}</strong> {badge(f['statut'], genre)}{refs}<br><small>{notices}</small>{note}")
        financeur = liste(fin)
    else:
        financeur = f"<p>{manque('Aucun financeur trouvé (PubMed, OpenAlex, Crossref)')}</p>"
        manquants.append("financeur")
    affs = d.get("affiliations_auteurs") or []
    insts = oa.get("institutions") or []
    affil = ""
    if insts:
        affil += "<p><small>Institutions normalisées (OpenAlex) :</small></p>" + liste(
            [f"{e(i['nom'])} <small>({e(i['pays'] or '?')}, {e(TYPES_INSTITUTION.get(i['type'], i['type'] or '?'))})</small>"
             + (" " + badge("entreprise", "verifier") if i["type"] == "company" else "") for i in insts])
    if affs:
        affil += f"<details><summary>Affiliations telles que déclarées dans PubMed ({len(affs)})</summary>{liste([e(a) for a in affs])}</details>"
    if not affil:
        affil = f"<p>{manque()}</p>"
        manquants.append("affiliations des auteurs")
    contenu = f"""<div class="acteurs">
      <div><h3>Promoteur d'essai</h3><p class="def">Organisme responsable d'un essai, déclaré au registre.</p>{promoteur}</div>
      <div><h3>Financeur</h3><p class="def">Organisme qui a financé la recherche, avec la notice qui le justifie.</p>{financeur}</div>
      <div><h3>Affiliations des auteurs</h3><p class="def">Établissements où travaillent les auteurs (pas un financement).</p>{affil}</div>
    </div>"""
    blocs.append(section("Promoteur, financeur et affiliations", contenu,
                         badge("PubMed") + badge("OpenAlex") + badge("Crossref")))
    return entete, blocs, manquants


def texte_copie_article(memoire):
    d = memoire["donnees"]
    annexes = memoire.get("annexes", {})
    et = annexes.get("etiquettes", {})
    fin = annexes.get("financements") or []
    oa = annexes.get("openalex") or {}
    lignes = [
        f"SOURCE : PubMed, PMID {d['pmid']} — {d['lien']}" + (f" · DOI https://doi.org/{d['doi']}" if d.get("doi") else ""),
        "BASE : résumé PubMed uniquement (texte intégral non lu)" if d.get("resume_present") else "BASE : aucun résumé disponible",
        f"Titre : {d['titre']}", f"Revue : {d.get('revue')} · entrée PubMed : {d.get('date_entree_pubmed')}",
        f"Types de publication (PubMed) : {', '.join(d.get('types_publication') or [])}",
        "Produits repérés automatiquement (rôles SUGGÉRÉS, à vérifier) : " + (
            "; ".join(f"{p['produit']} = {p['role']}" for p in et.get("produits_suivis") or []) or "aucun"),
        "Molécules hors liste (repérage automatique, à vérifier) : " + (
            "; ".join(f"{m['molecule']} = {m['role']}" for m in et.get("molecules_hors_liste") or []) or "aucune"),
        "Essai lié : " + (", ".join(d.get("nct_declares") or []) + " (confirmé)" if d.get("nct_declares") else
                          (", ".join(d.get("nct_mentionnes_texte") or []) + " (cité dans le résumé seulement, à vérifier)"
                           if d.get("nct_mentionnes_texte") else "aucun")),
        "Financeurs : " + ("; ".join(f"{f['nom']} [{f['statut']}]" for f in fin) or "aucun trouvé"),
        "Affiliations (institutions, pas des financeurs) : " + ("; ".join(
            f"{i['nom']} ({i['pays']}, {i['type']})" for i in oa.get("institutions") or []) or "voir PubMed"),
        "", "RÉSUMÉ (texte source) :", d.get("resume") or "non disponible",
    ]
    return "\n".join(lignes)


# ------------------------------------------------------------ consigne et page

CONSIGNE = """Tu es assistant de veille scientifique sur le glaucome. À partir UNIQUEMENT des informations ci-dessous, rédige en français une fiche de synthèse avec ces rubriques :
1. Question étudiée
2. Traitement ou technologie
3. Type d'étude
4. Population et nombre de participants
5. Comparateur
6. Critères évalués
7. Principaux résultats chiffrés (recopie les valeurs exactes et indique leur source)
8. Données de tolérance
9. Limites
10. Intérêt potentiel pour une veille marketing — présenté comme une INTERPRÉTATION, séparé des faits
11. À retenir (une phrase)

Règles :
- N'invente rien. Si une information manque, écris « non rapporté ».
- Distingue un essai simplement enregistré, un protocole, des résultats déposés dans un registre et une publication de résultats.
- Si la source est seulement le résumé d'un article, indique que la synthèse repose uniquement sur ce résumé.
- Les rôles « suggérés » (traitement étudié / comparateur) sont à vérifier dans le texte source.
- Ne confonds pas promoteur d'essai, financeur et affiliation des auteurs.
- Termine par la liste des points à vérifier.

=== INFORMATIONS ==="""


STYLE = """
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap");
:root{--fond:#f4f7fb;--carte:#fff;--texte:#0f1d33;--doux:#52627a;--bord:#e2e8f0;--accent:#0b4f8a;
--ok:#146c43;--ok-fond:#e3f4ea;--att:#8a5300;--att-fond:#fdf1d8;--ver:#b42318;--ver-fond:#fdeceb;
--reg:#3f3c9e;--reg-fond:#ecebfb;--src-fond:#f1f5f9;--mark:#fff1a8;--manque:#b42318;--turquoise:#14b8a6;}
@media (prefers-color-scheme:dark){:root{--fond:#0a1120;--carte:#101a2c;--texte:#e6edf7;--doux:#9db0ca;
--bord:#1e2b42;--accent:#6fb4ff;--ok:#6fd6a0;--ok-fond:#12301f;--att:#f3c15e;--att-fond:#352a10;--ver:#ff9a8f;
--ver-fond:#3a1714;--reg:#b4b2ff;--reg-fond:#24234a;--src-fond:#0d1626;--mark:#5a4d10;--manque:#ff9a8f;--turquoise:#2dd4bf;}}
*{box-sizing:border-box}body{margin:0;background:var(--fond);color:var(--texte);
font:15.5px/1.6 "Inter",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
:focus-visible{outline:3px solid var(--turquoise);outline-offset:2px;border-radius:6px}
main{max-width:1000px;margin:0 auto;padding:20px 18px 64px}
.bandeau{display:flex;align-items:center;gap:10px;font-weight:800;letter-spacing:-.02em;padding:6px 0 14px;color:var(--texte);text-decoration:none}
.bandeau i{width:30px;height:30px;border-radius:9px;background:linear-gradient(135deg,#0b4f8a,#14b8a6);display:inline-block}
header,section{background:var(--carte);border:1px solid var(--bord);border-radius:16px;padding:20px 24px;margin:0 0 16px;
box-shadow:0 1px 2px rgba(15,29,51,.04),0 6px 20px -8px rgba(15,29,51,.12)}
h1{font-size:1.45rem;line-height:1.3;margin:.2em 0 .5em}h2{font-size:1.1rem;margin:0 0 .6em;color:var(--accent)}
h3{font-size:1rem;margin:1.1em 0 .4em}.surtitre{color:var(--doux);margin:0;font-size:.9rem}
a{color:var(--accent)}small,.def{color:var(--doux)}.def{font-size:.88rem;margin:.2em 0 .6em}
.grille{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;margin:12px 0 0}
.grille dt{color:var(--doux)}.grille dd{margin:0}
.badge{display:inline-block;font-size:.72rem;font-weight:600;padding:2px 8px;border-radius:999px;margin:2px 4px 2px 0;
vertical-align:middle;background:var(--src-fond);color:var(--doux)}
.badge.confirme{background:var(--ok-fond);color:var(--ok)}.badge.attente{background:var(--att-fond);color:var(--att)}
.badge.verifier{background:var(--ver-fond);color:var(--ver)}.badge.regle{background:var(--reg-fond);color:var(--reg)}
.rubrique{font-weight:600}.manque{color:var(--manque);font-style:italic}
mark{background:var(--mark);color:inherit;padding:0 2px;border-radius:3px}
blockquote{margin:.5em 0;padding:.5em .9em;border-left:3px solid var(--bord);background:var(--src-fond);border-radius:0 6px 6px 0}
pre{white-space:pre-wrap;font-size:.85rem;background:var(--src-fond);padding:10px;border-radius:6px}
.defile{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.92rem;margin:.4em 0}
th,td{border:1px solid var(--bord);padding:6px 8px;text-align:left;vertical-align:top}th{background:var(--src-fond)}
.analyse{background:var(--src-fond);padding:6px 10px;border-radius:6px;font-size:.92rem}
.acteurs{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.acteurs>div{border:1px solid var(--bord);border-radius:8px;padding:10px 12px}.acteurs h3{margin-top:0}
.copier{position:sticky;top:0;z-index:2;display:flex;gap:12px;align-items:center;flex-wrap:wrap;
background:var(--fond);padding:10px 0;margin-bottom:8px}
button{font:inherit;font-weight:600;background:var(--accent);color:#fff;border:0;border-radius:8px;padding:9px 16px;cursor:pointer}
@media (prefers-color-scheme:dark){button{color:#10141a}}
textarea{width:100%;min-height:260px;font:13px/1.4 ui-monospace,Consolas,monospace;background:var(--src-fond);
color:var(--texte);border:1px solid var(--bord);border-radius:6px;padding:8px}
details{margin:.5em 0}summary{cursor:pointer;color:var(--accent)}
.retour{font-size:.92rem;margin:0 0 4px}
@media (max-width:600px){.grille{grid-template-columns:1fr}.grille dt{margin-top:6px}header,section{padding:14px}}
"""

SCRIPT = """
function copierFiche(){
  var zone=document.getElementById('a-copier'), bouton=document.getElementById('bouton-copier');
  function fait(){bouton.textContent='Copié ✓ — collez dans Claude ou ChatGPT';setTimeout(function(){bouton.textContent='Copier pour Claude / ChatGPT'},3000);}
  function secours(){zone.parentElement.open=true;zone.select();try{document.execCommand('copy');fait();}
    catch(err){bouton.textContent='Sélectionnez le texte ci-dessous puis Ctrl+C';}}
  if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(zone.value).then(fait,secours);}else{secours();}
}
"""


NAVIGATION = ('<a class="bandeau" href="../index.html"><i aria-hidden="true"></i>Glaucoma Intelligence</a>'
              '<nav class="retour"><a href="../index.html">Accueil</a> · <a href="../etudes.html">← Essais &amp; articles</a>'
              ' · <a href="../recherche.html">Rechercher</a> · <a href="../carte.html">Carte des acteurs</a>'
              ' · <a href="../alertes.html">Alertes</a></nav>')


def page(titre_onglet, entete, blocs, manquants, texte_copie, genere_le, retour=False):
    manque_html = (liste([e(m) for m in manquants]) if manquants
                   else "<p>Toutes les rubriques ont au moins une information.</p>")
    analyse = section("Limites, intérêt pour la veille marketing, à retenir",
                      f"<p>{manque(ANALYSE_NON_REDIGEE)}</p>", badge("non produit par l'outil", "attente"))
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(titre_onglet)}</title><style>{STYLE}</style></head>
<body><main>
{NAVIGATION if retour else ""}
<div class="copier"><button id="bouton-copier" type="button" onclick="copierFiche()">Copier pour Claude / ChatGPT</button>
<small>Copie une consigne + les faits de cette fiche, à coller dans votre assistant.</small></div>
{entete}
{''.join(blocs)}
{section("Ce qui manque", manque_html, badge("calculé par l'outil", "regle"))}
{analyse}
<section><details><summary>Voir le texte copié par le bouton</summary>
<textarea id="a-copier" readonly>{html.escape(CONSIGNE + chr(10) + texte_copie)}</textarea></details></section>
<p><small>Fiche générée le {e(genere_le)} par Glaucoma Intelligence. Extraits des sources en langue originale.</small></p>
</main><script>{SCRIPT}</script></body></html>"""
