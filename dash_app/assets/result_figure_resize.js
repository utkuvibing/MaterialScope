(function () {
  "use strict";

  function resizeResultFigures(root) {
    if (!window.Plotly || !window.Plotly.Plots) {
      return;
    }
    var scope = root && root.querySelectorAll ? root : document;
    var plots = scope.querySelectorAll(".ms-figure-host .js-plotly-plot");
    plots.forEach(function (plot) {
      window.requestAnimationFrame(function () {
        try {
          window.Plotly.Plots.resize(plot);
        } catch (error) {
          // Plotly may briefly expose a node before it is fully initialized.
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    resizeResultFigures(document);
  });

  var observer = new MutationObserver(function (mutations) {
    mutations.forEach(function (mutation) {
      mutation.addedNodes.forEach(function (node) {
        if (node.nodeType === 1) {
          resizeResultFigures(node);
        }
      });
    });
  });

  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("resize", function () {
    resizeResultFigures(document);
  });
})();
