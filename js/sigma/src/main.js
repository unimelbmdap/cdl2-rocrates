import Graph from "graphology";
import Sigma from "sigma";

import {
  initGrid,
  runAnimatedLayout,
  runSimpleLayout,
  runSyncLayout,
} from "./fa2_layout.js";

// ---------------------------------------------------------------------------
// Theme state
// ---------------------------------------------------------------------------

var isDark = true;
var DIM_DARK = "#333";
var DIM_LIGHT = "#ccc";
var EDGE_ALPHA_DARK = 0.15;
var EDGE_ALPHA_LIGHT = 0.35;
var currentGraph = null;
var currentRenderer = null;

// Expose a setter so the FA2 layout module can hand back its graph +
// renderer without reaching into this module's globals.
function setCurrent(graph, renderer) {
  currentGraph = graph;
  currentRenderer = renderer;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escapeHtml(text) {
  var div = document.createElement("div");
  div.appendChild(document.createTextNode(String(text)));
  return div.innerHTML;
}

function toggleTheme() {
  isDark = !isDark;
  document.documentElement.setAttribute("data-theme", isDark ? "dark" : "light");

  var btnTheme = document.getElementById("btn-theme");
  if (btnTheme) {
    btnTheme.textContent = isDark ? "Light" : "Dark";
  }

  // Update sigma background colour
  if (currentRenderer) {
    currentRenderer.setSetting(
      "labelColor",
      { color: isDark ? "#d8dade" : "#1a1a2e" }
    );
  }

  // Update neighbourhood dim colours on any highlighted nodes
  if (currentGraph) {
    var dimColour = isDark ? DIM_DARK : DIM_LIGHT;
    currentGraph.forEachNode(function (nid, na) {
      if (na.color === DIM_DARK || na.color === DIM_LIGHT) {
        currentGraph.setNodeAttribute(nid, "color", dimColour);
      }
    });
    if (currentRenderer) {
      currentRenderer.refresh();
    }
  }
}

function hexToRgba(hex, alpha) {
  hex = hex.replace("#", "");
  var r = parseInt(hex.substring(0, 2), 16);
  var g = parseInt(hex.substring(2, 4), 16);
  var b = parseInt(hex.substring(4, 6), 16);
  return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
}

// ---------------------------------------------------------------------------
// Graph construction
// ---------------------------------------------------------------------------

function buildGraph(graphData) {
  var graph = new Graph({ multi: true, type: "directed" });

  graphData.nodes.forEach(function (n) {
    graph.addNode(n.id, {
      x: n.x,
      y: n.y,
      size: n.size,
      color: n.color,
      label: n.label,
      entityType: n.entityType,
      degree: n.degree,
      originalColor: n.color,
      properties: n.properties || {},
    });
  });

  graphData.edges.forEach(function (e) {
    graph.addDirectedEdgeWithKey(e.id, e.source, e.target, {
      color: e.color,
      size: e.size !== undefined ? e.size : 0.3,
      type: e.type,
    });
  });

  return graph;
}

// ---------------------------------------------------------------------------
// Renderer
// ---------------------------------------------------------------------------

function createRenderer(graph, container) {
  return new Sigma(graph, container, {
    renderEdgeLabels: false,
    renderLabels: false,
    defaultEdgeColor: "rgba(255,255,255,0.1)",
    edgeColor: { attribute: "color" },
    defaultEdgeType: "line",
    zIndex: true,
    minCameraRatio: 0.02,
    maxCameraRatio: 20,
  });
}

// ---------------------------------------------------------------------------
// Interactions: legend, click-details, neighbourhood highlight, cursors
// ---------------------------------------------------------------------------

function setupInteractions(graph, renderer, typeColours) {
  // Legend (bottom-left)
  var legendEl = document.getElementById("legend");
  var legendHtml = "";
  Object.keys(typeColours)
    .sort()
    .forEach(function (t) {
      legendHtml +=
        '<div class="legend-item"><div class="legend-swatch" style="background:' +
        typeColours[t] +
        '"></div><span>' +
        escapeHtml(t) +
        "</span></div>";
    });
  legendEl.innerHTML = legendHtml;

  var container = document.getElementById("sigma-container");

  // Click node — show details panel and highlight neighbourhood
  renderer.on("clickNode", function (ev) {
    var attrs = graph.getNodeAttributes(ev.node);
    var det = document.getElementById("details");
    det.innerHTML =
      "<h4>" +
      escapeHtml(attrs.label) +
      "</h4>" +
      '<div class="detail-row"><span class="detail-label">Type:</span> ' +
      escapeHtml(attrs.entityType) +
      "</div>" +
      '<div class="detail-row"><span class="detail-label">Connections:</span> ' +
      attrs.degree +
      "</div>" +
      '<div class="detail-row"><span class="detail-label">ID:</span> ' +
      escapeHtml(ev.node) +
      "</div>";
    det.style.display = "block";

    var neighbours = new Set(graph.neighbors(ev.node));
    neighbours.add(ev.node);
    var dimColour = isDark ? DIM_DARK : DIM_LIGHT;
    graph.forEachNode(function (nid, na) {
      graph.setNodeAttribute(
        nid,
        "color",
        neighbours.has(nid) ? na.originalColor : dimColour
      );
    });
    renderer.refresh();
  });

  // Click stage — reset highlights
  renderer.on("clickStage", function () {
    document.getElementById("details").style.display = "none";
    graph.forEachNode(function (nid, na) {
      graph.setNodeAttribute(nid, "color", na.originalColor);
    });
    renderer.refresh();
  });

  // Cursor changes
  container.style.cursor = "default";
  renderer.on("enterNode", function () {
    container.style.cursor = "pointer";
  });
  renderer.on("leaveNode", function () {
    container.style.cursor = "default";
  });
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

// Wrapper around initGrid that threads this module's `buildGraph` in, so
// the exported IIFE shape (`CrategraphSigma.initGrid()`) keeps its old
// no-argument contract.
function initGridInternal() {
  initGrid({ buildGraph: buildGraph });
}

function init() {
  var config = window.sigmaConfig || {};

  // Grid mode — multiple graphs on one page (FA2-driven).
  if (config.grid) {
    initGridInternal();
    return;
  }

  var container = document.getElementById("sigma-container");
  var graph = buildGraph(window.graphData);

  // Theme toggle
  var btnTheme = document.getElementById("btn-theme");
  if (btnTheme) {
    btnTheme.addEventListener("click", toggleTheme);
  }

  if (config.precomputed) {
    // Positions already computed server-side — skip FA2, render directly.
    var renderer = createRenderer(graph, container);
    setCurrent(graph, renderer);
    var status = document.getElementById("status");
    if (status) {
      status.textContent =
        graph.order +
        " nodes, " +
        graph.size +
        " edges — pre-computed layout";
    }
    setupInteractions(graph, renderer, window.typeColours);
  } else {
    // All remaining paths are FA2-driven. They live in fa2_layout.js.
    var hooks = {
      createRenderer: createRenderer,
      setupInteractions: setupInteractions,
      setCurrent: setCurrent,
    };
    if (config.simple) {
      runSimpleLayout(graph, container);
    } else if (config.animated) {
      runAnimatedLayout(graph, container, window.typeColours, hooks);
    } else {
      runSyncLayout(graph, container, window.typeColours, hooks);
    }
  }
}

document.addEventListener("DOMContentLoaded", init);

// Export for IIFE global access
export {
  init,
  initGridInternal as initGrid,
  buildGraph,
  createRenderer,
  setupInteractions,
  hexToRgba,
  escapeHtml,
  toggleTheme,
};
