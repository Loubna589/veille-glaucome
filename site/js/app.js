/* Glaucoma Intelligence — code commun aux pages : navigation, aide « À quoi sert cette page », utilitaires, carte d'étude.
   Les données viennent de site/data/*.json, générés depuis la base SQLite par construire_site.py. */
(function () {
  "use strict";
  var V = (window.Veille = {});
  V.donnees = { etudes: [], laboratoires: [], ordre_rubriques: [] };
  // L'assistant (Flask, port 8770) sert le site sous /site/ : les liens doivent alors pointer vers /site/…
  V.racine = location.port === "8770" ? "/site/" : "";

  /* Icônes (traits simples, 24×24) */
  var I = {
    accueil: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    recherche: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    assistant: '<path d="M4 5h16v11H8l-4 4z"/><path d="M8 9h8M8 12h5"/>',
    carte: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="7" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8.2 7.2l7.5.5M7.3 8.2l3.6 7.6M16.9 9.2l-3.8 6.9"/>',
    etudes: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/><path d="M10 13h6M10 17h6"/>',
    laboratoires: '<path d="M4 21V9l6-4v16"/><path d="M10 21V3l10 5v13"/><path d="M3 21h18M13 10h4M13 14h4"/>',
    marche: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    alertes: '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    fonctionnement: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
  };
  V.LOGO = '<svg viewBox="0 0 48 48" aria-hidden="true"><defs><linearGradient id="gi-a" x1="0" y1="0" x2="1" y2="1">' +
    '<stop offset="0" stop-color="#0b4f8a"/><stop offset="1" stop-color="#14b8a6"/></linearGradient></defs>' +
    '<rect width="48" height="48" rx="13" fill="url(#gi-a)"/>' +
    '<path d="M7 24c4.5-7 10.2-10.5 17-10.5S36.5 17 41 24c-4.5 7-10.2 10.5-17 10.5S11.5 31 7 24z" fill="none" stroke="#fff" stroke-width="2.6" stroke-linejoin="round"/>' +
    '<circle cx="24" cy="24" r="7.2" fill="none" stroke="#a7f3e9" stroke-width="2.4"/><circle cx="24" cy="24" r="3.2" fill="#fff"/>' +
    '<circle cx="26.6" cy="21.5" r="1.3" fill="#0b4f8a"/></svg>';

  /* Les pages, dans l'ordre du menu. `but` et `exemple` s'affichent en haut de chaque page. */
  V.PAGES = [
    { id: "accueil", href: "index.html", label: "Accueil", icone: "accueil",
      but: "Voir d'un coup d'œil ce que la veille suit aujourd'hui et choisir quoi faire.",
      exemple: "Cliquez sur « Voir ce qui a changé » pour lire les nouveautés de ce matin." },
    { id: "recherche", href: "recherche.html", label: "Rechercher", icone: "recherche",
      but: "Trouver les essais et articles qui parlent d'un sujet, même s'ils n'emploient pas vos mots exacts.",
      exemple: "Tapez « collyres sans conservateur » : l'essai ZOLYMBUS sort en premier." },
    { id: "assistant", href: "assistant.html", label: "Poser une question", icone: "assistant", etiquette: "IA",
      but: "Poser une question en français et obtenir une réponse courte, où chaque phrase cite sa source.",
      exemple: "« Quels traitements sans conservateur sont en recherche clinique ? » → réponse avec des liens [NCT…]." },
    { id: "carte", href: "carte.html", label: "Carte des acteurs", icone: "carte",
      but: "Voir qui travaille sur quoi : essais, traitements, laboratoires et financeurs, reliés entre eux.",
      exemple: "Tapez « Santen » dans la recherche de la carte pour voir ses essais et traitements." },
    { id: "etudes", href: "etudes.html", label: "Essais & articles", icone: "etudes",
      but: "Parcourir tous les essais cliniques et articles suivis, avec une fiche détaillée pour chacun.",
      exemple: "Choisissez « Détectées : ces 7 derniers jours » pour ne voir que les plus récents." },
    { id: "laboratoires", href: "laboratoires.html", label: "Laboratoires", icone: "laboratoires",
      but: "Voir, laboratoire par laboratoire, les essais qu'il mène et les articles qu'il finance.",
      exemple: "Tapez « Alcon » pour voir ses essais et ses publications." },
    { id: "marche", href: "marche.html", label: "Autorisations & remboursement", icone: "marche",
      but: "Savoir si un traitement est autorisé et remboursé en France, en Europe et aux États-Unis.",
      exemple: "Regardez la ligne Roclanda : autorisé par l'EMA en 2021, SMR « faible » en France, remboursé à 15 %." },
    { id: "alertes", href: "alertes.html", label: "Alertes", icone: "alertes",
      but: "Être prévenu quand un essai change : nouveau statut, nouvelle date de fin ou résultats publiés.",
      exemple: "Une alerte « RECRUITING → COMPLETED » signale qu'un essai vient de se terminer." },
    { id: "fonctionnement", href: "fonctionnement.html", label: "Comment ça marche", icone: "fonctionnement", etiquette: "jury",
      but: "La partie technique : comment les données sont collectées, contrôlées, analysées par l'IA et évaluées.",
      exemple: "Regardez le schéma, puis le journal de la dernière exécution (une ligne par source)." },
  ];
  V.page = function (id) { return V.PAGES.filter(function (p) { return p.id === id; })[0]; };

  /* Chargement des données exportées (site/data/*.json, générées depuis la base SQLite).
     GitHub Pages est un hébergement statique : le site lit des JSON, pas la base. */
  V.charger = function (fichiers) {
    return Promise.all(fichiers.map(function (f) {
      return fetch(V.racine + "data/" + f, { cache: "no-cache" }).then(function (r) {
        if (!r.ok) throw new Error(f + " : HTTP " + r.status);
        return r.json();
      });
    }));
  };
  V.erreurChargement = function (erreur) {
    var p = document.querySelector("main.page") || document.body;
    p.insertAdjacentHTML("afterbegin", '<div class="encadre" style="border-color:var(--ver);margin-bottom:16px"><strong>' +
      "Données non chargées.</strong> Ouvrez le site avec <code>ouvrir_site.bat</code> (serveur local) ou en ligne : " +
      "en double-clic, le navigateur bloque la lecture des fichiers JSON. <small>(" + V.esc(erreur && erreur.message) + ")</small></div>");
  };
  /* Lance `fn` quand data/veille.json est chargé. */
  V.pret = function (fn) {
    V.charger(["veille.json"]).then(function (r) { V.donnees = r[0]; fn(); }).catch(function (e) {
      if (document.getElementById("nav")) V.monterNavigation("");
      V.erreurChargement(e);
    });
  };

  /* Petits drapeaux SVG locaux (site/img/drapeaux/, Windows n'affiche pas les émojis drapeaux).
     Le nom du pays est presque toujours écrit à côté : l'image est alors décorative (alt vide, sinon le lecteur
     d'écran lirait deux fois le pays). Avec seul=true (drapeau sans texte), alt = nom du pays. */
  V.DRAPEAUX = { "france": "fr", "union europeenne": "eu", "etats-unis": "us", "canada": "ca", "espagne": "es",
    "italie": "it", "suisse": "ch", "australie": "au", "royaume-uni": "gb", "allemagne": "de", "japon": "jp" };
  V.drapeau = function (pays, seul) {
    var n = V.norm(pays || ""), code = null;
    Object.keys(V.DRAPEAUX).forEach(function (k) { if (!code && n.indexOf(k) === 0) code = V.DRAPEAUX[k]; });
    if (!code) return "";
    return '<img class="drapeau" src="' + V.racine + "img/drapeaux/" + code + '.svg" width="20" height="15" ' +
      (seul ? 'alt="' + V.esc(pays) + '" title="' + V.esc(pays) + '"' : 'alt=""') + ">";
  };
  V.esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  V.norm = function (s) {
    return String(s == null ? "" : s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  };
  V.date = function (iso) {
    if (!iso) return "date non rapportée";
    var m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(iso);
    return m ? (m[3] ? m[3] + "/" : "") + m[2] + "/" + m[1] : iso;
  };
  V.param = function (nom) { return new URLSearchParams(location.search).get(nom); };

  V.icone = function (nom) { return '<svg viewBox="0 0 24 24" aria-hidden="true">' + (I[nom] || "") + "</svg>"; };

  V.monterNavigation = function (actuelle) {
    var liens = V.PAGES.map(function (p) {
      return '<a href="' + V.racine + p.href + '"' + (p.id === actuelle ? ' aria-current="page"' : "") + ">" + V.icone(p.icone) +
        "<span>" + V.esc(p.label) + "</span>" + (p.etiquette ? '<span class="etiquette">' + V.esc(p.etiquette) + "</span>" : "") + "</a>";
    });
    var nav = document.getElementById("nav");
    nav.innerHTML = '<a class="lien-evitement" href="#contenu">Aller au contenu</a>' +
      '<nav class="nav" aria-label="Menu principal"><a class="marque" href="' + V.racine + 'index.html">' + V.LOGO +
      "<span><b>Glaucoma Intelligence</b><small>Veille scientifique · glaucome</small></span></a>" +
      '<div class="nav__liens">' + liens.slice(0, 8).join("") + '</div><div class="nav__groupe">Pour le jury</div>' +
      '<div class="nav__liens">' + liens.slice(8).join("") + "</div>" +
      '<div class="nav__pied">Données publiques uniquement.<br>Mise à jour chaque matin.</div></nav>';
    var main = document.querySelector("main.page");
    if (main) main.id = "contenu";
    // « À quoi sert cette page » + un exemple concret, juste sous le titre
    var p = V.page(actuelle), hero = document.querySelector("main.page .hero");
    if (p && hero && !document.getElementById("aide-page")) {
      hero.insertAdjacentHTML("afterend", '<div class="aide" id="aide-page"><div><strong>À quoi sert cette page ?</strong> ' + V.esc(p.but) +
        '</div><div class="aide__exemple"><strong>Exemple :</strong> ' + V.esc(p.exemple) + "</div></div>");
    }
    // Bulle d'assistant + bouton « retour en haut » sur toutes les pages (sauf l'application assistant elle-même)
    if (location.port !== "8770" && !document.getElementById("gi-bulle-script")) {
      var s = document.createElement("script");
      s.id = "gi-bulle-script"; s.src = V.racine + "js/bulle.js";
      document.body.appendChild(s);
    }
    // Pied de page : lit data/meta.json (petit fichier), quelle que soit la page
    var pied = document.getElementById("pied");
    if (pied) {
      pied.innerHTML = "Glaucoma Intelligence — veille construite uniquement à partir de 11 sources publiques : 4 scientifiques (ClinicalTrials.gov, PubMed, OpenAlex, Crossref) " +
        "et 7 réglementaires (BDPM/HAS, EMA, openFDA, Santé Canada, AEMPS, AIFA, Swissmedic).";
      V.charger(["meta.json"]).then(function (r) {
        pied.innerHTML += " Dernière mise à jour : <strong>" + V.esc(V.date(r[0].derniere_mise_a_jour)) + "</strong> · site généré le " + V.esc(r[0].genere_le) + ".";
      }).catch(function () {});
    }
  };

  V.classeNiveau = function (niveau) {
    if (/Résultats déposés|résultats dans le résumé/.test(niveau)) return "ok";
    if (/Protocole|sans résultats|Preprint/.test(niveau)) return "att";
    return "";
  };

  /* Carte d'une étude, utilisée par l'accueil et la page Études */
  V.carte = function (e) {
    var titre = e.fiche
      ? '<a href="' + V.esc(e.fiche) + '">' + V.esc(e.titre || "Titre non rapporté") + "</a>"
      : '<a href="' + V.esc(e.lien_source) + '" target="_blank" rel="noopener">' + V.esc(e.titre || "Titre non rapporté") + "</a>";
    var badges = (e.nouveau ? '<span class="badge neuf">Nouveau</span>' : "") +
      (e.modifie ? '<span class="badge neuf">Modifié</span>' : "") +
      '<span class="badge">' + V.esc(e.source) + "</span>" +
      '<span class="badge ' + V.classeNiveau(e.niveau) + '">' + V.esc(e.niveau) + "</span>" +
      (e.phase ? '<span class="badge reg">' + V.esc(e.phase) + "</span>" : "") +
      (e.statut ? '<span class="badge">' + V.esc(e.statut) + "</span>" : "");
    var labos = (e.labos || []).map(function (l) {
      return '<a href="laboratoires.html?labo=' + encodeURIComponent(l.nom) + '">' + V.esc(l.nom) + "</a> <small>(" + V.esc(l.role) + ")</small>";
    }).join(" · ");
    var produits = (e.produits || []).slice(0, 5).map(function (p) {
      return V.esc(p.nom) + " <small>— " + V.esc(p.role) + "</small>";
    }).join(" · ");
    var modifs = (e.modifications || []).length
      ? "<span>Modifié le " + V.esc(V.date(e.modifications[e.modifications.length - 1].date)) + " : " +
        V.esc(e.modifications[e.modifications.length - 1].champs.join(", ")) + "</span>" : "";
    return '<article class="carte">' + badges + "<h3>" + titre + "</h3>" +
      '<div class="meta"><span>Détecté le <strong>' + V.esc(V.date(e.date_detection)) + "</strong></span>" +
      "<span>Date source : " + V.esc(V.date(e.date_source)) + "</span>" + modifs +
      (e.revue ? "<span>" + V.esc(e.revue) + "</span>" : "") + "</div>" +
      '<div class="meta"><span>Produits : ' + (produits || '<span class="vide">aucun repéré</span>') + "</span></div>" +
      '<div class="meta"><span>Organismes : ' + (labos || '<span class="vide">aucun</span>') + "</span></div>" +
      '<div class="meta"><span>Rubrique : ' + V.esc(e.rubrique) + ' <span class="badge reg">classement automatique</span> <small>' +
      V.esc(e.raison_rubrique) + "</small></span></div>" +
      (e.resume_ia ? '<div class="resume-ia"><span class="badge ver">' + V.esc(e.resume_ia.mention || "Généré par IA, non vérifié") +
        '</span> <span class="badge reg">' + V.esc(e.resume_ia.categorie_libelle || "") + "</span><ul>" +
        (e.resume_ia.resume || []).map(function (l) { return "<li>" + V.esc(l) + "</li>"; }).join("") + "</ul>" +
        "<small>" + V.esc(e.resume_ia.modele) + " · prompt " + V.esc(e.resume_ia.version_prompt) + " · " +
        V.esc(V.date(e.resume_ia.genere_le)) + "</small></div>" : "") +
      (e.resume ? '<details class="resume"><summary>Résumé (texte source' + (e.type === "essai" ? " du registre" : "") +
        ", en anglais)</summary><p lang=\"en\">" + V.esc(e.resume) + "</p></details>"
        : '<p class="vide" style="margin-top:6px">Aucun résumé disponible dans la source.</p>') +
      '<div class="actions">' + (e.fiche ? '<a href="' + V.esc(e.fiche) + '">Fiche détaillée →</a>' : "") +
      '<a href="' + V.esc(e.lien_source) + '" target="_blank" rel="noopener">Voir la source ↗</a></div></article>';
  };
})();
