/* Glaucoma Intelligence — bulle d'assistant (toutes les pages) + bouton « retour en haut ».

   Bascule automatique :
   1. si l'assistant local répond (http://127.0.0.1:8770/api/etat, délai court), la question lui est envoyée :
      réponse rédigée, chaque citation [PMID:…] / [NCT…] devient un lien ;
      (sans jeton GitHub, l'assistant renvoie lui-même les sources seules) ;
   2. sinon (site en ligne, assistant éteint) :
      - question préparée (config/questions_preparees.txt) : réponse rédigée par l'IA lors de la dernière mise à jour,
        citations vérifiées (site/data/reponses_preparees.json) ;
      - question sans rapport avec le glaucome (aucun mot du domaine, site/data/domaine.json) : on le dit ;
      - autre question : recherche sémantique dans le navigateur, les 5 documents les plus proches.
   L'historique reste dans la session de l'onglet (sessionStorage). Accessible au clavier ; Échap ferme le panneau. */
(function () {
  "use strict";
  var V = window.Veille;
  if (!V || document.getElementById("gi-bulle")) return;
  var ASSISTANT = "http://127.0.0.1:8770";
  var CLE = "gi-bulle-historique";
  var EXEMPLES = [  // remplacées par les questions préparées quand le fichier est disponible
    "Quels traitements du glaucome sans conservateur font l'objet de recherches cliniques ?",
    "Quels essais étudient le netarsudil ?",
    "Que dit la recherche sur l'intelligence artificielle pour dépister le glaucome ?",
  ];
  var modeAssistant = null; // null = pas encore testé, true / false ensuite
  var preparees = null, domaine = null;
  function json(nom) { return fetch(V.racine + "data/" + nom, { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }); }
  var pretes = Promise.all([json("reponses_preparees.json"), json("domaine.json")]).then(function (r) {
    preparees = r[0]; domaine = r[1];
    if (preparees && preparees.reponses && preparees.reponses.length) {
      EXEMPLES = preparees.reponses.map(function (x) { return x.question; });
      afficherExemples();
    }
  });
  function cle(q) { return V.norm(q).replace(/[^a-z0-9]+/g, " ").trim(); }
  function reponsePreparee(question) {
    if (!preparees || !preparees.reponses) return null;
    var c = cle(question);
    return preparees.reponses.filter(function (x) { return cle(x.question) === c; })[0] || null;
  }
  function horsSujet(question) {
    if (!domaine) return false;
    var q = " " + cle(question) + " ";
    var termes = (domaine.termes || []).map(cle).filter(function (t) { return t.length >= 2; });
    if (termes.some(function (t) { return q.indexOf(" " + t) >= 0; })) return false;
    return !labosCites(question).length;
  }
  function labosCites(question) {
    if (!domaine) return [];
    var q = " " + cle(question) + " ";
    return (domaine.laboratoires || []).filter(function (l) { var c = cle(l.nom); return c.length >= 4 && q.indexOf(" " + c + " ") >= 0; });
  }
  function carteLabo(l) {
    var lien = V.racine + "laboratoires.html?labo=" + encodeURIComponent(l.nom);
    var texte = l.produits ? "<b>" + V.esc(l.nom) + "</b> est un laboratoire titulaire de " + l.produits + " autorisation(s) de médicament(s) " +
      "contre le glaucome (" + V.esc(l.molecules.join(", ").toLowerCase()) + "), déclarée(s) par les autorités de santé : " + V.esc(l.pays.join(", ")) + "."
      : "<b>" + V.esc(l.nom) + "</b> apparaît dans la veille comme promoteur ou partenaire d'essais cliniques sur le glaucome.";
    return '<p class="gi-reponse">' + texte + ' <a href="' + V.esc(lien) + '">Voir sa fiche laboratoire →</a></p>';
  }

  function lienCitation(c) {
    return c.indexOf("PMID:") === 0 ? "https://pubmed.ncbi.nlm.nih.gov/" + c.slice(5) + "/" :
      c.indexOf("NCT") === 0 ? "https://clinicaltrials.gov/study/" + c : "https://openalex.org/" + c.split(":")[1];
  }
  function citationsEnLiens(texte) {
    // Listes « * … » ou « - … » du modèle → vraie liste à puces ; citations [PMID:…] / [NCT…] → liens
    var lignes = String(texte).split(/\n+/), html = "", liste = false;
    lignes.forEach(function (l) {
      var puce = /^\s*[*-]\s+/.test(l);
      if (puce && !liste) { html += "<ul>"; liste = true; }
      if (!puce && liste) { html += "</ul>"; liste = false; }
      var t = liensCitations(l.replace(/^\s*[*-]\s+/, ""));
      if (t.trim()) html += puce ? "<li>" + t + "</li>" : "<p>" + t + "</p>";
    });
    return html + (liste ? "</ul>" : "");
  }
  function liensCitations(texte) {
    return V.esc(texte).replace(/\[(PMID:\d+|NCT\d{8}|OpenAlex:W\d+)\]/g, function (m, c) {
      return '<a class="gi-cite" href="' + lienCitation(c) + '" target="_blank" rel="noopener">' + c + "</a>";
    });
  }
  function historique() { try { return JSON.parse(sessionStorage.getItem(CLE) || "[]"); } catch (e) { return []; } }
  function memoriser(h) { try { sessionStorage.setItem(CLE, JSON.stringify(h.slice(-30))); } catch (e) { /* navigation privée */ } }

  /* ---------- Construction ---------- */
  var bulle = document.createElement("button");
  bulle.id = "gi-bulle"; bulle.type = "button"; bulle.className = "gi-bulle";
  bulle.setAttribute("aria-label", "Ouvrir l'assistant Glaucoma Intelligence"); bulle.setAttribute("aria-expanded", "false");
  bulle.setAttribute("aria-controls", "gi-panneau");
  bulle.innerHTML = V.icone("assistant");
  var panneau = document.createElement("section");
  panneau.id = "gi-panneau"; panneau.className = "gi-panneau"; panneau.hidden = true;
  panneau.setAttribute("role", "dialog"); panneau.setAttribute("aria-labelledby", "gi-titre");
  panneau.innerHTML =
    '<header class="gi-entete"><div>' + V.LOGO + '<span><b id="gi-titre">Assistant</b><small id="gi-mode">Glaucoma Intelligence</small></span></div>' +
    '<button type="button" class="gi-fermer" aria-label="Fermer l\'assistant (Échap)">×</button></header>' +
    '<div class="gi-messages" id="gi-messages" aria-live="polite"></div>' +
    '<div class="gi-exemples" id="gi-exemples"></div>' +
    '<form class="gi-saisie" id="gi-form"><label for="gi-q" class="sr">Votre question</label>' +
    '<input id="gi-q" type="text" maxlength="500" autocomplete="off" placeholder="Posez votre question…">' +
    '<button type="button" class="gi-micro" id="gi-micro" hidden aria-label="Dicter la question à voix haute" title="Dicter la question">' +
    '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg></button>' +
    '<button type="submit" aria-label="Envoyer">' + V.icone("recherche") + "</button></form>";
  var haut = document.createElement("button");
  haut.type = "button"; haut.className = "gi-haut"; haut.hidden = true;
  haut.setAttribute("aria-label", "Revenir en haut de la page");
  haut.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';
  document.body.appendChild(haut);
  document.body.appendChild(panneau);
  document.body.appendChild(bulle);

  var messages = panneau.querySelector("#gi-messages"), champ = panneau.querySelector("#gi-q");

  function ajouter(role, html) {
    var div = document.createElement("div");
    div.className = "gi-msg gi-msg--" + role;
    div.innerHTML = html;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return div;
  }
  function rendreSources(sources, note) {
    return (note ? '<p class="gi-note">' + note + "</p>" : "") + "<ol class=\"gi-sources\">" + sources.map(function (s) {
      var cible = s.lien || (s.fiche ? V.racine + s.fiche : "#");
      return '<li><a href="' + V.esc(cible) + '" target="_blank" rel="noopener">' + V.esc(s.titre || s.id) + "</a> <small>" +
        V.esc(s.citation || s.id) + (s.score != null ? " · ressemblance " + Math.round(Math.min(1, s.score) * 100) + " %" : "") + "</small></li>";
    }).join("") + "</ol>";
  }
  function rejouer() {
    messages.innerHTML = "";
    var h = historique();
    if (!h.length) {
      ajouter("ia", "Bonjour ! Posez une question sur le glaucome : je cherche dans les essais et articles suivis, et je cite mes sources.");
    }
    h.forEach(function (m) { ajouter(m.role, m.html); });
  }
  function afficherExemples() { panneau.querySelector("#gi-exemples").innerHTML = EXEMPLES.map(function (q) {
    return '<button type="button" class="gi-exemple">' + V.esc(q) + "</button>";
  }).join(""); }
  afficherExemples();

  /* ---------- Bascule : assistant local, sinon recherche dans le navigateur ---------- */
  function avecDelai(promesse, ms) {
    return Promise.race([promesse, new Promise(function (_, rej) { setTimeout(function () { rej(new Error("délai dépassé")); }, ms); })]);
  }
  function testerAssistant() {
    if (modeAssistant !== null) return Promise.resolve(modeAssistant);
    return avecDelai(fetch(ASSISTANT + "/api/etat", { mode: "cors" }).then(function (r) { return r.ok; }), 1500)
      .catch(function () { return false; })
      .then(function (ok) {
        modeAssistant = ok;
        panneau.querySelector("#gi-mode").textContent = ok ? "Assistant local connecté (réponses en direct)" : "Version en ligne";
        return ok;
      });
  }
  function repondreAssistant(question) {
    return fetch(ASSISTANT + "/api/question", { method: "POST", mode: "cors", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question }) }).then(function (r) { return r.json(); }).then(function (d) {
      if (d.erreur && !d.sources) throw new Error(d.erreur);
      var valide = d.statut === "ok" || d.statut === "je_ne_sais_pas";
      if (d.reponse && valide) {
        return '<div class="gi-reponse">' + citationsEnLiens(d.reponse) + "</div>" +
          rendreSources(d.sources, "Sources retrouvées · modèle " + V.esc(d.modele) + " · prompt " + V.esc(d.version_prompt));
      }
      return rendreSources(d.sources, d.statut === "sans_jeton" ? "L'assistant local n'a pas de clé IA (GEMINI_API_KEY dans .env) : voici seulement les documents retrouvés."
        : "Réponse non affichée (" + V.esc(d.statut) + ") — voici les sources retrouvées.");
    });
  }
  function repondreNavigateur(question, attente) {
    // import() refuse un chemin relatif « nu » : on le résout en URL absolue
    return import(new URL(V.racine + "js/recherche-semantique.js", location.href).href).then(function (mod) {
      return mod.chercher(question, 5, V.racine, function (t) { attente.innerHTML = '<span class="gi-attente">' + V.esc(t) + "</span>"; });
    }).then(function (res) {
      return rendreSources(res, "Sur le site en ligne, je rédige une réponse seulement pour les questions proposées sous la conversation. " +
        "Pour votre question, voici les 5 documents de la veille qui s'en rapprochent le plus. Le pourcentage indique à quel point " +
        "chaque document ressemble à votre question : plus il est élevé, plus il est pertinent.");
    });
  }
  function repondrePreparee(p) {
    return '<div class="gi-reponse">' + citationsEnLiens(p.reponse) + "</div>" +
      rendreSources(p.sources.slice(0, 5), "Réponse rédigée par l'IA (" + V.esc(p.modele) + ") lors de la mise à jour du " +
        V.esc(V.date(preparees.genere_le)) + ", uniquement à partir des documents ci-dessous. Chaque référence citée a été vérifiée automatiquement.");
  }
  function repondreHorsSujet() {
    return '<p>Votre question ne semble pas porter sur le glaucome. Je réponds seulement à partir des essais cliniques, articles, ' +
      "laboratoires et autorisations sur le glaucome que la veille suit. Essayez par exemple une des questions proposées ci-dessous.</p>";
  }
  function poser(question) {
    question = (question || "").trim();
    if (!question) return;
    var h = historique();
    var html = V.esc(question);
    ajouter("moi", html); h.push({ role: "moi", html: html }); memoriser(h);
    var attente = ajouter("ia", '<span class="gi-attente">Je cherche…</span>');
    Promise.all([testerAssistant(), pretes]).then(function (r) {
      var ok = r[0];
      if (ok) return repondreAssistant(question).catch(function () { modeAssistant = false; return repondreNavigateur(question, attente); });
      var p = reponsePreparee(question);
      if (p) return repondrePreparee(p);
      if (horsSujet(question)) return repondreHorsSujet();
      var labos = labosCites(question);
      return repondreNavigateur(question, attente).then(function (html) {
        return labos.slice(0, 3).map(carteLabo).join("") + html;
      }, function (e) { if (labos.length) return labos.slice(0, 3).map(carteLabo).join(""); throw e; });
    }).then(function (rep) {
      attente.innerHTML = rep;
      var h2 = historique(); h2.push({ role: "ia", html: rep }); memoriser(h2);
    }).catch(function (e) {
      attente.innerHTML = '<p class="gi-note">Recherche indisponible (' + V.esc(e.message) + "). Ouvrez la page « Rechercher » ou lancez l'assistant local.</p>";
    });
  }

  /* ---------- Ouverture, fermeture, clavier ---------- */
  function ouvrir() {
    panneau.hidden = false; bulle.setAttribute("aria-expanded", "true"); bulle.classList.add("gi-bulle--ouverte");
    rejouer(); testerAssistant(); champ.focus();
  }
  function fermer() {
    panneau.hidden = true; bulle.setAttribute("aria-expanded", "false"); bulle.classList.remove("gi-bulle--ouverte"); bulle.focus();
  }
  bulle.addEventListener("click", function () { panneau.hidden ? ouvrir() : fermer(); });
  panneau.querySelector(".gi-fermer").addEventListener("click", fermer);
  panneau.addEventListener("keydown", function (e) { if (e.key === "Escape") { e.preventDefault(); fermer(); } });
  panneau.querySelector("#gi-form").addEventListener("submit", function (e) { e.preventDefault(); var q = champ.value; champ.value = ""; poser(q); });
  panneau.querySelector("#gi-exemples").addEventListener("click", function (e) {
    var b = e.target.closest(".gi-exemple"); if (b) poser(b.textContent);
  });

  /* ---------- Dictée vocale (reconnaissance vocale du navigateur : Chrome, Edge, Safari) ---------- */
  var Reco = window.SpeechRecognition || window.webkitSpeechRecognition;
  var micro = panneau.querySelector("#gi-micro");
  if (Reco) {
    micro.hidden = false;
    var reco = null;
    micro.addEventListener("click", function () {
      if (reco) { reco.stop(); return; }
      reco = new Reco();
      reco.lang = "fr-FR"; reco.interimResults = true; reco.maxAlternatives = 1;
      var avant = champ.placeholder;
      champ.placeholder = "Je vous écoute… parlez maintenant";
      micro.classList.add("gi-micro--actif"); micro.setAttribute("aria-label", "Arrêter la dictée");
      reco.onresult = function (e) {
        var t = ""; for (var i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
        champ.value = t;
        if (e.results[e.results.length - 1].isFinal) { reco.stop(); var q = champ.value; champ.value = ""; poser(q); }
      };
      reco.onerror = function (e) {
        if (e.error === "not-allowed") ajouter("ia", '<p class="gi-note">Le micro est bloqué : autorisez-le dans la barre d\'adresse du navigateur, puis réessayez.</p>');
      };
      reco.onend = function () { reco = null; champ.placeholder = avant; micro.classList.remove("gi-micro--actif"); micro.setAttribute("aria-label", "Dicter la question à voix haute"); };
      reco.start();
    });
  }

  /* Ouverture depuis un bouton de la page (ex. page « Poser une question ») */
  V.ouvrirAssistant = function (question) { if (panneau.hidden) ouvrir(); if (question) poser(question); };
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-ouvrir-assistant]");
    if (b) { e.preventDefault(); V.ouvrirAssistant(b.getAttribute("data-question") || ""); }
  });

  /* ---------- Retour en haut ---------- */
  var reduit = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function majHaut() { haut.hidden = window.scrollY < 500; }
  window.addEventListener("scroll", majHaut, { passive: true });
  majHaut(); // la page peut déjà être défilée (retour arrière, ancre)
  haut.addEventListener("click", function () {
    window.scrollTo({ top: 0, behavior: reduit ? "auto" : "smooth" });
    var cible = document.getElementById("contenu"); if (cible) { cible.setAttribute("tabindex", "-1"); cible.focus({ preventScroll: true }); }
  });
})();
