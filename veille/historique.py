"""Mémoire de la veille : un fichier JSON par élément suivi (essai ou article).

Pourquoi un fichier texte par élément ?
- Git (et GitHub Actions) peut conserver et comparer ces fichiers d'un jour à l'autre ;
- on peut les ouvrir et les lire avec n'importe quel éditeur ;
- un fichier n'est réécrit QUE si l'élément a changé : l'historique Git reste propre ;
- le nom du fichier est l'identifiant (NCT ou PMID) : un même élément ne peut
  donc pas être enregistré deux fois.

Contenu d'un fichier (ex. data/historique/essais/NCT01234567.json) :
{
  "nct": "...",                            identifiant (clé « nct » ou « pmid »)
  "premiere_detection": "2026-09-25",      date à laquelle NOTRE outil l'a vu pour la 1re fois
  "derniere_modification_detectee": null,  date du dernier changement repéré par l'outil
  "donnees": {...},                        dernière version connue, TELLE QUE DONNÉE PAR LA SOURCE
  "modifications": [                       journal des changements (le plus ancien d'abord)
    {"date_detection": "...", "resultats_ajoutes": false,
     "champs": {"statut": {"avant": "RECRUITING", "apres": "COMPLETED"}}}
  ],
  "annexes": {...}                         informations calculées par l'outil (étiquettes) ou
                                           venant d'une autre source (enrichissement OpenAlex).
                                           Leur mise à jour n'est PAS une modification de l'élément.
}
"""
import json
import os
from pathlib import Path


def chemin_fichier(dossier, identifiant):
    return Path(dossier) / f"{identifiant}.json"


def charger(dossier, identifiant):
    """Renvoie le fichier mémorisé d'un élément, ou None s'il n'a jamais été vu."""
    chemin = chemin_fichier(dossier, identifiant)
    if not chemin.exists():
        return None
    return json.loads(chemin.read_text(encoding="utf-8"))


def _egal(avant, apres):
    """Égalité qui ignore les sous-champs absents de l'ancienne version (évolution de l'outil)."""
    if isinstance(avant, dict) and isinstance(apres, dict):
        return all(_egal(v, apres.get(k)) for k, v in avant.items())
    return avant == apres


def comparer(avant, apres):
    """Liste les champs qui diffèrent entre deux versions d'un élément.

    Un champ (ou sous-champ) ABSENT de l'ancienne version n'est pas comparé : il vient
    d'une évolution de l'outil (nouveau champ collecté), pas d'un changement de la source.
    """
    return {
        champ: {"avant": avant.get(champ), "apres": apres.get(champ)}
        for champ in sorted(avant)
        if not _egal(avant.get(champ), apres.get(champ))
    }


def enregistrer(dossier, donnees, date_du_jour, cle="nct", annexes=None):
    """Mémorise un élément et indique ce qui s'est passé depuis la dernière exécution.

    `cle` est le nom du champ identifiant : "nct" pour un essai, "pmid" pour un article.
    `annexes` (facultatif) : dictionnaire fusionné dans la partie « annexes » du fichier.

    Renvoie (etat, changements) avec etat parmi :
      "nouveau"             jamais vu auparavant
      "inchange"            déjà vu, rien n'a changé (le fichier n'est pas réécrit)
      "modifie"             déjà vu, au moins un champ a changé
      "resultats_ajoutes"   essai déjà vu, et des résultats viennent d'être déposés au registre
    """
    identifiant = donnees[cle]
    memoire = charger(dossier, identifiant)

    if memoire is None:
        memoire = {
            cle: identifiant,
            "premiere_detection": date_du_jour,
            "derniere_modification_detectee": None,
            "donnees": donnees,
            "modifications": [],
        }
        if annexes:
            memoire["annexes"] = annexes
        _ecrire(dossier, identifiant, memoire)
        return "nouveau", {}

    annexes_changees = False
    if annexes:
        fusion = {**memoire.get("annexes", {}), **annexes}
        annexes_changees = fusion != memoire.get("annexes")
        memoire["annexes"] = fusion

    changements = comparer(memoire["donnees"], donnees)
    if not changements:
        nouveaux_champs = donnees != memoire["donnees"]
        if nouveaux_champs:  # format enrichi par l'outil : on complète sans signaler de modification
            memoire["donnees"] = donnees
        if annexes_changees or nouveaux_champs:
            _ecrire(dossier, identifiant, memoire)
        return "inchange", {}

    resultats_ajoutes = (not memoire["donnees"].get("resultats_deposes")) and donnees.get("resultats_deposes")
    memoire["modifications"].append({
        "date_detection": date_du_jour,
        "resultats_ajoutes": bool(resultats_ajoutes),
        "champs": changements,
    })
    memoire["donnees"] = donnees
    memoire["derniere_modification_detectee"] = date_du_jour
    _ecrire(dossier, identifiant, memoire)
    return ("resultats_ajoutes" if resultats_ajoutes else "modifie"), changements


def annoter(dossier, identifiant, annexes):
    """Ajoute des annexes à un élément déjà mémorisé, sans toucher à ses données.

    Renvoie False si l'élément n'est pas en mémoire.
    """
    memoire = charger(dossier, identifiant)
    if memoire is None:
        return False
    fusion = {**memoire.get("annexes", {}), **annexes}
    if fusion != memoire.get("annexes"):
        memoire["annexes"] = fusion
        _ecrire(dossier, identifiant, memoire)
    return True


def _ecrire(dossier, identifiant, memoire):
    """Écrit le fichier en passant par un fichier temporaire (pas de fichier à moitié écrit en cas de coupure)."""
    chemin = chemin_fichier(dossier, identifiant)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_suffix(".tmp")
    temporaire.write_text(json.dumps(memoire, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporaire, chemin)
