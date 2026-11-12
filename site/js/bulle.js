/* Glaucoma Intelligence — bulle d'assistant (toutes les pages) + bouton « retour en haut ».

   Bascule automatique :
   1. si l'assistant local répond (http://127.0.0.1:8770/api/etat, délai court), la question lui est envoyée :
      réponse rédigée, chaque citation [PMID:…] / [NCT…] devient un lien ;
      (sans jeton GitHub, l'assistant renvoie lui-même les sources seules) ;
   2. sinon (site en ligne, assistant éteint), recherche sémantique dans le navigateur :
      les 5 sources les plus pertinentes, avec la mention « mode sources seulement ».
   L'historique reste dans la session de l'onglet (sessionStorage). Accessible au clavier ; Échap ferme le panneau. */
(function () {
  "use strict";
  var V = window.Veille;
  if (!V || document.getElementById("gi-bulle")) return;
  var ASSISTANT = "http://127.0.0.1:8770";
  var CLE = "gi-bulle-historique";
  var EXEMPLES = [
    "Quels traitements du glaucome sans conservateur font l'objet de recherches cliniques ?",
    "Quels essais étudient le netarsudil ?",
    "Que dit la recherche sur l'intelligence artificielle pour dépister le glaucome ?",
  ];
  var modeAssistant = null; // null = pas encore testé, true / false ensuite

  function lienCitation(c) {
    return c.indexOf("PMID:") === 0 ? "https://pubmed.ncbi.nlm.nih.gov/" + c.slice(5) + "/" :
      c.indexOf("NCT") === 0 ? "https://clinicaltrials.gov/study/" + c : "https://openalex.org/" + c.split(":")[1];
  }
  function citationsEnLiens(texte) {
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
        V.esc(s.citation || s.id) + (s.score != null ? " · " + Number(s.score).toFixed(3) : "") + "</small></li>";
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
  panneau.querySelector("#gi-exemples").innerHTML = EXEMPLES.map(function (q) {
    return '<button type="button" class="gi-exemple">' + V.esc(q) + "</button>";
  }).join("");

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
        panneau.querySelector("#gi-mode").textContent = ok ? "Assistant local connecté" : "Mode sources seulement";
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
      return rendreSources(d.sources, d.statut === "sans_jeton" ? "Mode sources seulement : l'assistant n'a pas de jeton GitHub pour rédiger une réponse."
        : "Réponse non affichée (" + V.esc(d.statut) + ") — voici les sources retrouvées.");
    });
  }
  function repondreNavigateur(question, attente) {
    // import() refuse un chemin relatif « nu » : on le résout en URL absolue
    return import(new URL(V.racine + "js/recherche-semantique.js", location.href).href).then(function (mod) {
      return mod.chercher(question, 5, V.racine, function (t) { attente.innerHTML = '<span class="gi-attente">' + V.esc(t) + "</span>"; });
    }).then(function (res) {
      return rendreSources(res, "Mode sources seulement : l'assistant local n'est pas lancé. Voici les 5 sources les plus pertinentes.");
    });
  }
  function poser(question) {
    question = (question || "").trim();
    if (!question) return;
    var h = historique();
    var html = V.esc(question);
    ajouter("moi", html); h.push({ role: "moi", html: html }); memoriser(h);
    var attente = ajouter("ia", '<span class="gi-attente">Je cherche…</span>');
    testerAssistant().then(function (ok) {
      return ok ? repondreAssistant(question).catch(function () { modeAssistant = false; return repondreNavigateur(question, attente); })
        : repondreNavigateur(question, attente);
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
