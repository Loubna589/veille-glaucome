"""Récupération des essais sur ClinicalTrials.gov (API v2, gratuite, sans clé).

Deux fonctions principales :
- rechercher() : interroge l'API et renvoie les essais bruts (format JSON de la source) ;
- normaliser() : garde uniquement les champs utiles à la veille, sous un format stable.

Règle de la veille : on n'invente rien. Une information absente de la source
vaut None dans les données, et s'affiche « non rapporté ».
"""
from veille import reseau

API = "https://clinicaltrials.gov/api/v2/studies"
# Cherché dans le champ « conditions » des essais. Les guillemets sont indispensables :
# sans eux, « hypertension » seul ramène par exemple l'hypertension intracrânienne.
CONDITION = 'glaucoma OR "ocular hypertension"'
DELAI_MAX = 30

# Libellés français. On garde toujours aussi le code d'origine de la source.
PHASES = {
    "EARLY_PHASE1": "Phase précoce 1",
    "PHASE1": "Phase 1",
    "PHASE2": "Phase 2",
    "PHASE3": "Phase 3",
    "PHASE4": "Phase 4",
    "NA": "Non applicable (déclaré)",
}
STATUTS = {
    "NOT_YET_RECRUITING": "Pas encore en recrutement",
    "RECRUITING": "Recrutement en cours",
    "ENROLLING_BY_INVITATION": "Recrutement sur invitation",
    "ACTIVE_NOT_RECRUITING": "Actif, recrutement terminé",
    "COMPLETED": "Terminé",
    "SUSPENDED": "Suspendu",
    "TERMINATED": "Arrêté prématurément",
    "WITHDRAWN": "Retiré avant inclusion",
    "UNKNOWN": "Inconnu (non mis à jour)",
    "AVAILABLE": "Accès élargi disponible",
    "NO_LONGER_AVAILABLE": "Accès élargi terminé",
    "TEMPORARILY_NOT_AVAILABLE": "Accès élargi suspendu",
    "APPROVED_FOR_MARKETING": "Autorisé à la commercialisation",
    "WITHHELD": "Non communiqué",
}
TYPES_ETUDE = {
    "INTERVENTIONAL": "Interventionnelle",
    "OBSERVATIONAL": "Observationnelle",
    "EXPANDED_ACCESS": "Accès élargi",
}
TYPES_INTERVENTION = {
    "DRUG": "Médicament",
    "DEVICE": "Dispositif",
    "PROCEDURE": "Procédure / chirurgie",
    "BIOLOGICAL": "Biologique",
    "BEHAVIORAL": "Comportementale",
    "DIAGNOSTIC_TEST": "Test diagnostique",
    "DIETARY_SUPPLEMENT": "Complément alimentaire",
    "GENETIC": "Génétique",
    "RADIATION": "Rayonnement",
    "COMBINATION_PRODUCT": "Produit combiné",
    "OTHER": "Autre",
}


def rechercher(filtre=None, max_resultats=10, tri="LastUpdatePostDate:desc"):
    """Renvoie jusqu'à `max_resultats` essais bruts sur le glaucome / l'hypertension oculaire.

    `filtre` utilise la syntaxe avancée de l'API, par exemple "AREA[Phase]PHASE3".
    Les pages de résultats sont suivies automatiquement (jeton nextPageToken).
    """
    params = {
        "query.cond": CONDITION,
        "pageSize": min(max_resultats, 1000),
        "sort": tri,
        "format": "json",
    }
    if filtre:
        params["filter.advanced"] = filtre

    essais = []
    while len(essais) < max_resultats:
        donnees = reseau.lire_json(reseau.requete("GET", API, "ClinicalTrials.gov", params=params, timeout=DELAI_MAX),
                                   "ClinicalTrials.gov")
        essais.extend(donnees.get("studies", []))
        if not donnees.get("nextPageToken"):
            break
        params["pageToken"] = donnees["nextPageToken"]
    return essais[:max_resultats]


def par_nct(ncts):
    """Récupère des essais précis par leur numéro NCT, en un seul appel (jusqu'à 1 000)."""
    if not ncts:
        return []
    params = {"filter.ids": ",".join(ncts), "pageSize": 1000, "format": "json"}
    reponse = reseau.requete("GET", API, "ClinicalTrials.gov", params=params, timeout=DELAI_MAX)
    return reseau.lire_json(reponse, "ClinicalTrials.gov").get("studies", [])


def _resultats(etude):
    """Extrait les résultats DÉPOSÉS au registre, valeurs recopiées telles quelles."""
    r = etude.get("resultsSection")
    if not r:
        return None

    criteres = []
    for o in r.get("outcomeMeasuresModule", {}).get("outcomeMeasures", []):
        groupes = {g["id"]: g.get("title") for g in o.get("groups", [])}
        effectifs = {c["groupId"]: c.get("value")
                     for d in o.get("denoms", [])[:1] for c in d.get("counts", [])}
        valeurs = []
        for classe in o.get("classes", []):
            for categorie in classe.get("categories", []):
                for m in categorie.get("measurements", []):
                    valeurs.append({
                        "groupe": groupes.get(m.get("groupId")),
                        "sous_groupe": " / ".join(filter(None, [classe.get("title"), categorie.get("title")])) or None,
                        "valeur": m.get("value"),
                        "dispersion": m.get("spread"),
                        "borne_basse": m.get("lowerLimit"),
                        "borne_haute": m.get("upperLimit"),
                        "effectif_analyse": effectifs.get(m.get("groupId")),
                    })
        criteres.append({
            "type": o.get("type"),  # PRIMARY, SECONDARY, OTHER_PRE_SPECIFIED, POST_HOC
            "titre": o.get("title"),
            "description": o.get("description"),
            "delai": o.get("timeFrame"),
            "parametre": o.get("paramType"),
            "dispersion_type": o.get("dispersionType"),
            "unite": o.get("unitOfMeasure"),
            "population": o.get("populationDescription"),
            "valeurs": valeurs or None,
            "analyses": [{
                "groupes": [groupes.get(g) for g in a.get("groupIds", [])],
                "p": a.get("pValue"),
                "methode": a.get("statisticalMethod"),
                "parametre": a.get("paramType"),
                "estimation": a.get("paramValue"),
                "ic_pct": a.get("ciPctValue"),
                "ic_bas": a.get("ciLowerLimit"),
                "ic_haut": a.get("ciUpperLimit"),
                "hypothese": a.get("nonInferiorityType"),
            } for a in o.get("analyses", [])] or None,
        })

    ei = r.get("adverseEventsModule", {})
    groupes_ei = {g["id"]: g.get("title") for g in ei.get("eventGroups", [])}

    def evenements(liste):
        return [{
            "terme": e.get("term"),
            "systeme": e.get("organSystem"),
            "par_groupe": [{"groupe": groupes_ei.get(s.get("groupId")), "touches": s.get("numAffected"),
                            "exposes": s.get("numAtRisk")} for s in e.get("stats", [])],
        } for e in liste]

    flux = r.get("participantFlowModule", {})
    groupes_flux = {g["id"]: g.get("title") for g in flux.get("groups", [])}
    etapes = []
    for periode in flux.get("periods", [])[:1]:
        for jalon in periode.get("milestones", []):
            etapes.append({"etape": jalon.get("type"), "par_groupe": [
                {"groupe": groupes_flux.get(a.get("groupId")), "nombre": a.get("numSubjects")}
                for a in jalon.get("achievements", [])]})

    return {
        "flux_participants": etapes or None,
        "criteres": criteres or None,
        "evenements_indesirables": {
            "periode": ei.get("timeFrame"),
            "seuil_frequence_pct": ei.get("frequencyThreshold"),
            "par_groupe": [{"groupe": g.get("title"), "exposes": g.get("seriousNumAtRisk"),
                            "graves": g.get("seriousNumAffected"), "autres": g.get("otherNumAffected"),
                            "deces": g.get("deathsNumAffected")} for g in ei.get("eventGroups", [])],
            "graves": evenements(ei.get("seriousEvents", [])) or None,
            "autres": evenements(ei.get("otherEvents", [])) or None,
        } if ei else None,
    }


def normaliser(etude):
    """Transforme un essai brut de l'API en fiche de données stable pour la veille."""
    p = etude.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    statut = p.get("statusModule", {})
    promoteurs = p.get("sponsorCollaboratorsModule", {})
    design = p.get("designModule", {})
    interventions = p.get("armsInterventionsModule", {}).get("interventions", [])
    criteres = p.get("outcomesModule", {}).get("primaryOutcomes", [])
    effectif = design.get("enrollmentInfo", {})
    references = p.get("referencesModule", {}).get("references", [])
    nct = ident.get("nctId")

    return {
        "nct": nct,
        "titre": ident.get("briefTitle"),
        "titre_officiel": ident.get("officialTitle"),
        "lien": f"https://clinicaltrials.gov/study/{nct}",
        "date_premiere_publication": statut.get("studyFirstPostDateStruct", {}).get("date"),
        "date_derniere_mise_a_jour": statut.get("lastUpdatePostDateStruct", {}).get("date"),
        "type_etude": design.get("studyType"),
        # Liste telle que déclarée (ex. ["PHASE1", "PHASE2"]) ; None si la source ne dit rien
        "phases_declarees": design.get("phases"),
        "statut": statut.get("overallStatus"),
        "raison_arret": statut.get("whyStopped"),
        "date_debut": statut.get("startDateStruct", {}).get("date"),
        "date_fin_principale": statut.get("primaryCompletionDateStruct", {}).get("date"),
        "promoteur": promoteurs.get("leadSponsor", {}).get("name"),
        "type_promoteur": promoteurs.get("leadSponsor", {}).get("class"),  # INDUSTRY, OTHER, NIH...
        "collaborateurs": [c.get("name") for c in promoteurs.get("collaborators", [])] or None,
        "conditions": p.get("conditionsModule", {}).get("conditions"),
        "interventions": [
            {"type": i.get("type"), "nom": i.get("name")} for i in interventions
        ] or None,
        "participants_nombre": effectif.get("count"),
        "participants_type": effectif.get("type"),  # ACTUAL (réel) ou ESTIMATED (prévu)
        "criteres_principaux": [
            {"critere": c.get("measure"), "delai": c.get("timeFrame")} for c in criteres
        ] or None,
        "resultats_deposes": bool(etude.get("hasResults")),
        "publications_declarees": [
            {"pmid": r.get("pmid"), "type": r.get("type")} for r in references if r.get("pmid")
        ] or None,
        "resume_source": p.get("descriptionModule", {}).get("briefSummary"),
        # --- Champs ajoutés pour les fiches (étape 5) ---
        "citations_declarees": [
            {"pmid": r.get("pmid"), "type": r.get("type"), "citation": r.get("citation")}
            for r in references
        ] or None,
        "plan": {
            "repartition": design.get("designInfo", {}).get("allocation"),
            "modele": design.get("designInfo", {}).get("interventionModel"),
            "but_principal": design.get("designInfo", {}).get("primaryPurpose"),
            "insu": design.get("designInfo", {}).get("maskingInfo", {}).get("masking"),
            "insu_pour": design.get("designInfo", {}).get("maskingInfo", {}).get("whoMasked"),
            "insu_description": design.get("designInfo", {}).get("maskingInfo", {}).get("maskingDescription"),
            "modele_observationnel": design.get("designInfo", {}).get("observationalModel"),
        },
        # Bras de l'étude avec leur TYPE DÉCLARÉ (EXPERIMENTAL, ACTIVE_COMPARATOR, PLACEBO_COMPARATOR…)
        "bras": [
            {"libelle": b.get("label"), "type": b.get("type"), "description": b.get("description"),
             "interventions": b.get("interventionNames")}
            for b in p.get("armsInterventionsModule", {}).get("armGroups", [])
        ] or None,
        "eligibilite": {
            "criteres": p.get("eligibilityModule", {}).get("eligibilityCriteria"),
            "age_min": p.get("eligibilityModule", {}).get("minimumAge"),
            "age_max": p.get("eligibilityModule", {}).get("maximumAge"),
            "sexe": p.get("eligibilityModule", {}).get("sex"),
            "volontaires_sains": p.get("eligibilityModule", {}).get("healthyVolunteers"),
        },
        "criteres_secondaires": [
            {"critere": c.get("measure"), "delai": c.get("timeFrame")}
            for c in p.get("outcomesModule", {}).get("secondaryOutcomes", [])
        ] or None,
        # Responsables déclarés au registre (investigateur, directeur d'étude) et leur affiliation
        "responsables": [
            {"nom": o.get("name"), "affiliation": o.get("affiliation"), "role": o.get("role")}
            for o in p.get("contactsLocationsModule", {}).get("overallOfficials", [])
        ] or None,
        "date_depot_resultats": statut.get("resultsFirstPostDateStruct", {}).get("date"),
        "resultats": _resultats(etude),
    }


# ------------------------------------------------------ affichage en français

def libelle_phase(essai):
    phases = essai.get("phases_declarees")
    if not phases:
        return "Non renseignée"
    return " / ".join(PHASES.get(ph, ph) for ph in phases)


def libelle_statut(essai):
    code = essai.get("statut")
    return STATUTS.get(code, code) if code else "Non rapporté"


def libelle_type_etude(essai):
    code = essai.get("type_etude")
    return TYPES_ETUDE.get(code, code) if code else "Non rapporté"


def libelle_participants(essai):
    nombre = essai.get("participants_nombre")
    if nombre is None:
        return "Non rapporté"
    nature = {"ACTUAL": "réel", "ESTIMATED": "prévu"}.get(essai.get("participants_type"), "nature non précisée")
    return f"{nombre} ({nature})"


def libelle_interventions(essai):
    if not essai.get("interventions"):
        return ["Non rapporté"]
    return [f"{TYPES_INTERVENTION.get(i['type'], i['type'])} : {i['nom']}" for i in essai["interventions"]]


def libelle_resultats(essai):
    return "Oui, déposés au registre" if essai.get("resultats_deposes") else "Non"
