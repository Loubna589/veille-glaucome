/* Glaucoma Intelligence — code commun aux pages : navigation, aide « À quoi sert cette page », utilitaires, carte d'étude.
   Les données viennent de site/data/*.json, générés depuis la base SQLite par construire_site.py. */
(function () {
  "use strict";
  var V = (window.Veille = {});
  V.donnees = { etudes: [], laboratoires: [], ordre_rubriques: [] };
  // L'assistant (Flask, port 8770) sert le site sous /site/ : les liens doivent alors pointer vers /site/…
  V.racine = location.port === "8770" ? "/site/" : "";
  // Version des fichiers (ajoutée par construire_site.py) : la bulle est chargée dans la même version que ce script
  V.version = ((document.currentScript && document.currentScript.src) || "").split("?v=")[1] || "";

  /* Icônes (traits simples, 24×24) */
  var I = {
    accueil: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    recherche: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    assistant: '<path d="M4 5h16v11H8l-4 4z"/><path d="M8 9h8M8 12h5"/>',
    carte: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="7" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8.2 7.2l7.5.5M7.3 8.2l3.6 7.6M16.9 9.2l-3.8 6.9"/>',
    etudes: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/><path d="M10 13h6M10 17h6"/>',
    laboratoires: '<path d="M4 21V9l6-4v16"/><path d="M10 21V3l10 5v13"/><path d="M3 21h18M13 10h4M13 14h4"/>',
    marche: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    apropos: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><circle cx="12" cy="7.5" r=".6" fill="currentColor"/>',
    concurrents: '<path d="M3 21V10l5-3v14"/><path d="M8 21V5l6 3v13"/><path d="M14 21V11l7-3v13"/><path d="M2 21h20"/>',
    semaine: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4M8 14h3M8 17h6"/>',
    methode: '<path d="M5 4h11l3 3v13H5z"/><path d="M8 10h8M8 13h8M8 16h5"/><path d="M15 4v4h4"/>',
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
    { id: "semaine", href: "semaine.html", label: "Cette semaine", icone: "semaine", etiquette: "IA",
      but: "Lire en 2 minutes les 5 points à retenir des 7 derniers jours, chacun avec sa source.",
      exemple: "Cliquez sur un identifiant (NCT…, PMID…) pour ouvrir l'essai ou l'article d'origine." },
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
      but: "Une fiche par laboratoire : médicaments autorisés pays par pays, essais et publications.",
      exemple: "Ouvrez la fiche Santen : Roclanda, Catiolanze, Saflutan… pays par pays, puis ses essais." },
    { id: "marche", href: "marche.html", label: "Autorisations & remboursement", icone: "marche",
      but: "Savoir si un traitement est autorisé et remboursé en France, en Europe et aux États-Unis.",
      exemple: "Regardez la ligne Roclanda : autorisé par l'EMA en 2021, SMR « faible » en France, remboursé à 15 %." },
    { id: "alertes", href: "alertes.html", label: "Alertes", icone: "alertes",
      but: "Être prévenu quand un essai change : nouveau statut, nouvelle date de fin ou résultats publiés.",
      exemple: "Une alerte « RECRUITING → COMPLETED » signale qu'un essai vient de se terminer." },
    { id: "fonctionnement", href: "fonctionnement.html", label: "Comment ça marche", icone: "fonctionnement", etiquette: "jury",
      but: "La partie technique : comment les données sont collectées, contrôlées, analysées par l'IA et évaluées.",
      exemple: "Regardez le schéma, puis le journal de la dernière exécution (une ligne par source)." },
    { id: "methode", href: "methode.html", label: "Limites", icone: "methode", etiquette: "jury",
      but: "Savoir d'où viennent les données, à quelle fréquence, ce que l'IA fait et ne fait pas, et les biais à garder en tête.",
      exemple: "Lisez « Ce que l'IA ne fait pas » avant de citer un résumé automatique." },
    { id: "apropos", href: "apropos.html", label: "À propos", icone: "apropos",
      but: "Qui a réalisé ce projet, dans quel cadre, et selon quels principes.",
      exemple: "Suivez le lien « Limites » pour savoir ce que l'outil ne fait pas." },
  ];
  /* Le fil de la présentation orale : l'ordre des étapes (les autres pages restent dans « Autres pages ») */
  V.ETAPES = ["apropos", "accueil", "fonctionnement", "semaine", "etudes", "laboratoires", "marche", "methode"];
  V.HORS_MENU = ["assistant", "carte"];  // pages gardées (liens directs) mais retirées du menu à la demande de Loubna
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
    function lien(p, numero) {
      var etiquette = p.etiquette && p.etiquette !== "jury" ? p.etiquette : "";
      return '<a href="' + V.racine + p.href + '"' + (p.id === actuelle ? ' aria-current="page"' : "") + ">" +
        (numero ? '<span class="nav__num">' + numero + "</span>" : V.icone(p.icone)) +
        "<span>" + V.esc(p.label) + "</span>" + (etiquette ? '<span class="etiquette">' + V.esc(etiquette) + "</span>" : "") + "</a>";
    }
    var fil = V.ETAPES.map(function (id, i) { return lien(V.page(id), i + 1); });
    var autres = V.PAGES.filter(function (p) { return V.ETAPES.indexOf(p.id) < 0 && V.HORS_MENU.indexOf(p.id) < 0; }).map(function (p) { return lien(p); });
    var nav = document.getElementById("nav");
    nav.innerHTML = '<a class="lien-evitement" href="#contenu">Aller au contenu</a>' +
      '<nav class="nav" aria-label="Menu principal"><a class="marque" href="' + V.racine + 'index.html">' + V.LOGO +
      "<span><b>Glaucoma Intelligence</b><small>Veille scientifique · glaucome</small></span></a>" +
      '<div class="nav__groupe nav__groupe--haut">Le projet, étape par étape</div>' +
      '<div class="nav__liens">' + fil.join("") + '</div><div class="nav__groupe">Autres pages</div>' +
      '<div class="nav__liens">' + autres.join("") + "</div>" +
      '<div class="nav__pied">Sources officielles citées.<br>Mise à jour chaque jour.</div></nav>';
    var main = document.querySelector("main.page");
    if (main) main.id = "contenu";
    // « À quoi sert cette page » + un exemple concret, juste sous le titre
    // (désactivé à la demande de Loubna : les pages s'expliquent dans leur titre ; `but` reste utilisé par l'assistant)
    var p = V.page(actuelle), hero = document.querySelector("main.page .hero");
    if (false && p && hero && !document.getElementById("aide-page")) {
      hero.insertAdjacentHTML("afterend", '<div class="aide" id="aide-page"><div><strong>À quoi sert cette page ?</strong> ' + V.esc(p.but) +
        '</div><div class="aide__exemple"><strong>Exemple :</strong> ' + V.esc(p.exemple) + "</div></div>");
    }
    // Bulle d'assistant + bouton « retour en haut » sur toutes les pages (sauf l'application assistant elle-même)
    if (location.port !== "8770" && !document.getElementById("gi-bulle-script")) {
      var s = document.createElement("script");
      s.id = "gi-bulle-script"; s.src = V.racine + "js/bulle.js" + (V.version ? "?v=" + V.version : "");
      document.body.appendChild(s);
    }
    // Barre « Étape précédente / suivante » en bas des pages du fil (pour présenter en cliquant, ou avec les flèches ← →)
    var rang = V.ETAPES.indexOf(actuelle), main2 = document.querySelector("main.page");
    if (rang >= 0 && main2 && !document.getElementById("fil-etapes")) {
      var prec = V.page(V.ETAPES[rang - 1]), suiv = V.page(V.ETAPES[rang + 1]);
      main2.insertAdjacentHTML("beforeend", '<nav class="fil-etapes" id="fil-etapes" aria-label="Étapes de la présentation">' +
        (prec ? '<a class="fil-prec" href="' + V.racine + prec.href + '">← ' + (rang) + ". " + V.esc(prec.label) + "</a>" : "<span></span>") +
        '<span class="fil-rang">Étape ' + (rang + 1) + " sur " + V.ETAPES.length + "</span>" +
        (suiv ? '<a class="fil-suiv" href="' + V.racine + suiv.href + '">Étape suivante : ' + (rang + 2) + ". " + V.esc(suiv.label) + " →</a>"
          : '<a class="fil-suiv" href="' + V.racine + 'index.html">Fin · retour à l\'accueil ↺</a>') + "</nav>");
      document.addEventListener("keydown", function (e) {
        var t = e.target, saisie = t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable);
        if (saisie || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
        if (e.key === "ArrowRight" && suiv) location.href = V.racine + suiv.href;
        if (e.key === "ArrowLeft" && prec) location.href = V.racine + prec.href;
      });
    }
    // Pied de page : lit data/meta.json (petit fichier), quelle que soit la page
    var pied = document.getElementById("pied");
    if (pied) {
      pied.innerHTML = "<strong>Glaucoma Intelligence</strong> · projet pédagogique · M2 MOD, IAE Clermont Auvergne · " +
        '<a href="' + V.racine + 'methode.html">Limites</a> · <a href="' + V.racine + 'apropos.html">À propos</a>.';
      V.charger(["meta.json"]).then(function (r) {
        pied.innerHTML += " Dernière mise à jour : <strong>" + V.esc(V.date(r[0].derniere_mise_a_jour)) + "</strong>.";
      }).catch(function () {});
    }
  };

  V.classeNiveau = function (niveau) {
    if (/Résultats déposés|résultats dans le résumé/.test(niveau)) return "ok";
    if (/Protocole|sans résultats|Preprint/.test(niveau)) return "att";
    return "";
  };

  V.LIBELLES_ACCES = { libre: "✅ Lecture gratuite", payant: "🔒 Article payant", inconnu: "❔ Gratuit ? non indiqué" };
  V.AIDE_ACCES = { libre: "Le texte complet se lit gratuitement en ligne.",
    payant: "Le texte complet est sur abonnement : demandez-le à la BU ou à l'auteur.",
    inconnu: "Les bases consultées ne disent pas si l'article est gratuit : essayez le lien de la source, sinon demandez-le à la BU." };
  /* Libellés en mots simples (les valeurs internes restent celles des filtres) */
  var NIVEAUX_SIMPLES = {
    "Résultats déposés au registre": ["📊 Résultats publiés", "L'équipe a mis les résultats de l'essai sur ClinicalTrials.gov, le site officiel où chaque essai est déclaré."],
    "Essai enregistré (sans résultats)": ["Essai déclaré, pas encore de résultats", "L'essai est déclaré sur ClinicalTrials.gov, le site officiel des essais, mais ses résultats n'y sont pas encore."]
  };

  /* Carte d'une étude, utilisée par l'accueil et la page Études */
  V.carte = function (e) {
    var titre = e.fiche
      ? '<a href="' + V.esc(e.fiche) + '">' + V.esc(e.titre || "Titre non rapporté") + "</a>"
      : '<a href="' + V.esc(e.lien_source) + '" target="_blank" rel="noopener">' + V.esc(e.titre || "Titre non rapporté") + "</a>";
    var badges = (e.nouveau ? '<span class="badge neuf">Nouveau</span>' : "") +
      (e.modifie ? '<span class="badge neuf">Modifié</span>' : "") +
      '<span class="badge">' + V.esc(e.source) + "</span>" +
      '<span class="badge ' + V.classeNiveau(e.niveau) + '" title="' + V.esc((NIVEAUX_SIMPLES[e.niveau] || [])[1] || "") + '">' +
        V.esc((NIVEAUX_SIMPLES[e.niveau] || [e.niveau])[0]) + "</span>" +
      (e.phase && !/non renseign/i.test(e.phase) ? '<span class="badge reg">' + V.esc(e.phase) + "</span>" : "") +
      (e.statut ? '<span class="badge">' + V.esc(e.statut) + "</span>" : "") +
      (e.acces ? '<span class="badge acces-' + V.esc(e.acces) + '" title="' + V.esc(V.AIDE_ACCES[e.acces] || "") + '">' + V.esc(V.LIBELLES_ACCES[e.acces] || e.acces) + "</span>" : "");
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
      (e.resume_ia ? '<button type="button" class="bouton-ia" aria-expanded="false" data-resume-ia>✨ Résumé en français par l\'IA</button>' +
        '<div class="resume-ia" hidden><span class="badge ver">' + V.esc(e.resume_ia.mention || "Généré par IA, non vérifié") +
        '</span> <span class="badge reg">' + V.esc(e.resume_ia.categorie_libelle || "") + "</span><ul>" +
        (e.resume_ia.resume || []).map(function (l) { return "<li>" + V.esc(l) + "</li>"; }).join("") + "</ul>" +
        "<small>" + V.esc(e.resume_ia.modele) + " · prompt " + V.esc(e.resume_ia.version_prompt) + " · " +
        V.esc(V.date(e.resume_ia.genere_le)) + "</small></div>" : "") +
      (e.resume ? '<details class="resume"><summary>Résumé (texte source' + (e.type === "essai" ? " du registre" : "") +
        ", en anglais)</summary><p lang=\"en\">" + V.esc(e.resume) + "</p></details>"
        : '<p class="vide" style="margin-top:6px">Aucun résumé disponible dans la source.</p>') +
      '<div class="actions">' + (e.fiche ? '<a href="' + V.esc(e.fiche) + '">Fiche détaillée →</a>' : "") +
      (e.lien_bu ? '<a class="bouton-bu" href="' + V.esc(e.lien_bu) + '" target="_blank" rel="noopener" title="Ouvre le catalogue de la BU avec la référence de l\'article : connectez-vous avec l\'ENT puis faites la demande de prêt entre bibliothèques.">📚 Demander à la BU</a>' : "") +
      '<a href="' + V.esc(e.lien_source) + '" target="_blank" rel="noopener">Voir la source ↗</a></div></article>';
  };
  /* Bouton « Résumé en français par l'IA » des cartes : le résumé (préparé chaque nuit) s'affiche à la demande */
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest("[data-resume-ia]");
    if (!b) return;
    var bloc = b.nextElementSibling, ouvert = b.getAttribute("aria-expanded") === "true";
    bloc.hidden = ouvert; b.setAttribute("aria-expanded", String(!ouvert));
    b.textContent = ouvert ? "✨ Résumé en français par l'IA" : "Masquer le résumé IA";
  });
})();
