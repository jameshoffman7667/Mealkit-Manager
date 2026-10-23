/* Registers the service worker, offers updates, and drives the Install button. No inline scripts. */
(function () {
  "use strict";

  function el(id) { return document.getElementById(id); }

  // ----- install -----
  var deferredPrompt = null;
  var installBox = el("install-box");
  var installBtn = el("install-btn");
  var iosHelp = el("install-ios");
  var standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;

  if (installBox && standalone) {
    installBox.hidden = false;
    var done = el("install-done");
    if (done) done.hidden = false;
  }
  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    deferredPrompt = e;
    if (installBox && installBtn) { installBox.hidden = false; installBtn.hidden = false; }
  });
  if (installBtn) {
    installBtn.addEventListener("click", function () {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then(function () { deferredPrompt = null; installBtn.hidden = true; });
    });
  }
  var isIos = /iphone|ipad|ipod/i.test(navigator.userAgent);
  if (installBox && iosHelp && isIos && !standalone) { installBox.hidden = false; iosHelp.hidden = false; }

  // ----- confirmation prompts (replaces inline onsubmit handlers) -----
  document.addEventListener("submit", function (e) {
    var msg = e.target && e.target.getAttribute && e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // ----- service worker and update prompt -----
  if (!("serviceWorker" in navigator)) return;
  var banner = el("update-banner");
  var reloadBtn = el("update-reload");
  var hadController = !!navigator.serviceWorker.controller;
  var waiting = null;

  function offerUpdate(worker) {
    waiting = worker;
    if (banner) banner.hidden = false;
  }
  if (reloadBtn) {
    reloadBtn.addEventListener("click", function () { if (waiting) waiting.postMessage("SKIP_WAITING"); });
  }
  // Reload on controllerchange only if the page already had a controller. Reloading on the very first
  // install would wipe whatever the user has just typed.
  navigator.serviceWorker.addEventListener("controllerchange", function () {
    if (hadController) window.location.reload();
  });

  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).then(function (reg) {
      if (reg.waiting && navigator.serviceWorker.controller) offerUpdate(reg.waiting);
      reg.addEventListener("updatefound", function () {
        var w = reg.installing;
        if (!w) return;
        w.addEventListener("statechange", function () {
          if (w.state === "installed" && navigator.serviceWorker.controller) offerUpdate(w);
        });
      });
    }).catch(function () { /* the app works without it */ });
  });
})();
