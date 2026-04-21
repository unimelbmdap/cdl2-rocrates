// Client-side ForceAtlas2 layout paths.
//
// This module exists purely to isolate the FA2 dependency. The main
// `SigmaRenderer.render()` pipeline uses server-side-computed positions
// (config.precomputed: true) and never invokes these functions. They are
// kept as an escape hatch for paths that would otherwise need FA2
// installed on the Python side (the `fa2` extra + its native build).
//
// If FA2-on-the-browser ever becomes unwanted, deleting this file,
// removing the import + dispatch branches in `main.js`, and dropping
// `graphology-layout-forceatlas2` from `package.json` removes it
// cleanly.

import Sigma from "sigma";
import forceAtlas2 from "graphology-layout-forceatlas2";
import FA2Layout from "graphology-layout-forceatlas2/worker";

// Sync layout path — blocking FA2 computation.
export function runSyncLayout(
  graph,
  container,
  typeColours,
  { createRenderer, setupInteractions, setCurrent }
) {
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
    " edges — layout computed in " +
    dt +
    "ms";

  var renderer = createRenderer(graph, container);
  setCurrent(graph, renderer);
  setupInteractions(graph, renderer, typeColours);
}

// Animated (worker) layout path — non-blocking FA2 with controls.
export function runAnimatedLayout(
  graph,
  container,
  typeColours,
  { createRenderer, setupInteractions, setCurrent }
) {
  var status = document.getElementById("status");
  var btnToggle = document.getElementById("btn-toggle");
  var btnStop = document.getElementById("btn-stop");

  var renderer = createRenderer(graph, container);
  setCurrent(graph, renderer);
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
    "Layout running — " +
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
        " nodes) — resume or fix";
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
      status.textContent = "Layout paused — drag nodes or resume";
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
      status.textContent = "Layout finalised — positions fixed";
    }
  });
}

// Simple layout path — static thumbnail, no interactions.
export function runSimpleLayout(graph, container) {
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

// Snapshot a live sigma renderer into a static image. Used by initGrid
// to free the WebGL context after painting each thumbnail.
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

// Grid layout — multiple thumbnails on one page. Each cell gets its own
// FA2 pass, renders once, then snapshots to a static image so the WebGL
// context can be released before moving on.
export function initGrid({ buildGraph }) {
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
