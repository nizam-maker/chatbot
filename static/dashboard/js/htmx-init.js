// static/dashboard/js/htmx-init.js
// Loaded once in the persistent shell. Dispatches to the registered view
// init function for the current path after every HTMX swap AND on the
// very first full-page load — both paths funnel through dispatchView().
(function () {
  function updateActiveNav(path) {
    document.querySelectorAll(".nav-item").forEach(a =>
      a.classList.toggle("active", a.getAttribute("href") === path));
  }

  function dispatchView() {
    const fn = (window.dashboardViews || {})[window.location.pathname];
    if (fn) Promise.resolve(fn()).catch(() => { /* auth redirect already in flight */ });
    updateActiveNav(window.location.pathname);
  }

  document.body.addEventListener("htmx:afterSettle", dispatchView);
  document.addEventListener("DOMContentLoaded", dispatchView);
})();
