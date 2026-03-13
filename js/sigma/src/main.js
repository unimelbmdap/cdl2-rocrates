import Graph from "graphology";
import Sigma from "sigma";
import forceAtlas2 from "graphology-layout-forceatlas2";
import FA2Layout from "graphology-layout-forceatlas2/worker";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escapeHtml(text) {
  var div = document.createElement("div");
  div.appendChild(document.createTextNode(String(text)));
  return div.innerHTML;
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
  var graph = new Graph();

  graphData.nodes.forEach(function (n) {
    graph.addNode(n.id, {
      x: n.x,
      y: n.y,
      size: n.size,
      color: n.color,
      label: n.label,
      entityType: n.type,
      degree: n.degree,
      originalColor: n.color,
    });
  });

  graphData.edges.forEach(function (e) {
    if (!graph.hasEdge(e.source, e.target)) {
      graph.addEdge(e.source, e.target, {
        color: e.color,
        size: 0.5,
        relType: e.type,
      });
    }
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
        t +
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
    graph.forEachNode(function (nid, na) {
      graph.setNodeAttribute(
        nid,
        "color",
        neighbours.has(nid) ? na.originalColor : "#333"
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
// Sync layout path — blocking FA2 computation
// ---------------------------------------------------------------------------

function runSyncLayout(graph, container, typeColours) {
  var status = document.getElementById("status");
  status.textContent = "Building graph...";

  status.textContent = "Computing layout...";
  var t0 = performance.now();
  var settings = forceAtlas2.inferSettings(graph);
  settings.barnesHutOptimize = graph.order > 200;
  forceAtlas2.assign(graph, { iterations: 100, settings: settings });
  var dt = (performance.now() - t0).toFixed(0);
  status.textContent =
    graph.order +
    " nodes, " +
    graph.size +
    " edges \u2014 layout computed in " +
    dt +
    "ms";

  var renderer = createRenderer(graph, container);
  setupInteractions(graph, renderer, typeColours);
}

// ---------------------------------------------------------------------------
// Animated (worker) layout path — non-blocking FA2 with controls
// ---------------------------------------------------------------------------

function runAnimatedLayout(graph, container, typeColours) {
  var status = document.getElementById("status");
  var btnToggle = document.getElementById("btn-toggle");
  var btnStop = document.getElementById("btn-stop");

  var renderer = createRenderer(graph, container);
  setupInteractions(graph, renderer, typeColours);

  var settings = forceAtlas2.inferSettings(graph);
  settings.barnesHutOptimize = graph.order > 200;
  settings.slowDown = 5;

  var fa2Layout = new FA2Layout(graph, { settings: settings });
  var isRunning = false;

  fa2Layout.start();
  isRunning = true;
  btnToggle.textContent = "Pause Layout";
  btnToggle.classList.add("active");
  status.textContent =
    "Layout running \u2014 " +
    graph.order +
    " nodes, " +
    graph.size +
    " edges";

  // Auto-stop after 8 seconds
  setTimeout(function () {
    if (isRunning && fa2Layout) {
      fa2Layout.stop();
      isRunning = false;
      btnToggle.textContent = "Resume Layout";
      btnToggle.classList.remove("active");
      status.textContent =
        "Layout converged (" +
        graph.order +
        " nodes) \u2014 resume or fix";
    }
  }, 8000);

  // Toggle pause/resume
  btnToggle.addEventListener("click", function () {
    if (!fa2Layout) return;
    if (isRunning) {
      fa2Layout.stop();
      isRunning = false;
      btnToggle.textContent = "Resume Layout";
      btnToggle.classList.remove("active");
      status.textContent = "Layout paused \u2014 drag nodes or resume";
    } else {
      fa2Layout.start();
      isRunning = true;
      btnToggle.textContent = "Pause Layout";
      btnToggle.classList.add("active");
      status.textContent = "Layout running...";
    }
  });

  // Stop permanently
  btnStop.addEventListener("click", function () {
    if (fa2Layout) {
      fa2Layout.stop();
      fa2Layout.kill();
      fa2Layout = null;
      isRunning = false;
      btnToggle.textContent = "Layout Finished";
      btnToggle.disabled = true;
      btnStop.disabled = true;
      status.textContent = "Layout finalised \u2014 positions fixed";
    }
  });
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

function init() {
  var container = document.getElementById("sigma-container");
  var graph = buildGraph(window.graphData);
  var config = window.sigmaConfig || {};

  if (config.animated) {
    runAnimatedLayout(graph, container, window.typeColours);
  } else {
    runSyncLayout(graph, container, window.typeColours);
  }
}

document.addEventListener("DOMContentLoaded", init);

// Export for IIFE global access
export { init, buildGraph, createRenderer, setupInteractions, hexToRgba, escapeHtml };
