"""Cartographie : graphe essais ↔ traitements ↔ organismes ↔ publications, exporté en JSON pour Cytoscape.js.

Règle : CHAQUE LIEN VIENT D'UNE DONNÉE DÉCLARÉE PAR UNE SOURCE, jamais d'une déduction de l'outil.

Nœuds :
  essai        un essai ClinicalTrials.gov de la base (ou cité par un article, hors base)
  traitement   une intervention déclarée au registre (médicament, dispositif, procédure…)
  organisme    promoteur ou collaborateur d'essai, financeur d'une publication
  publication  un article PubMed relié à au moins un autre nœud

Liens (type → source de la donnée) :
  promoteur     essai → organisme      ClinicalTrials.gov (leadSponsor)
  collaborateur essai → organisme      ClinicalTrials.gov (collaborators)
  intervention  essai → traitement     ClinicalTrials.gov (interventions)
  cite_essai    publication → essai    PubMed (DataBankList : NCT déclaré) ou registre (références de l'essai)
  financeur     publication → organisme PubMed (GrantList) ou Crossref (financeur déclaré par l'éditeur)
"""
import json
import re

TYPES_INTERVENTION = {"DRUG": "médicament", "DEVICE": "dispositif", "PROCEDURE": "procédure", "BIOLOGICAL": "biologique",
                      "COMBINATION_PRODUCT": "produit combiné", "DIAGNOSTIC_TEST": "test diagnostique",
                      "BEHAVIORAL": "comportemental", "RADIATION": "rayonnement", "DIETARY_SUPPLEMENT": "complément",
                      "GENETIC": "génétique", "OTHER": "autre"}
# Dosages (« 0.02% », « 50 µg/mL ») et formes galéniques génériques, retirés pour regrouper les variantes.
# Attention : pas de \b après « % » (ce n'est pas un caractère de mot) — bug détecté par tests/test_graphe.py.
DOSAGE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|(?:mg|µg|mcg|ml|microgram\w*)\b)(?:\s*/\s*ml\b)?|"
                    r"\bophthalmic (?:solution|suspension|emulsion)\b|\beye ?drops?\b", re.I)


def cle_traitement(nom):
    """Regroupe les variantes d'écriture d'un même traitement (casse, dosage, « ophthalmic solution »)."""
    simple = DOSAGE.sub(" ", nom or "")
    return " ".join(re.sub(r"[^\w+/-]", " ", simple.lower()).split()) or (nom or "").lower()


def cle_organisme(nom):
    return " ".join(re.sub(r"[^\w&-]", " ", (nom or "").lower()).split())


def construire(conn):
    noeuds, liens = {}, {}

    def noeud(id_, type_, label, **attrs):
        n = noeuds.setdefault(id_, {"id": id_, "type": type_, "label": label, "degre": 0, **attrs})
        return n

    def lien(source, cible, type_, origine):
        cle = (source, cible, type_)
        if cle not in liens and source != cible:
            liens[cle] = {"id": f"e{len(liens)}", "source": source, "target": cible, "type": type_, "origine": origine}

    essais_base = set()
    for e in conn.execute("SELECT nct, donnees FROM essais"):
        d = json.loads(e["donnees"])
        nct = e["nct"]
        essais_base.add(nct)
        noeud(nct, "essai", nct, titre=d.get("titre"), statut=d.get("statut"),
              phase="/".join(d.get("phases_declarees") or []) or None, fiche=f"fiches/{nct}.html", lien=d.get("lien"))
        if d.get("promoteur"):
            o = "org:" + cle_organisme(d["promoteur"])
            noeud(o, "organisme", d["promoteur"], industriel=d.get("type_promoteur") == "INDUSTRY")
            lien(nct, o, "promoteur", "ClinicalTrials.gov")
        for c in d.get("collaborateurs") or []:
            o = "org:" + cle_organisme(c)
            noeud(o, "organisme", c)
            lien(nct, o, "collaborateur", "ClinicalTrials.gov")
        for i in d.get("interventions") or []:
            if not i.get("nom"):
                continue
            t = "trt:" + cle_traitement(i["nom"])
            noeud(t, "traitement", i["nom"], categorie=TYPES_INTERVENTION.get(i.get("type"), i.get("type")))
            lien(nct, t, "intervention", "ClinicalTrials.gov")
        for p in d.get("publications_declarees") or []:  # références déclarées au registre
            if p.get("pmid"):
                lien("pmid:" + p["pmid"], nct, "cite_essai", "ClinicalTrials.gov (références)")

    for a in conn.execute("SELECT pmid, donnees, annexes FROM articles WHERE origine = 'pubmed'"):
        d, ann = json.loads(a["donnees"]), json.loads(a["annexes"])
        p = "pmid:" + a["pmid"]
        for nct in d.get("nct_declares") or []:
            if nct not in essais_base:
                noeud(nct, "essai", nct, hors_base=True, lien=f"https://clinicaltrials.gov/study/{nct}")
            lien(p, nct, "cite_essai", "PubMed (DataBankList)")
        for f in ann.get("financements") or []:
            if f.get("nom") and str(f.get("statut", "")).startswith("CONFIRMÉ"):
                o = "org:" + cle_organisme(f["nom"])
                noeud(o, "organisme", f["nom"])
                lien(p, o, "financeur", "PubMed / Crossref")
        if any(l["source"] == p for l in liens.values()):
            noeud(p, "publication", f"PMID {a['pmid']}", titre=d.get("titre"), fiche=f"fiches/{a['pmid']}.html",
                  lien=f"https://pubmed.ncbi.nlm.nih.gov/{a['pmid']}/")

    # On ne garde que les liens dont les deux extrémités existent (ex. PMID déclaré au registre mais absent de la base)
    aretes = [l for l in liens.values() if l["source"] in noeuds and l["target"] in noeuds]
    for l in aretes:
        noeuds[l["source"]]["degre"] += 1
        noeuds[l["target"]]["degre"] += 1
    return {"noeuds": list(noeuds.values()), "liens": aretes}


def statistiques(graphe):
    par_type = {}
    for n in graphe["noeuds"]:
        par_type[n["type"]] = par_type.get(n["type"], 0) + 1
    liens_type = {}
    for l in graphe["liens"]:
        liens_type[l["type"]] = liens_type.get(l["type"], 0) + 1
    return {"noeuds": len(graphe["noeuds"]), "liens": len(graphe["liens"]), "noeuds_par_type": par_type,
            "liens_par_type": liens_type}
