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

// Returns true if `value` parses as an http: or https: URL. Used to
// gate whether a string property value becomes a clickable <a href>.
function isHttpUrl(value) {
  if (typeof value !== "string") return false;
  try {
    var u = new URL(value);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch (e) {
    return false;
  }
}

// Build a clickable reference element pointing at `targetId` and
// append it to `parent`. The label is set via textContent and the
// node id via setAttribute, so attribute-context injection is
// structurally impossible — no escaping required at call sites.
function appendClickableRef(parent, targetId, label) {
  var el = document.createElement("a");
  el.className = "detail-link";
  el.setAttribute("data-node-id", targetId);
  el.setAttribute("title", targetId);
  el.textContent = label;
  parent.appendChild(el);
}

// Single point of colour mutation. `highlighted` is either a Set of
// node ids (those stay full-colour; everything else dims) or null
// (everything restored to originalColor).
//
// The future type-filter spec extends this function with a third
// branch — filter-hidden nodes always dim, even inside the
// highlighted set. Priority: filter-hidden > highlight-dimmed > original.
function applyColours(graph, highlighted) {
  var dimColour = isDark ? DIM_DARK : DIM_LIGHT;
  graph.forEachNode(function (nid, na) {
    var colour;
    if (highlighted && !highlighted.has(nid)) {
      colour = dimColour;
    } else {
      colour = na.originalColor;
    }
    graph.setNodeAttribute(nid, "color", colour);
  });
}

// Render a property value as a safe HTML string. Strings, numbers,
// and booleans are escaped via escapeHtml. References to known nodes
// become clickable <a data-node-id> elements built via DOM
// construction. URLs are gated through isHttpUrl. Arrays render
// inline (capped at 8 items). Non-reference objects render compactly,
// one level deep.
function renderValue(v, graph) {
  if (v === null || v === undefined) return '<span class="detail-row">—</span>';

  // Reference shape: {"@id": "<id>"}
  if (
    typeof v === "object" &&
    !Array.isArray(v) &&
    Object.prototype.hasOwnProperty.call(v, "@id")
  ) {
    var targetId = v["@id"];
    if (graph.hasNode(targetId)) {
      var holder = document.createElement("span");
      var label = graph.getNodeAttribute(targetId, "label") || targetId;
      appendClickableRef(holder, targetId, label);
      return holder.innerHTML;
    }
    // Missing reference. Build via DOM construction so an id containing
    // a quote cannot break out of the surrounding markup. escapeHtml is
    // text-context only and does NOT escape attribute quotes — never
    // build attributes by string concatenation here.
    var missing = document.createElement("span");
    missing.className = "detail-row";
    missing.textContent = targetId;
    var missingHolder = document.createElement("div");
    missingHolder.appendChild(missing);
    return missingHolder.innerHTML;
  }

  if (Array.isArray(v)) {
    if (v.length === 0) return '<span class="detail-row">—</span>';
    var cap = 8;
    var shown = v.slice(0, cap).map(function (item) {
      return renderValue(item, graph);
    });
    var suffix = v.length > cap ? ', <span class="detail-row">+' +
      (v.length - cap) + " more</span>" : "";
    return shown.join(", ") + suffix;
  }

  if (typeof v === "object") {
    // Non-reference object: compact one-level render.
    var parts = Object.keys(v).map(function (k) {
      return escapeHtml(k) + ": " + escapeHtml(String(v[k]));
    });
    return '<span class="detail-row">' + parts.join(", ") + "</span>";
  }

  if (typeof v === "boolean") {
    return '<span class="detail-row">' + (v ? "true" : "false") + "</span>";
  }

  if (isHttpUrl(v)) {
    var a = document.createElement("a");
    a.setAttribute("href", v);
    a.setAttribute("target", "_blank");
    a.setAttribute("rel", "noopener");
    a.className = "detail-link";
    a.textContent = v;
    return a.outerHTML;
  }

  return '<span class="detail-row">' + escapeHtml(String(v)) + "</span>";
}

// Ordered list of property keys to surface first in the panel,
// if present. Everything else is appended alphabetically after.
var WELL_KNOWN_PROPERTY_KEYS = ["description", "datePublished", "author"];

function renderPanel(nodeId, graph) {
  var det = document.getElementById("details");
  det.innerHTML = "";

  var attrs = graph.getNodeAttributes(nodeId);

  // (a) Header
  var header = document.createElement("div");
  header.className = "detail-section";
  header.innerHTML =
    "<h4>" + escapeHtml(attrs.label) + "</h4>" +
    '<div class="detail-row"><span class="detail-label">Type:</span> ' +
    escapeHtml(attrs.entityType) + "</div>" +
    '<div class="detail-row"><span class="detail-label">ID:</span> ' +
    escapeHtml(nodeId) + "</div>" +
    '<div class="detail-row"><span class="detail-label">Connections:</span> ' +
    escapeHtml(String(attrs.degree)) + "</div>";
  det.appendChild(header);

  // (b) Properties
  var props = attrs.properties || {};
  var keys = Object.keys(props);
  if (keys.length > 0) {
    var orderedKeys = [];
    WELL_KNOWN_PROPERTY_KEYS.forEach(function (k) {
      if (Object.prototype.hasOwnProperty.call(props, k)) orderedKeys.push(k);
    });
    keys
      .filter(function (k) { return WELL_KNOWN_PROPERTY_KEYS.indexOf(k) === -1; })
      .sort()
      .forEach(function (k) { orderedKeys.push(k); });

    var propSection = document.createElement("div");
    propSection.className = "detail-section";
    var propHead = document.createElement("div");
    propHead.className = "detail-subhead";
    propHead.textContent = "Properties";
    propSection.appendChild(propHead);

    orderedKeys.forEach(function (k) {
      var row = document.createElement("div");
      row.className = "detail-row";
      row.innerHTML =
        '<span class="detail-label">' + escapeHtml(k) + ":</span> " +
        renderValue(props[k], graph);
      propSection.appendChild(row);
    });
    det.appendChild(propSection);
  }

  // (c) Connected to — neighbours grouped by direction + edge type.
  if (graph.degree(nodeId) > 0) {
    var groups = {}; // key: e.g. "out:authoredBy" -> { label: "authoredBy →", entries: [{id, name}] }
    graph.forEachEdge(nodeId, function (edge, eattrs, source, target) {
      var outgoing = source === nodeId;
      var other = outgoing ? target : source;
      var type = eattrs.type || "related";
      var groupKey = (outgoing ? "out:" : "in:") + type;
      if (!groups[groupKey]) {
        groups[groupKey] = {
          label: outgoing ? type + " →" : "← " + type,
          entries: [],
        };
      }
      groups[groupKey].entries.push({
        id: other,
        name: graph.getNodeAttribute(other, "label") || other,
      });
    });

    var connSection = document.createElement("div");
    connSection.className = "detail-section";
    var connHead = document.createElement("div");
    connHead.className = "detail-subhead";
    connHead.textContent = "Connected to";
    connSection.appendChild(connHead);

    Object.keys(groups).sort().forEach(function (gk) {
      var group = groups[gk];
      var groupEl = document.createElement("div");
      groupEl.className = "detail-group";
      var groupLabel = document.createElement("div");
      groupLabel.className = "detail-group-label";
      groupLabel.textContent = group.label;
      groupEl.appendChild(groupLabel);

      var list = document.createElement("div");
      list.className = "detail-row";
      group.entries.forEach(function (entry, i) {
        if (i > 0) list.appendChild(document.createTextNode(", "));
        appendClickableRef(list, entry.id, entry.name);
      });
      groupEl.appendChild(list);
      connSection.appendChild(groupEl);
    });
    det.appendChild(connSection);
  }

  det.style.display = "block";
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
  applyColours,
  hexToRgba,
  escapeHtml,
  toggleTheme,
  isHttpUrl,
  appendClickableRef,
  renderValue,
  renderPanel,
};
