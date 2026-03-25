import Graph from "graphology";
import Sigma from "sigma";
import forceAtlas2 from "graphology-layout-forceatlas2";
import FA2Layout from "graphology-layout-forceatlas2/worker";

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
  var graph = new Graph();

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
    });
  });

  graphData.edges.forEach(function (e) {
    if (!graph.hasEdge(e.source, e.target)) {
      graph.addEdge(e.source, e.target, {
        color: e.color,
        size: 0.3,
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
// Sync layout path — blocking FA2 computation
// ---------------------------------------------------------------------------

function runSyncLayout(graph, container, typeColours) {
  var status = document.getElementById("status");
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
  currentGraph = graph;
  currentRenderer = renderer;
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
  currentGraph = graph;
  currentRenderer = renderer;
  setupInteractions(graph, renderer, typeColours);

  var settings = forceAtlas2.inferSettings(graph);
  settings.barnesHutOptimize = graph.order > 200;
  settings.slowDown = 5;

  var fa2Layout = new FA2Layout(graph, { settings: settings });
  var isRunning = false;

  btnToggle.style.display = "inline-block";
  btnStop.style.display = "inline-block";

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
// Simple layout path — static thumbnail, no interactions
// ---------------------------------------------------------------------------

function runSimpleLayout(graph, container) {
  var settings = forceAtlas2.inferSettings(graph);
  settings.barnesHutOptimize = graph.order > 200;
  forceAtlas2.assign(graph, { iterations: 100, settings: settings });

  new Sigma(graph, container, {
    renderEdgeLabels: false,
    renderLabels: false,
    defaultEdgeColor: "rgba(255,255,255,0.1)",
    edgeColor: { attribute: "color" },
    defaultEdgeType: "line",
    zIndex: true,
    minCameraRatio: 0.02,
    maxCameraRatio: 20,
    enableCameraRotation: false,
  });
}

// ---------------------------------------------------------------------------
// Grid layout — multiple thumbnails on one page
// ---------------------------------------------------------------------------

function snapshotSigma(renderer, container) {
  // Sigma uses layered canvases — composite them into a single image.
  var canvases = container.querySelectorAll("canvas");
  var composite = document.createElement("canvas");
  var first = canvases[0];
  composite.width = first.width;
  composite.height = first.height;
  var ctx = composite.getContext("2d");
  for (var j = 0; j < canvases.length; j++) {
    ctx.drawImage(canvases[j], 0, 0);
  }

  // Replace sigma canvases with a static image.
  var img = document.createElement("img");
  img.src = composite.toDataURL("image/png");
  img.style.width = "100%";
  img.style.height = "100%";
  img.style.display = "block";

  renderer.kill();
  container.innerHTML = "";
  container.appendChild(img);
}

function initGrid() {
  var grid = document.getElementById("grid");
  var items = window.gridData || [];

  // Force preserveDrawingBuffer so we can snapshot WebGL canvases.
  var origGetContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (type, attrs) {
    if (type === "webgl" || type === "webgl2") {
      attrs = Object.assign({}, attrs, { preserveDrawingBuffer: true });
    }
    return origGetContext.call(this, type, attrs);
  };

  // Pre-build all cells so the grid is visible immediately.
  var cells = [];
  items.forEach(function (item, i) {
    var cell = document.createElement("div");
    cell.className = "grid-cell";

    var label = document.createElement("div");
    label.className = "cell-label";
    label.textContent = item.label || "Crate " + (i + 1);
    cell.appendChild(label);

    var meta = document.createElement("div");
    meta.className = "cell-meta";
    var nNodes = item.totalNodes || item.graphData.nodes.length;
    var nEdges = item.totalEdges || item.graphData.edges.length;
    meta.textContent = nNodes + " nodes, " + nEdges + " edges";
    cell.appendChild(meta);

    var container = document.createElement("div");
    container.className = "sigma-container";
    container.id = "sigma-" + i;
    cell.appendChild(container);

    grid.appendChild(cell);
    cells.push({ item: item, container: container });
  });

  // Render one graph at a time: compute layout, let sigma paint one
  // frame, snapshot to a static image, destroy the WebGL context,
  // then move on. Never holds more than one context at a time.
  var idx = 0;
  function renderNext() {
    if (idx >= cells.length) return;
    var entry = cells[idx];
    var graph = buildGraph(entry.item.graphData);
    var n = graph.order;
    var settings = forceAtlas2.inferSettings(graph);
    settings.barnesHutOptimize = n > 200;

    // Scale iterations down for large graphs — thumbnails don't need
    // perfect layout, just a recognisable shape.
    var iters = n > 10000 ? 5 : n > 2000 ? 15 : n > 500 ? 30 : 50;
    forceAtlas2.assign(graph, { iterations: iters, settings: settings });

    // Edges drove the layout — clear them unless the caller wants them visible.
    if (!window.sigmaConfig.showEdges) {
      graph.clearEdges();
    }

    var renderer = new Sigma(graph, entry.container, {
      renderEdgeLabels: false,
      renderLabels: false,
      defaultEdgeColor: "rgba(255,255,255,0.1)",
      edgeColor: { attribute: "color" },
      defaultEdgeType: "line",
      zIndex: true,
    });

    // Wait for sigma to paint, then snapshot and move on.
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        snapshotSigma(renderer, entry.container);
        idx++;
        setTimeout(renderNext, 0);
      });
    });
  }
  renderNext();
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

function init() {
  var config = window.sigmaConfig || {};

  // Grid mode — multiple graphs on one page
  if (config.grid) {
    initGrid();
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
    currentGraph = graph;
    currentRenderer = renderer;
    var status = document.getElementById("status");
    if (status) {
      status.textContent =
        graph.order +
        " nodes, " +
        graph.size +
        " edges \u2014 pre-computed layout";
    }
    setupInteractions(graph, renderer, window.typeColours);
  } else if (config.simple) {
    runSimpleLayout(graph, container);
  } else if (config.animated) {
    runAnimatedLayout(graph, container, window.typeColours);
  } else {
    runSyncLayout(graph, container, window.typeColours);
  }
}

document.addEventListener("DOMContentLoaded", init);

// Export for IIFE global access
export { init, initGrid, buildGraph, createRenderer, setupInteractions, hexToRgba, escapeHtml, toggleTheme };
