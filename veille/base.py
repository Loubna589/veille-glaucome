"""Base de données de la veille : SQLite (data/veille.db), module sqlite3 standard.

Pourquoi SQLite ?
- un seul fichier, versionné avec le code (GitHub Actions le relit chaque jour) ;
- des CLÉS UNIQUES qui garantissent la déduplication (PMID, DOI, OpenAlex, NCT) ;
- des requêtes SQL pour le site, les contrôles qualité et les alertes ;
- l'historique complet : chaque version d'un essai et chaque événement daté.

Tables :
  sources            les 11 sources publiques interrogées (4 scientifiques, 7 réglementaires)
  articles           publications (PubMed ou OpenAlex), dédupliquées par PMID, DOI ou identifiant OpenAlex
  articles_sources   quelle source a vu quelle publication (traçabilité)
  essais             essais ClinicalTrials.gov (clé NCT), dernière version
  versions_essais    un instantané complet + son empreinte à chaque changement d'un essai
  evenements         nouveautés et changements détectés (clé de déduplication unique)
  executions         journal de chaque passage : une ligne par source (début, fin, statut, nb, erreurs)
  traitements_ia     sorties de l'IA (modèle, version du prompt, date, statut de validation)
  meta               petites valeurs d'état (date de la dernière exécution, dernier bilan)
"""
import hashlib
import json
import sqlite3
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
CHEMIN = RACINE / "data" / "veille.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, nom TEXT NOT NULL, url TEXT, acces TEXT
);
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    pmid TEXT UNIQUE, doi TEXT UNIQUE, openalex_id TEXT UNIQUE,
    origine TEXT NOT NULL CHECK (origine IN ('pubmed', 'openalex')),
    titre TEXT NOT NULL, date_source TEXT, revue TEXT,
    donnees TEXT NOT NULL, annexes TEXT NOT NULL DEFAULT '{}',
    premiere_detection TEXT NOT NULL, derniere_maj TEXT NOT NULL,
    CHECK (pmid IS NOT NULL OR doi IS NOT NULL OR openalex_id IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS articles_sources (
    article_id INTEGER NOT NULL REFERENCES articles(id), source TEXT NOT NULL REFERENCES sources(id),
    premiere_vue TEXT NOT NULL, PRIMARY KEY (article_id, source)
);
CREATE TABLE IF NOT EXISTS essais (
    nct TEXT PRIMARY KEY CHECK (nct GLOB 'NCT[0-9]*'),
    titre TEXT NOT NULL, statut TEXT, phases TEXT, date_fin_principale TEXT, participants INTEGER,
    resultats_deposes INTEGER NOT NULL DEFAULT 0, promoteur TEXT,
    donnees TEXT NOT NULL, annexes TEXT NOT NULL DEFAULT '{}', empreinte TEXT NOT NULL,
    premiere_detection TEXT NOT NULL, derniere_modification TEXT
);
CREATE TABLE IF NOT EXISTS versions_essais (
    id INTEGER PRIMARY KEY, nct TEXT NOT NULL REFERENCES essais(nct), empreinte TEXT NOT NULL,
    instantane TEXT NOT NULL, date_detection TEXT NOT NULL, execution_id TEXT,
    UNIQUE (nct, empreinte)
);
CREATE TABLE IF NOT EXISTS evenements (
    id INTEGER PRIMARY KEY,
    cle_dedup TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL, objet_type TEXT NOT NULL, objet_id TEXT NOT NULL,
    champ TEXT, avant TEXT, apres TEXT, titre TEXT,
    date_detection TEXT NOT NULL, execution_id TEXT,
    envoye INTEGER NOT NULL DEFAULT 0, date_envoi TEXT
);
CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY, execution_id TEXT NOT NULL, source TEXT NOT NULL,
    debut TEXT NOT NULL, fin TEXT, statut TEXT NOT NULL CHECK (statut IN ('en_cours', 'ok', 'partielle', 'echec', 'saute')),
    nb_elements INTEGER NOT NULL DEFAULT 0, erreurs TEXT
);
CREATE TABLE IF NOT EXISTS traitements_ia (
    id INTEGER PRIMARY KEY, objet_type TEXT NOT NULL, objet_id TEXT NOT NULL,
    empreinte_source TEXT NOT NULL, modele TEXT NOT NULL, version_prompt TEXT NOT NULL,
    date TEXT NOT NULL, sortie TEXT NOT NULL, categorie TEXT, resume TEXT, pourquoi TEXT,
    statut_validation TEXT NOT NULL DEFAULT 'non_verifie'
        CHECK (statut_validation IN ('non_verifie', 'valide', 'corrige', 'rejete')),
    UNIQUE (objet_id, empreinte_source, version_prompt)
);
CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur TEXT);
CREATE INDEX IF NOT EXISTS idx_evenements_envoye ON evenements(envoye, date_detection);
CREATE INDEX IF NOT EXISTS idx_executions ON executions(execution_id);
"""

SOURCES = [
    ("clinicaltrials", "ClinicalTrials.gov", "https://clinicaltrials.gov/data-api/api", "API v2, sans clé"),
    ("pubmed", "PubMed (NCBI E-utilities)", "https://www.ncbi.nlm.nih.gov/books/NBK25501/", "API, clé facultative"),
    ("openalex", "OpenAlex", "https://docs.openalex.org", "API, clé facultative (gratuite)"),
    ("crossref", "Crossref", "https://api.crossref.org", "API, sans clé"),
    ("bdpm", "BDPM (ANSM, HAS, Assurance maladie)", "https://base-donnees-publique.medicaments.gouv.fr", "fichiers publics"),
    ("ema", "EMA", "https://www.ema.europa.eu/en/medicines/download-medicine-data", "fichier JSON public"),
    ("openfda", "openFDA Drugs@FDA", "https://open.fda.gov/apis/drug/drugsfda/", "API, sans clé"),
    ("canada", "Santé Canada — DPD", "https://health-products.canada.ca/api/documentation/dpd-documentation-en.html", "API, sans clé"),
    ("espagne", "AEMPS — CIMA", "https://cima.aemps.es/cima/publico/home.html", "API REST, sans clé"),
    ("italie", "AIFA — listes A et H", "https://www.aifa.gov.it/liste-farmaci-a-h", "fichiers CSV publics"),
    ("suisse", "Swissmedic — liste étendue", "https://www.swissmedic.ch/swissmedic/fr/home/services/listen_neu.html", "fichier Excel public"),
    ("australie", "PBS (facultatif)", "https://data.pbs.gov.au/api/pbs-api.html", "API publique, clé partagée publiée par le ministère"),
]

# Statuts ClinicalTrials.gov qui décrivent le RECRUTEMENT (le reste = statut de l'essai)
STATUTS_RECRUTEMENT = {"NOT_YET_RECRUITING", "RECRUITING", "ENROLLING_BY_INVITATION", "ACTIVE_NOT_RECRUITING"}


def maintenant():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def jdump(valeur):
    """JSON canonique (clés triées) : deux contenus identiques donnent le même texte et la même empreinte."""
    return json.dumps(valeur, ensure_ascii=False, sort_keys=True)


def empreinte(valeur):
    return hashlib.sha256(jdump(valeur).encode("utf-8")).hexdigest()[:20]


def connecter(chemin=CHEMIN):
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.executemany("INSERT OR IGNORE INTO sources (id, nom, url, acces) VALUES (?, ?, ?, ?)", SOURCES)
    conn.commit()
    return conn


# ------------------------------------------------------------ état

def lire_meta(conn, cle, defaut=None):
    ligne = conn.execute("SELECT valeur FROM meta WHERE cle = ?", (cle,)).fetchone()
    return json.loads(ligne["valeur"]) if ligne else defaut


def ecrire_meta(conn, cle, valeur):
    conn.execute("INSERT INTO meta (cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
                 (cle, jdump(valeur)))


# ------------------------------------------------------------ événements

def ajouter_evenement(conn, type_, objet_type, objet_id, date, execution_id=None, champ=None, avant=None,
                      apres=None, titre=None):
    """Enregistre un événement UNE SEULE FOIS : la clé de déduplication est unique dans la table.

    Renvoie True si l'événement est nouveau, False s'il existait déjà."""
    avant_txt = None if avant is None else (avant if isinstance(avant, str) else jdump(avant))
    apres_txt = None if apres is None else (apres if isinstance(apres, str) else jdump(apres))
    cle = "|".join(str(x) for x in (type_, objet_id, champ or "", avant_txt or "", apres_txt or ""))
    curseur = conn.execute(
        "INSERT OR IGNORE INTO evenements (cle_dedup, type, objet_type, objet_id, champ, avant, apres, titre, "
        "date_detection, execution_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cle, type_, objet_type, objet_id, champ, avant_txt, apres_txt, titre, date, execution_id))
    return curseur.rowcount == 1


def evenements_essai(avant, apres):
    """Événements métier à partir de deux versions d'un essai : liste de (type, champ, avant, après)."""
    sortie = []
    s1, s2 = avant.get("statut"), apres.get("statut")
    if s1 != s2:
        type_ = "changement_recrutement" if {s1, s2} <= STATUTS_RECRUTEMENT else "changement_statut"
        sortie.append((type_, "statut", s1, s2))
    if avant.get("participants_nombre") != apres.get("participants_nombre") and "participants_nombre" in avant:
        sortie.append(("changement_recrutement", "participants_nombre", avant.get("participants_nombre"),
                       apres.get("participants_nombre")))
    if avant.get("date_fin_principale") != apres.get("date_fin_principale") and "date_fin_principale" in avant:
        sortie.append(("changement_date_fin", "date_fin_principale", avant.get("date_fin_principale"),
                       apres.get("date_fin_principale")))
    if avant.get("phases_declarees") != apres.get("phases_declarees") and "phases_declarees" in avant:
        sortie.append(("changement_phase", "phases_declarees", avant.get("phases_declarees"), apres.get("phases_declarees")))
    if not avant.get("resultats_deposes") and apres.get("resultats_deposes"):
        sortie.append(("resultats_deposes", "resultats_deposes", False, True))
    return sortie


# ------------------------------------------------------------ essais

def enregistrer_essai(conn, donnees, jour, execution_id=None, annexes=None):
    """Insère ou met à jour un essai. Renvoie (etat, changements, nouveaux_evenements).

    etat : "nouveau", "inchange", "modifie" ou "resultats_ajoutes" (mêmes valeurs que l'ancien historique JSON).
    À chaque changement, l'ancienne version est conservée dans versions_essais."""
    from veille import historique  # comparaison champ à champ, déjà éprouvée

    nct = donnees["nct"]
    nouvelle = empreinte(donnees)
    ligne = conn.execute("SELECT donnees, annexes, empreinte FROM essais WHERE nct = ?", (nct,)).fetchone()
    colonnes = (donnees.get("titre") or "(titre non rapporté)", donnees.get("statut"), jdump(donnees.get("phases_declarees")),
                donnees.get("date_fin_principale"), donnees.get("participants_nombre"),
                int(bool(donnees.get("resultats_deposes"))), donnees.get("promoteur"), jdump(donnees), nouvelle)
    if ligne is None:
        conn.execute("INSERT INTO essais (titre, statut, phases, date_fin_principale, participants, resultats_deposes, "
                     "promoteur, donnees, empreinte, nct, premiere_detection, annexes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (*colonnes, nct, jour, jdump(annexes or {})))
        conn.execute("INSERT OR IGNORE INTO versions_essais (nct, empreinte, instantane, date_detection, execution_id) "
                     "VALUES (?, ?, ?, ?, ?)", (nct, nouvelle, jdump(donnees), jour, execution_id))
        n = ajouter_evenement(conn, "nouvel_essai", "essai", nct, jour, execution_id, titre=donnees.get("titre"))
        return "nouveau", {}, int(n)

    if annexes:
        fusion = {**json.loads(ligne["annexes"]), **annexes}
        conn.execute("UPDATE essais SET annexes = ? WHERE nct = ?", (jdump(fusion), nct))
    if ligne["empreinte"] == nouvelle:
        return "inchange", {}, 0

    ancienne = json.loads(ligne["donnees"])
    changements = historique.comparer(ancienne, donnees)
    conn.execute("UPDATE essais SET titre=?, statut=?, phases=?, date_fin_principale=?, participants=?, "
                 "resultats_deposes=?, promoteur=?, donnees=?, empreinte=? WHERE nct=?", (*colonnes, nct))
    if not changements:  # seulement des champs nouveaux (évolution de l'outil) : pas un changement de la source
        return "inchange", {}, 0
    conn.execute("UPDATE essais SET derniere_modification = ? WHERE nct = ?", (jour, nct))
    conn.execute("INSERT OR IGNORE INTO versions_essais (nct, empreinte, instantane, date_detection, execution_id) "
                 "VALUES (?, ?, ?, ?, ?)", (nct, nouvelle, jdump(donnees), jour, execution_id))
    n = sum(ajouter_evenement(conn, t, "essai", nct, jour, execution_id, champ, av, ap, donnees.get("titre"))
            for t, champ, av, ap in evenements_essai(ancienne, donnees))
    resultats = not ancienne.get("resultats_deposes") and donnees.get("resultats_deposes")
    return ("resultats_ajoutes" if resultats else "modifie"), changements, n


# ------------------------------------------------------------ articles

def trouver_article(conn, pmid=None, doi=None, openalex_id=None):
    """Identifiant interne d'une publication déjà connue sous l'un de ses identifiants (déduplication)."""
    for colonne, valeur in (("pmid", pmid), ("doi", (doi or "").lower() or None), ("openalex_id", openalex_id)):
        if valeur:
            ligne = conn.execute(f"SELECT id FROM articles WHERE {colonne} = ?", (valeur,)).fetchone()
            if ligne:
                return ligne["id"]
    return None


def enregistrer_article(conn, donnees, jour, source, origine, annexes=None, execution_id=None):
    """Insère une publication ou complète celle déjà connue (même PMID, DOI ou OpenAlex).

    Renvoie (etat, id interne) avec etat « nouveau » ou « deja_connu »."""
    pmid, oa = donnees.get("pmid"), donnees.get("openalex_id")
    doi = (donnees.get("doi") or "").lower() or None
    existant = trouver_article(conn, pmid, doi, oa)
    if existant is None:
        curseur = conn.execute(
            "INSERT INTO articles (pmid, doi, openalex_id, origine, titre, date_source, revue, donnees, annexes, "
            "premiere_detection, derniere_maj) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (pmid, doi, oa, origine, donnees.get("titre") or "(titre non rapporté)",
             donnees.get("date_entree_pubmed") or donnees.get("date_publication"), donnees.get("revue"),
             jdump(donnees), jdump(annexes or {}), jour, jour))
        article_id = curseur.lastrowid
        conn.execute("INSERT OR IGNORE INTO articles_sources VALUES (?, ?, ?)", (article_id, source, jour))
        ajouter_evenement(conn, "nouvel_article", "article", pmid or doi or oa, jour, execution_id, titre=donnees.get("titre"))
        return "nouveau", article_id

    ligne = conn.execute("SELECT * FROM articles WHERE id = ?", (existant,)).fetchone()
    # Compléter les identifiants manquants (ex. un DOI trouvé par PubMed pour une publication vue d'abord par OpenAlex)
    for colonne, valeur in (("pmid", pmid), ("doi", doi), ("openalex_id", oa)):
        if valeur and not ligne[colonne] and not trouver_article(conn, **{colonne: valeur}):
            conn.execute(f"UPDATE articles SET {colonne} = ? WHERE id = ?", (valeur, existant))
    if origine == "pubmed" and ligne["origine"] != "pubmed":
        # PubMed devient la notice de référence ; l'ancienne notice OpenAlex reste en annexe
        fusion = {**json.loads(ligne["annexes"]), "notice_openalex": json.loads(ligne["donnees"]), **(annexes or {})}
        conn.execute("UPDATE articles SET origine='pubmed', titre=?, date_source=?, revue=?, donnees=?, annexes=?, "
                     "derniere_maj=? WHERE id=?", (donnees.get("titre") or ligne["titre"], donnees.get("date_entree_pubmed"),
                                                   donnees.get("revue"), jdump(donnees), jdump(fusion), jour, existant))
    elif annexes:
        fusion = {**json.loads(ligne["annexes"]), **annexes}
        conn.execute("UPDATE articles SET annexes = ?, derniere_maj = ? WHERE id = ?", (jdump(fusion), jour, existant))
    conn.execute("INSERT OR IGNORE INTO articles_sources VALUES (?, ?, ?)", (existant, source, jour))
    return "deja_connu", existant


def annoter_article(conn, pmid, annexes, jour=None):
    ligne = conn.execute("SELECT id, annexes FROM articles WHERE pmid = ?", (pmid,)).fetchone()
    if not ligne:
        return False
    fusion = {**json.loads(ligne["annexes"]), **annexes}
    conn.execute("UPDATE articles SET annexes = ?, derniere_maj = COALESCE(?, derniere_maj) WHERE id = ?",
                 (jdump(fusion), jour, ligne["id"]))
    return True


# ------------------------------------------------------------ lecture (format « mémoire » utilisé par le site)

def memoires_essais(conn):
    """Essais au format de l'ancien historique JSON (donnees, annexes, modifications…)."""
    sortie = []
    for e in conn.execute("SELECT * FROM essais ORDER BY nct"):
        modifs = {}
        for ev in conn.execute("SELECT * FROM evenements WHERE objet_id = ? AND type NOT IN ('nouvel_essai') "
                               "ORDER BY date_detection, id", (e["nct"],)):
            m = modifs.setdefault(ev["date_detection"], {"date_detection": ev["date_detection"], "resultats_ajoutes": False,
                                                         "champs": {}})
            m["champs"][ev["champ"] or ev["type"]] = {"avant": ev["avant"], "apres": ev["apres"]}
            m["resultats_ajoutes"] = m["resultats_ajoutes"] or ev["type"] == "resultats_deposes"
        sortie.append({"nct": e["nct"], "premiere_detection": e["premiere_detection"],
                       "derniere_modification_detectee": e["derniere_modification"],
                       "donnees": json.loads(e["donnees"]), "annexes": json.loads(e["annexes"]),
                       "modifications": list(modifs.values())})
    return sortie


def memoires_articles(conn, origine):
    sortie = []
    for a in conn.execute("SELECT * FROM articles WHERE origine = ? ORDER BY id", (origine,)):
        cle = "pmid" if origine == "pubmed" else "openalex_id"
        sortie.append({cle: a[cle], "premiere_detection": a["premiere_detection"], "derniere_modification_detectee": None,
                       "donnees": json.loads(a["donnees"]), "annexes": json.loads(a["annexes"]), "modifications": []})
    return sortie


# ------------------------------------------------------------ journal des exécutions

class Execution:
    """Journal d'un passage du pipeline : une ligne par source dans la table executions."""

    def __init__(self, conn):
        self.conn = conn
        self.id = time.strftime("%Y%m%dT%H%M%S")
        self.debut = maintenant()
        self.etapes = []

    def etape(self, source, fonction):
        """Exécute une étape ; une erreur est journalisée et N'ARRÊTE PAS les autres sources."""
        debut = maintenant()
        try:
            nb = fonction() or 0
            statut, erreur = "ok", None
        except Exception as e:  # noqa: BLE001 — toute panne d'une source est isolée et tracée
            self.conn.rollback()  # on annule les écritures à moitié faites de CETTE étape seulement
            # Une étape volontairement sautée (ex. clé facultative absente) n'est pas une panne
            nb, statut, erreur = 0, ("saute" if getattr(e, "saute", False) else "echec"), f"{type(e).__name__}: {e}"[:500]
        self.conn.execute("INSERT INTO executions (execution_id, source, debut, fin, statut, nb_elements, erreurs) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?)", (self.id, source, debut, maintenant(), statut, int(nb), erreur))
        self.conn.commit()
        self.etapes.append({"source": source, "statut": statut, "nb": int(nb), "erreur": erreur})
        return statut, erreur

    def terminer(self):
        """Statut global : ok (tout a marché), partielle (au moins une source en échec), echec (toutes)."""
        echecs = [e for e in self.etapes if e["statut"] == "echec"]
        statut = "ok" if not echecs else ("echec" if len(echecs) == len(self.etapes) else "partielle")
        self.conn.execute("INSERT INTO executions (execution_id, source, debut, fin, statut, nb_elements, erreurs) "
                          "VALUES (?, 'pipeline', ?, ?, ?, ?, ?)",
                          (self.id, self.debut, maintenant(), statut, sum(e["nb"] for e in self.etapes),
                           "; ".join(f"{e['source']} : {e['erreur']}" for e in echecs) or None))
        self.conn.commit()
        return statut
