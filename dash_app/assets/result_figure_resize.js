(function () {
  "use strict";

  function debugEnabled() {
    try {
      return window.localStorage && window.localStorage.getItem("materialscope.figureDebug") === "1";
    } catch (error) {
      return false;
    }
  }

  function debugLog() {
    if (debugEnabled() && window.console && window.console.log) {
      window.console.log.apply(window.console, arguments);
    }
  }

  debugLog("[MaterialScope figure resize] script loaded");

  function boxFor(element) {
    if (!element || !element.getBoundingClientRect) {
      return null;
    }
    var rect = element.getBoundingClientRect();
    return {
      width: rect.width,
      height: rect.height,
      top: rect.top,
      left: rect.left
    };
  }

  function resizeResultFigures(root) {
    if (!window.Plotly || !window.Plotly.Plots) {
      debugLog("[MaterialScope figure resize] Plotly unavailable");
      return;
    }
    var scope = root && root.querySelectorAll ? root : document;
    var plots = scope.querySelectorAll(".ms-figure-host .js-plotly-plot");
    debugLog("[MaterialScope figure resize] plots found", plots.length);
    plots.forEach(function (plot) {
      scheduleResize(plot, 0);
    });
  }

  function scheduleResize(plot, attempt) {
    var delays = [0, 80, 240, 600];
    var delay = delays[Math.min(attempt, delays.length - 1)];
    window.requestAnimationFrame(function () {
      window.setTimeout(function () {
        var host = plot.closest(".ms-figure-host");
        var graph = host && host.querySelector(".dash-graph");
        var svg = plot.querySelector("svg.main-svg");
        debugLog("[MaterialScope figure resize] resizing", {
          attempt: attempt,
          host: boxFor(host),
          graph: boxFor(graph),
          plot: boxFor(plot),
          svg: boxFor(svg)
        });
        try {
          window.Plotly.Plots.resize(plot);
        } catch (error) {
          debugLog("[MaterialScope figure resize] resize failed", error);
        }
        var plotBox = boxFor(plot);
        var svgBox = boxFor(svg);
        var visible = plotBox && svgBox && plotBox.width > 300 && plotBox.height > 300 && svgBox.width > 300 && svgBox.height > 300;
        if (!visible && attempt < delays.length - 1) {
          scheduleResize(plot, attempt + 1);
        }
      }, delay);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    resizeResultFigures(document);
  });

  var observer = new MutationObserver(function (mutations) {
    mutations.forEach(function (mutation) {
      mutation.addedNodes.forEach(function (node) {
        if (node.nodeType === 1) {
          if (node.matches && (node.matches(".dash-graph") || node.matches(".js-plotly-plot"))) {
            debugLog("[MaterialScope figure resize] graph inserted", node);
          } else if (node.querySelector && node.querySelector(".dash-graph, .js-plotly-plot")) {
            debugLog("[MaterialScope figure resize] graph subtree inserted", node);
          }
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
