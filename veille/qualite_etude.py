"""Grille « Qualité de l'étude » : un repère simple pour juger la solidité d'un article, sans IA.

Règles fixes, lues dans les types de publication déclarés par PubMed, le titre et le résumé :
1. le TYPE D'ÉTUDE place l'article sur la « pyramide des preuves » (niveau 1 = le plus solide) ;
2. des CRITÈRES complètent : tirage au sort, insu (« aveugle »), groupe de comparaison, plusieurs centres,
   nombre de participants, essai enregistré, financement par un laboratoire.
Chaque critère dit ce qui a été trouvé et où. Ce n'est pas un verdict : un résumé ne dit pas tout.
"""
import re

# (niveau, libellé court, explication simple)
NIVEAUX = {
    1: ("Méta-analyse ou revue systématique", "Rassemble plusieurs études sur la même question : c'est le niveau de preuve le plus élevé."),
    2: ("Essai randomisé", "Les patients sont tirés au sort entre les traitements : on peut attribuer l'effet au traitement."),
    3: ("Essai ou étude comparative non randomisée", "Compare des traitements, mais sans tirage au sort : d'autres facteurs peuvent jouer."),
    4: ("Étude observationnelle", "Observe des patients sans leur attribuer de traitement (cohorte, étude rétrospective…) : montre un lien, pas une cause."),
    5: ("Cas clinique, avis ou revue narrative", "Un cas isolé, une opinion ou une synthèse non systématique : à lire comme une piste."),
}
PRECLINIQUE = ("Recherche préclinique (animal ou laboratoire)", "Étude sur l'animal ou en laboratoire : utile pour comprendre, pas encore une preuve chez l'humain.")
FORCE = {1: "Preuve forte", 2: "Preuve forte", 3: "Preuve moyenne", 4: "Preuve limitée", 5: "Preuve faible"}

MOTS = {
    "meta": r"meta-?analys|systematic review|network meta",
    "rct": r"\brandomi[sz]ed\b|\brandomly (assigned|allocated)|\brct\b",
    "essai": r"\bclinical trial\b|\bphase (i|ii|iii|iv|[1-4])\b|prospective(ly)? (interventional|trial)|\btrial\b",
    "comparatif": r"\bcompar(ed|ing|ative|ison)\b|\bversus\b|\bvs\.?\b",
    "observ": r"\bcohort\b|retrospective|cross-sectional|case-control|\bregistry\b|observational|population-based|real-world|chart review",
    "cas": r"case report|case series|\ba case of\b|\bwe (report|present|describe) (a|an|two|three)\b",
    "titre_revue": r"\breview\b|\badvances?\b|\bupdate\b|\bexpert\b|\bconsensus\b|\brecommendations?\b|\bguidelines?\b|"
                   r"\bcurrent (concepts|perspectives|status)\b|\bemerging\b|\bnarrative\b|\bstate of the art\b|\bprimer\b|: a review",
    "avis": r"\beditorial\b|\bcommentary\b|\bperspective\b|narrative review|\breview of the literature\b|\boverview\b",
    "preclin": r"\b(mice|mouse|murine|rats?|rabbits?|porcine|zebrafish|primates?|in vitro|cell line|cultured cells|ex vivo|animal model)\b",
    "aveugle": r"double[- ]blind|single[- ]blind|triple[- ]blind|\bmasked\b|\bblinded\b",
    "controle": r"placebo|control group|\bcontrols?\b|sham|vehicle|\bversus\b|\bvs\.?\b|compared (with|to)",
    "multicentre": r"multi-?cent(er|re)|multi-?site|\b\d+ (centers|centres|sites|hospitals)\b|multinational",
}
UNITES = r"(patients|participants|subjects|individuals|eyes|people|adults|children|persons|cases|women|men)"


def _cherche(cle, texte):
    return re.search(MOTS[cle], texte, re.I) is not None


def participants(texte):
    """Plus grand effectif écrit dans le résumé (« n = 120 », « 1 234 patients »), ou None."""
    nombres = []
    for m in re.finditer(r"\b[nN]\s*=\s*(\d[\d,\s]{0,8}\d|\d)\b", texte):
        nombres.append(m.group(1))
    for m in re.finditer(r"\b(\d{1,3}(?:[ ,]\d{3})+|\d+)\s+(?:\w+\s){0,2}" + UNITES + r"\b", texte, re.I):
        nombres.append(m.group(1))
    valeurs = []
    for n in nombres:
        try:
            v = int(re.sub(r"[ ,]", "", n))
        except ValueError:
            continue
        if 2 <= v <= 50_000_000:
            valeurs.append(v)
    return max(valeurs) if valeurs else None


def evaluer(d, financement_industriel=False):
    types = " ".join(d.get("types_publication") or [])
    titre, resume = d.get("titre") or "", d.get("resume") or ""
    texte = f"{titre}\n{resume}"
    tt = f"{types}\n{texte}"

    # 1. Type d'étude → niveau (types PubMed d'abord, puis mots du titre et du résumé)
    if re.search(r"Meta-Analysis|Systematic Review", types) or _cherche("meta", titre) or _cherche("meta", resume[:400]):
        niveau, source = 1, "type d'étude"
    elif "Randomized Controlled Trial" in types or _cherche("rct", texte):
        niveau, source = 2, "type d'étude"
    elif "Case Reports" in types or _cherche("cas", texte):
        niveau, source = 5, "type d'étude"
    elif _cherche("preclin", texte) and not re.search(r"\bpatients?\b", texte, re.I):
        niveau, source = 0, "type d'étude"
    elif re.search(r"Clinical Trial|Comparative Study|Equivalence Trial", types) or (_cherche("essai", texte) and _cherche("comparatif", texte)):
        niveau, source = 3, "type d'étude"
    elif "Observational Study" in types or _cherche("observ", texte):
        niveau, source = 4, "type d'étude"
    elif re.search(r"Review|Editorial|Letter|Comment", types) or _cherche("avis", texte) or _cherche("titre_revue", titre):
        niveau, source = 5, "type d'étude"
    else:
        niveau, source = None, "type non identifiable"
    libelle, explication = PRECLINIQUE if niveau == 0 else NIVEAUX.get(niveau, ("Type d'étude non identifié", "Le résumé ne permet pas de classer l'étude."))

    n = participants(resume)
    criteres = [
        ("Tirage au sort", _cherche("rct", tt), "les patients sont répartis au hasard entre les groupes"),
        ("Insu (« aveugle »)", _cherche("aveugle", texte), "patients et/ou médecins ne savent pas qui reçoit quoi"),
        ("Groupe de comparaison", _cherche("controle", texte), "placebo, autre traitement ou groupe témoin"),
        ("Plusieurs centres", "Multicenter" in types or _cherche("multicentre", texte), "résultats moins dépendants d'une seule équipe"),
        ("Essai enregistré", bool(d.get("nct_declares") or d.get("nct_mentionnes_texte")), "le protocole a été déclaré à l'avance dans un registre"),
    ]
    return {
        "niveau": niveau, "libelle": libelle, "explication": explication,
        "force": "Recherche préclinique" if niveau == 0 else FORCE.get(niveau, "Non évaluable"),
        "participants": n,
        "taille": None if n is None else ("grand effectif" if n >= 300 else "effectif moyen" if n >= 100 else "petit effectif"),
        "criteres": [{"nom": c, "present": bool(p), "pourquoi": w} for c, p, w in criteres],
        "financement_industriel": bool(financement_industriel),
        "prepublication": "Preprint" in types,
        "resume_present": bool(resume),
    }


def bloc_html(q):
    """Section « Qualité de l'étude » d'une fiche article."""
    from html import escape as e
    marche = "".join(
        f'<li class="pyr-{k}{" actif" if q["niveau"] == k else ""}"><b>{k}</b> {e(NIVEAUX[k][0])}</li>' for k in range(1, 6))
    crit = "".join(
        f'<li class="{"oui" if c["present"] else "non"}"><span>{"✓" if c["present"] else "–"}</span> <strong>{e(c["nom"])}</strong>'
        f' <small>{e(c["pourquoi"])}</small></li>' for c in q["criteres"])
    taille = (f'<li class="oui"><span>👥</span> <strong>{q["participants"]:,} participants</strong> <small>{e(q["taille"])}, '
              "nombre lu dans le résumé</small></li>".replace(",", " ") if q["participants"]
              else '<li class="non"><span>?</span> <strong>Nombre de participants</strong> <small>non trouvé dans le résumé</small></li>')
    alertes = []
    if q["financement_industriel"]:
        alertes.append("💼 Financée ou co-signée par un laboratoire : à garder en tête en lisant les conclusions.")
    if q["prepublication"]:
        alertes.append("⏳ Prépublication : pas encore relue par d'autres chercheurs.")
    if not q["resume_present"]:
        alertes.append("Aucun résumé : grille impossible à remplir.")
    return (f'<section class="qualite-etude" id="qualite-etude"><h2>Qualité de l\'étude <small>repère calculé par des règles, à partir du résumé</small></h2>'
            f'<div class="qe-grille"><div><p class="qe-force qe-n{q["niveau"] if q["niveau"] is not None else "x"}">{e(q["force"])}</p>'
            f'<p><strong>{e(q["libelle"])}</strong><br>{e(q["explication"])}</p>'
            f'<ol class="pyramide">{marche}</ol></div>'
            f'<div><ul class="qe-criteres">{crit}{taille}</ul>'
            + "".join(f'<p class="qe-alerte">{e(a)}</p>' for a in alertes) +
            '<p class="cm-aide">Un critère « – » veut dire qu\'il n\'apparaît pas dans le résumé : il peut exister dans l\'article complet.</p>'
            "</div></div></section>")


STYLE = """
.qualite-etude h2 small{font-weight:400;font-size:.8rem;color:var(--doux);margin-left:6px}
.qe-grille{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr));gap:18px}
.qe-force{display:inline-block;font-weight:800;border-radius:999px;padding:4px 14px;margin:0 0 8px;color:#fff;background:#64748b}
.qe-n1,.qe-n2{background:#146c43}.qe-n3{background:#a16207}.qe-n4{background:#c2410c}.qe-n5{background:#b42318}.qe-n0{background:#4f46e5}
.pyramide{list-style:none;padding:0;margin:10px 0 0;display:grid;gap:4px;justify-items:center}
.pyramide li{background:var(--carte-2);border:1px solid var(--bord);border-radius:6px;padding:4px 8px;font-size:.8rem;color:var(--doux);text-align:center}
.pyramide li b{color:var(--texte);margin-right:4px}
.pyramide .pyr-1{width:52%}.pyramide .pyr-2{width:64%}.pyramide .pyr-3{width:76%}.pyramide .pyr-4{width:88%}.pyramide .pyr-5{width:100%}
.pyramide li.actif{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:700}.pyramide li.actif b{color:#fff}
.qe-criteres{list-style:none;padding:0;margin:0;display:grid;gap:6px}
.qe-criteres li{display:grid;grid-template-columns:22px 1fr;column-gap:6px;font-size:.9rem}
.qe-criteres li small{grid-column:2;color:var(--doux)}
.qe-criteres li span{font-weight:800;text-align:center}
.qe-criteres li.oui span{color:#146c43}.qe-criteres li.non{opacity:.75}
.qe-alerte{background:var(--att-fond);border-radius:8px;padding:6px 10px;margin:8px 0 0;font-size:.88rem}
@media (prefers-color-scheme:dark){.pyramide li.actif{color:#0a1120}.pyramide li.actif b{color:#0a1120}.qe-criteres li.oui span{color:#6fd6a0}}
"""
