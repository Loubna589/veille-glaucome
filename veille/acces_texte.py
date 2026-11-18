"""« Lire l'article en entier » : trois façons légitimes d'obtenir le texte intégral d'un article.

1. TEXTE INTÉGRAL GRATUIT : seulement un lien DÉCLARÉ par une source.
   - PubMed Central (identifiant PMCID déclaré par PubMed ou OpenAlex) ;
   - version en accès libre déclarée par OpenAlex (statut gold, diamond, hybrid, green ou bronze ; OpenAlex
     reprend les données d'Unpaywall). Aucune adresse n'est devinée.
2. DEMANDER À L'AUTEUR : un e-mail pré-rédigé (lien mailto) vers l'adresse ÉCRITE dans les affiliations PubMed.
   Pas d'adresse trouvée = pas de bouton ; jamais d'adresse inventée. Rien n'est envoyé par l'outil :
   la messagerie s'ouvre, la personne relit et envoie elle-même.
3. DEMANDER À LA BU : lien OpenURL vers le catalogue de la BU (Primo VE, config/site.ini [bu]). Le catalogue reçoit
   la référence (titre, revue, année, DOI, PMID), demande la connexion ENT, puis propose la demande de prêt entre
   bibliothèques (PEB) déjà remplie. En secours : copie de la référence + formulaire PEB vierge.
   La personne se connecte, relit et envoie elle-même : l'outil ne gère aucun identifiant et n'envoie rien.
"""
import configparser
import html
import re
from pathlib import Path
from urllib.parse import quote, urlencode

CONFIG = Path(__file__).resolve().parents[1] / "config" / "site.ini"
MOTIF_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
STATUTS_LIBRES = {"gold", "diamond", "hybrid", "green", "bronze"}


def url_peb(chemin=CONFIG):
    config = configparser.ConfigParser(interpolation=None)
    config.read(chemin, encoding="utf-8")
    return (config.get("bu", "url_peb", fallback="") or "").strip()


def base_openurl(chemin=CONFIG):
    config = configparser.ConfigParser(interpolation=None)
    config.read(chemin, encoding="utf-8")
    return (config.get("bu", "url_openurl", fallback="") or "").strip()


def lien_openurl(d, base):
    """Lien OpenURL 1.0 (KEV) vers le catalogue : les champs sont repris tels que PubMed les déclare."""
    if not base:
        return ""
    params = [("ctx_ver", "Z39.88-2004"), ("rft_val_fmt", "info:ofi/fmt:kev:mtx:journal"), ("rft.genre", "article"),
              ("rft.atitle", d.get("titre") or ""), ("rft.jtitle", d.get("revue") or "")]
    if annee(d):
        params.append(("rft.date", annee(d)))
    if d.get("doi"):
        params += [("rft.doi", d["doi"]), ("rft_id", f"info:doi/{d['doi']}")]
    if d.get("pmid"):
        params += [("rft.pmid", d["pmid"]), ("rft_id", f"info:pmid/{d['pmid']}")]
    return base + ("&" if "?" in base else "?") + urlencode([(k, v) for k, v in params if v])


def lien_researchgate(d):
    """Simple lien de RECHERCHE ResearchGate par titre (pas d'API publique : aucune collecte automatique)."""
    titre = (d.get("titre") or "").strip().rstrip(".")
    return f"https://www.researchgate.net/search/publication?q={quote(titre)}" if titre else ""


def emails_auteurs(affiliations):
    """Adresses écrites dans les affiliations PubMed, dans l'ordre, sans doublon (point final retiré)."""
    vus = []
    for a in affiliations or []:
        for m in MOTIF_EMAIL.findall(a or ""):
            m = m.rstrip(".")
            if m.lower() not in (v.lower() for v in vus):
                vus.append(m)
    return vus


def texte_gratuit(d, oa):
    """(url, libellé) de la meilleure version gratuite déclarée, ou None."""
    pmcid = d.get("pmcid") or oa.get("pmcid")
    if pmcid:
        pmcid = pmcid if str(pmcid).upper().startswith("PMC") else f"PMC{pmcid}"
        return f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/", "PubMed Central"
    libre = oa.get("acces_ouvert") or oa.get("statut_acces") in STATUTS_LIBRES
    url = oa.get("url_pdf") or oa.get("url_texte")
    if libre and url:
        return url, "version en accès libre (OpenAlex)"
    return None


LIBELLES_ACCES = {
    "libre": "✅ Accès libre et gratuit",
    "payant": "🔒 Article payant : à demander",
    "inconnu": "❔ Gratuit ou payant : non indiqué",
}


def statut_acces(d, oa):
    """« libre » (version gratuite déclarée), « payant » (OpenAlex déclare l'article fermé) ou « inconnu »."""
    if texte_gratuit(d, oa):
        return "libre"
    if oa.get("statut_acces") == "closed" or oa.get("acces_ouvert") is False:
        return "payant"
    return "inconnu"


def annee(d):
    m = re.search(r"\d{4}", d.get("date_publication") or "")
    return m.group(0) if m else ""


def mail_auteur(d, email):
    titre, doi = d.get("titre") or "", d.get("doi")
    sujet = f"Request for a copy of your article: {titre[:120]}"
    corps = (
        "Dear Author,\n\n"
        "I am following research on glaucoma, and I read the abstract of your article with great interest:\n\n"
        f"\"{titre}\"\n"
        f"{d.get('revue') or ''}{', ' + annee(d) if annee(d) else ''}\n"
        f"{'DOI: ' + doi + chr(10) if doi else ''}"
        f"PMID: {d.get('pmid')}\n\n"
        "Unfortunately I do not have access to the full text. Would you be willing to share a copy for my personal "
        "study use only? It will not be redistributed.\n\n"
        "Thank you very much for your time.\n\n"
        "Kind regards,\n[Your name]\n"
    )
    return f"mailto:{email}?subject={quote(sujet)}&body={quote(corps)}"


def reference_peb(d):
    """Texte à coller dans le formulaire PEB (type « Article »)."""
    lignes = [
        "Type de référence : Article",
        f"Titre de l'article : {d.get('titre') or ''}",
        f"Revue : {d.get('revue') or 'non rapportée'}",
        f"Année : {annee(d) or 'non rapportée'}",
        f"DOI : {d.get('doi')}" if d.get("doi") else None,
        f"PMID : {d.get('pmid')} (https://pubmed.ncbi.nlm.nih.gov/{d.get('pmid')}/)" if d.get("pmid") else None,
        "Format souhaité : numérique",
    ]
    return "\n".join(l for l in lignes if l)


def bloc_html(d, oa, peb=None, openurl=None):
    """Section « Lire l'article en entier » d'une fiche article."""
    e = html.escape
    peb = url_peb() if peb is None else peb
    openurl = base_openurl() if openurl is None else openurl
    morceaux = []
    statut = statut_acces(d, oa)
    explication = {
        "libre": "Une version gratuite est déclarée : un clic suffit pour lire l'article.",
        "payant": "OpenAlex déclare cet article fermé (abonnement) : demandez-le à l'auteur, sur ResearchGate ou à la BU.",
        "inconnu": "Ni PubMed Central ni OpenAlex ne disent si l'article est gratuit : essayez le lien de l'éditeur, "
                   "sinon demandez-le à l'auteur, sur ResearchGate ou à la BU.",
    }[statut]
    morceaux.append(f'<p class="statut-acces statut-acces--{statut}"><strong>{LIBELLES_ACCES[statut]}</strong><br>'
                    f"<small>{explication} Certains boutons peuvent manquer : « Texte intégral gratuit » n'apparaît que "
                    "si une version gratuite est déclarée, le bouton pour écrire à l'auteur que si PubMed donne son e-mail.</small></p>")
    gratuit = texte_gratuit(d, oa)
    if gratuit:
        morceaux.append(f'<a class="bouton-acces" href="{e(gratuit[0])}" target="_blank" rel="noopener">Texte intégral gratuit</a>'
                        f' <small>{e(gratuit[1])}</small>')
    emails = emails_auteurs(d.get("affiliations_auteurs"))
    if emails:
        morceaux.append(f'<a class="bouton-acces secondaire" href="{e(mail_auteur(d, emails[0]))}">Demander à l\'auteur</a>'
                        f' <small>e-mail pré-rédigé en anglais à {e(emails[0])} (adresse écrite dans PubMed) : '
                        "votre messagerie s'ouvre, vous relisez et envoyez vous-même.</small>")
    rg = lien_researchgate(d)
    if rg:
        morceaux.append(f'<a class="bouton-acces secondaire" href="{e(rg)}" target="_blank" rel="noopener">Chercher sur ResearchGate</a>'
                        "<small> recherche l'article par son titre. S'il y est, connectez-vous avec votre compte et cliquez "
                        "sur « Request full-text » : l'auteur reçoit votre demande.</small>")
    ref = reference_peb(d)
    cible = f' data-url="{e(peb)}"' if peb else ""
    lien_bu = lien_openurl(d, openurl)
    if lien_bu:
        morceaux.append(f'<a class="bouton-acces secondaire" href="{e(lien_bu)}" target="_blank" rel="noopener">Demander à la BU</a>'
                        "<small> ouvre le catalogue de la BU avec la référence de cet article : connectez-vous avec l'ENT, "
                        "choisissez la demande de prêt entre bibliothèques (PEB), relisez et envoyez vous-même.</small>")
        morceaux.append(f'<button type="button" class="lien-secours" onclick="demanderBU(this)"{cible}>Si la référence n\'apparaît pas : '
                        "copier la référence et ouvrir le formulaire PEB vierge</button>"
                        f'<textarea class="ref-peb" hidden readonly>{e(ref)}</textarea>')
    else:
        morceaux.append(f'<button type="button" class="bouton-acces secondaire" onclick="demanderBU(this)"{cible}>Demander à la BU</button>'
                        "<small> copie la référence de l'article, puis ouvre le formulaire de prêt entre bibliothèques : "
                        "connectez-vous, choisissez « Article », collez et envoyez.</small>"
                        f'<textarea class="ref-peb" hidden readonly>{e(ref)}</textarea>')
    return ('<section class="acces"><h2>Lire l\'article en entier</h2>'
            + "".join(f"<p>{m}</p>" if not m.startswith("<p>") else m for m in morceaux) + "</section>")


SCRIPT = """
function demanderBU(b){
  var ref=(b.parentElement.querySelector('.ref-peb')||b.parentElement.parentElement.querySelector('.ref-peb')).value, url=b.getAttribute('data-url'), libelle=b.textContent;
  function fini(ok){b.textContent=ok?'Référence copiée ✓':'Copiez la référence ci-dessous';
    if(!ok){var t=b.parentElement.querySelector('.ref-peb');t.hidden=false;t.select();}
    if(url){window.open(url,'_blank','noopener');}else{b.textContent+=' — ouvrez l’onglet « Demande PEB » du catalogue de la BU';}
    setTimeout(function(){b.textContent=libelle},6000);}
  if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(ref).then(function(){fini(true)},function(){fini(false)});}
  else{fini(false);}
}
"""

STYLE = """
.acces p{margin:.5em 0}.bouton-acces{display:inline-block;font-weight:600;background:var(--accent);color:#fff;border:0;
border-radius:8px;padding:8px 14px;text-decoration:none;cursor:pointer;font:inherit;font-weight:600}
.bouton-acces.secondaire{background:var(--carte);color:var(--accent);border:1.5px solid var(--accent)}
.ref-peb{min-height:140px;margin-top:8px}
.statut-acces{padding:8px 12px;border-radius:8px;border-left:4px solid var(--doux)}
.statut-acces--libre{border-left-color:#2e9d5b;background:rgba(46,157,91,.10)}
.statut-acces--payant{border-left-color:#c2553f;background:rgba(194,85,63,.10)}
.lien-secours{background:none;border:0;padding:0;color:var(--accent);text-decoration:underline;font-weight:400;font-size:.88rem;cursor:pointer}
@media (prefers-color-scheme:dark){.bouton-acces{color:#10141a}.bouton-acces.secondaire{color:var(--accent)}}
"""
