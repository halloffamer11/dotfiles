// Inlined into the benchmark page by scripts/bench_page.py; never loaded on
// its own. It draws one score-against-cost plot per panel from the JSON in
// #bench-data. Every decision in that JSON (which lane a point is, what the
// pre-screen proposes off, which effort beats which) was made in Python; this
// file only filters what is shown, finds the frontier of it, and lays it out.
// `layout` is pure, so tests/test_bench_page.py runs it under node with no DOM.
// Text from a benchmark page is set with textContent only, never as markup.
(function () {
  "use strict";

  const EFFORT_ORDER = ["none", "low", "medium", "high", "xhigh", "max", "ultra"];
  const W = 880, H = 500;
  const PAD = { l: 58, r: 18, t: 14, b: 50 };
  const CHAR_PX = 6.6, LABEL_H = 12;
  const NO_HARNESS = "none";
  const SVG_NS = "http://www.w3.org/2000/svg";

  // --- numbers and axes ------------------------------------------------------

  function effortIndex(effort) {
    const i = EFFORT_ORDER.indexOf(effort);
    return i < 0 ? EFFORT_ORDER.length : i;
  }

  function logTicks(lo, hi) {
    const pick = (mantissas) => {
      const out = [];
      for (let e = Math.floor(Math.log10(lo)) - 1; Math.pow(10, e) <= hi; e++) {
        for (const m of mantissas) {
          const v = +(m * Math.pow(10, e)).toPrecision(6);
          if (v >= lo * 0.9999 && v <= hi * 1.0001) out.push(v);
        }
      }
      return out;
    };
    let ticks = pick([1, 2, 5]);
    if (ticks.length < 3) ticks = pick([1, 1.5, 2, 3, 4, 5, 6, 8]);
    if (ticks.length < 3) ticks = pick([1, 1.2, 1.4, 1.6, 1.8, 2, 2.5, 3, 3.5, 4, 4.5, 5, 6, 7, 8, 9]);
    return ticks;
  }

  // A round bound just outside the data on each side, with finer mantissas
  // than the ticks, so a board ending at $9,604 is not drawn to $20,000.
  function logDomain(values) {
    let lo = Math.min(...values), hi = Math.max(...values);
    if (hi / lo < 1.5) {
      const mid = Math.sqrt(lo * hi);
      lo = mid / 1.35;
      hi = mid * 1.35;
    }
    let loBound = null, hiBound = null;
    for (let e = Math.floor(Math.log10(lo)) - 1; Math.pow(10, e) <= hi * 10; e++) {
      for (const m of [1, 1.5, 2, 3, 4, 5, 6, 8]) {
        const v = +(m * Math.pow(10, e)).toPrecision(6);
        if (v <= lo * 0.92) loBound = v;
        if (v >= hi * 1.08 && hiBound === null) hiBound = v;
      }
    }
    return [loBound || lo * 0.8, hiBound || hi * 1.25];
  }

  // The score axis fits the points shown, not zero: a board whose scores all
  // sit between 0.6 and 0.9 is drawn across the whole height.
  function niceLinear(lo, hi, target) {
    target = target || 6;
    if (lo === hi) {
      const d = Math.abs(lo) * 0.1 || 1;
      lo -= d;
      hi += d;
    }
    const pad = (hi - lo) * 0.05;
    lo -= pad;
    hi += pad;
    const raw = (hi - lo) / target;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw * 0.999);
    const nlo = Math.floor(lo / step) * step, nhi = Math.ceil(hi / step) * step;
    const ticks = [];
    for (let v = nlo; v <= nhi + step * 1e-6; v += step) ticks.push(+v.toFixed(10));
    return { lo: nlo, hi: nhi, step, ticks };
  }

  function decimalsFor(step) {
    let d = 0;
    while (d < 6 && Math.abs(Math.round(step * Math.pow(10, d)) - step * Math.pow(10, d)) > 1e-6) d++;
    return d;
  }

  function fmtMoney(v) {
    if (v === null || v === undefined || !isFinite(v)) return "—";
    const a = Math.abs(v);
    if (a >= 100) return "$" + Math.round(v).toLocaleString("en-US");
    if (a >= 10) return "$" + v.toFixed(1);
    if (a >= 0.1) return "$" + v.toFixed(2).replace(/\.?0+$/, "");
    return "$" + String(+v.toPrecision(2));
  }

  function fmtTickMoney(v) {
    if (v >= 1000) return "$" + Math.round(v).toLocaleString("en-US");
    if (v >= 1) return "$" + String(+v.toPrecision(6));
    return "$" + String(+v.toPrecision(3));
  }

  // Fractions (every AA component) read to three places, points to one.
  function scoreDecimals(board) {
    return board.points.every((p) => p.score === null || Math.abs(p.score) <= 1.5) ? 3 : 1;
  }

  function fmtScore(v, unit, decimals) {
    if (v === null || v === undefined) return "—";
    return v.toFixed(decimals) + (unit === "%" ? "%" : "");
  }

  // --- what is shown, and its frontier ----------------------------------------

  function harnessKeys(p) {
    return p.harness && p.harness.length ? p.harness : [NO_HARNESS];
  }

  function isShown(p, st) {
    if (!p.plotted) return false;
    if (st.hiddenModels.has(p.model)) return false;
    if (st.hiddenEfforts.has(p.effort)) return false;
    return harnessKeys(p).some((h) => !st.hiddenHarness.has(h));
  }

  // The points nothing else beats: walking from cheapest to dearest, each one
  // scores more than every point to its left. A point that scores the same as
  // a cheaper one is not on it.
  function frontier(points) {
    const sorted = points.slice().sort((a, b) => a.cost - b.cost || b.score - a.score);
    const out = [];
    let best = -Infinity;
    for (const p of sorted) {
      if (p.score > best) {
        out.push(p);
        best = p.score;
      }
    }
    return out;
  }

  function frontierCandidates(shown, mode) {
    if (mode === "off") return [];
    if (mode === "lanes") return shown.filter((p) => p.lanes.length);
    return shown;
  }

  function labelText(p) {
    const weak = p.weak ? "?" : "";
    if (p.lanes.length) {
      return p.lanes[0].name + (p.lanes.length > 1 ? ` +${p.lanes.length - 1}` : "") + weak;
    }
    return `${p.name} ${p.effort}${weak}`;
  }

  function boxesClear(placed, box) {
    const [x0, y0, x1, y1] = box;
    return !placed.some(([a0, b0, a1, b1]) => x0 < a1 && a0 < x1 && y0 < b1 && b0 < y1);
  }

  // A label beside its point that lands on no other label and no point, or
  // null. A label that does not fit is dropped, never printed over another:
  // the tooltip and the tables still carry it.
  function place(text, cx, cy, placed, frame) {
    const width = text.length * CHAR_PX + 4;
    const [fx0, fy0, fx1, fy1] = frame;
    const slots = [[9, 4, "start"], [-9, 4, "end"], [9, -8, "start"], [-9, -8, "end"],
                   [9, 15, "start"], [-9, 15, "end"], [0, -11, "middle"], [0, 20, "middle"]];
    for (const [dx, dy, anchor] of slots) {
      const x = cx + dx, y = cy + dy;
      const x0 = anchor === "start" ? x : anchor === "end" ? x - width : x - width / 2;
      const box = [x0, y - LABEL_H + 3, x0 + width, y + 3];
      if (box[0] < fx0 || box[2] > fx1 || box[1] < fy0 || box[3] > fy1) continue;
      if (boxesClear(placed, box)) {
        placed.push(box);
        return { x, y, anchor, box };
      }
    }
    return null;
  }

  const KIND_RANK = { comparator: 0, own_other: 1, lane: 2, lane_off: 3 };

  // One wheel step about the pointer: the cost and score under (x, y) stay
  // under it, and every edge moves toward it by `factor` (below 1 zooms in).
  // Cost is on a log axis, so the cost edges move in log space. No DOM.
  function zoomAbout(d, p, x, y, factor) {
    const lx0 = Math.log10(d.xlo), lx1 = Math.log10(d.xhi);
    const fx = (x - p.x0) / (p.x1 - p.x0), fy = (p.y1 - y) / (p.y1 - p.y0);
    const lc = lx0 + fx * (lx1 - lx0), s = d.ylo + fy * (d.yhi - d.ylo);
    return { c0: Math.pow(10, lc + (lx0 - lc) * factor), c1: Math.pow(10, lc + (lx1 - lc) * factor),
             s0: s + (d.ylo - s) * factor, s1: s + (d.yhi - s) * factor };
  }

  // Whether a zoom shows at least the whole full view, so zooming out past it
  // is the full view again rather than empty margin around it.
  function covers(z, full) {
    return z.c0 <= full.xlo && z.c1 >= full.xhi && z.s0 <= full.ylo && z.s1 >= full.yhi;
  }

  // Everything one plot draws, in SVG coordinates, from one board and one
  // panel's settings. No DOM.
  function layout(board, st) {
    const shown = board.points.filter((p) => isShown(p, st));
    const out = { shown, points: [], labels: [], sweeps: [], frontier: [], xTicks: [], yTicks: [],
                  steps: "", wash: "", domain: null, plot: null };
    if (!shown.length) return out;
    const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;
    out.plot = { x0: PAD.l, y0: PAD.t, x1: W - PAD.r, y1: H - PAD.b };
    let xlo, xhi, ylo, yhi, yticks;
    if (st.zoom) {
      ({ c0: xlo, c1: xhi, s0: ylo, s1: yhi } = st.zoom);
      yticks = niceLinear(ylo, yhi).ticks.filter((v) => v >= ylo - 1e-9 && v <= yhi + 1e-9);
    } else {
      [xlo, xhi] = logDomain(shown.map((p) => p.cost));
      const lin = niceLinear(Math.min(...shown.map((p) => p.score)), Math.max(...shown.map((p) => p.score)));
      [ylo, yhi, yticks] = [lin.lo, lin.hi, lin.ticks];
    }
    out.domain = { xlo, xhi, ylo, yhi };
    const lxlo = Math.log10(xlo), lxhi = Math.log10(xhi);
    const X = (c) => PAD.l + (Math.log10(c) - lxlo) / (lxhi - lxlo) * iw;
    const Y = (s) => PAD.t + ih - (s - ylo) / (yhi - ylo) * ih;
    const ystep = yticks.length > 1 ? yticks[1] - yticks[0] : Math.abs(yhi - ylo) / 5;
    const yd = decimalsFor(+ystep.toPrecision(6));
    out.xTicks = logTicks(xlo, xhi).map((v) => ({ x: X(v), text: fmtTickMoney(v) }));
    out.yTicks = yticks.map((v) => ({ y: Y(v), text: v.toFixed(yd) + (board.unit === "%" ? "%" : "") }));

    const fr = frontier(frontierCandidates(shown, st.frontier));
    const onFrontier = new Set(fr);
    out.frontier = fr;
    if (fr.length) {
      const right = W - PAD.r, bottom = H - PAD.b;
      let steps = `M${X(fr[0].cost).toFixed(1)},${Y(fr[0].score).toFixed(1)}`;
      for (const p of fr.slice(1)) steps += ` H${X(p.cost).toFixed(1)} V${Y(p.score).toFixed(1)}`;
      steps += ` H${right}`;
      out.steps = steps;
      out.wash = `M${X(fr[0].cost).toFixed(1)},${bottom} V${Y(fr[0].score).toFixed(1)}`
        + steps.slice(steps.indexOf(" ")) + ` V${bottom} Z`;
    }

    if (st.lines) {
      const byModel = new Map();
      for (const p of shown) {
        if (!byModel.has(p.model)) byModel.set(p.model, []);
        byModel.get(p.model).push(p);
      }
      for (const [model, rows] of byModel) {
        if (rows.length < 2) continue;
        rows.sort((a, b) => effortIndex(a.effort) - effortIndex(b.effort));
        out.sweeps.push({ model, ours: rows[0].ours,
                          points: rows.map((p) => `${X(p.cost).toFixed(1)},${Y(p.score).toFixed(1)}`).join(" ") });
      }
    }

    const inFrame = shown.filter((p) => p.cost >= xlo && p.cost <= xhi && p.score >= ylo && p.score <= yhi);
    out.points = inFrame
      .map((p) => ({ p, x: X(p.cost), y: Y(p.score), frontier: onFrontier.has(p) }))
      .sort((a, b) => KIND_RANK[a.p.kind] - KIND_RANK[b.p.kind] || a.frontier - b.frontier);

    const placed = out.points.map((q) => [q.x - 7, q.y - 7, q.x + 7, q.y + 7]);
    const frame = [PAD.l + 2, PAD.t, W - PAD.r, H - PAD.b];
    const byScore = (a, b) => b.p.score - a.p.score;
    const queue = [];
    if (st.labels !== "none") {
      queue.push(...out.points.filter((q) => q.frontier).sort((a, b) => a.p.cost - b.p.cost));
      if (st.labels === "lanes" || st.labels === "all") {
        queue.push(...out.points.filter((q) => !q.frontier && q.p.lanes.length).sort(byScore));
      }
      if (st.labels === "all") {
        queue.push(...out.points.filter((q) => !q.frontier && !q.p.lanes.length).sort(byScore));
      }
    }
    for (const q of queue) {
      const text = labelText(q.p);
      const slot = place(text, q.x, q.y, placed, frame);
      if (!slot) continue;
      out.labels.push({ x: slot.x, y: slot.y, anchor: slot.anchor, text, box: slot.box,
                        model: q.p.model, frontier: q.frontier, off: q.p.kind === "lane_off",
                        ours: q.p.ours });
    }
    return out;
  }

  // --- drawing ----------------------------------------------------------------

  function svg(tag, attrs, parent) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
    if (parent) parent.appendChild(node);
    return node;
  }

  function el(tag, attrs, text, parent) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") node.className = v;
      else node.setAttribute(k, v);
    }
    if (text !== undefined && text !== null) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }

  function pointColour(p, mode) {
    if (p.kind === "comparator") return "var(--muted)";
    if (mode === "harness") return `var(--h-${harnessKeys(p)[0]}, var(--accent))`;
    if (mode === "tier") return p.tier ? `var(--tier-${p.tier}, var(--accent))` : "var(--muted)";
    return p.kind === "lane_off" ? "var(--off)" : "var(--accent)";
  }

  // Shape and fill carry the kind, a dashed outline weak provenance, and
  // colour whatever the panel colours by; never colour alone.
  function marker(g, p, cx, cy, mode) {
    const colour = pointColour(p, mode);
    const dash = p.weak ? { "stroke-dasharray": "2.5 2" } : {};
    if (p.kind === "comparator") {
      const r = 5.5;
      svg("path", Object.assign({ d: `M${cx},${cy - r} L${cx + r},${cy} L${cx},${cy + r} L${cx - r},${cy} Z`,
                                  fill: "var(--surface)", stroke: colour, "stroke-width": 1.6, class: "mk" }, dash), g);
    } else if (p.kind === "own_other" || p.weak) {
      svg("circle", Object.assign({ cx, cy, r: 4.8, fill: "var(--surface)", stroke: colour,
                                    "stroke-width": 2, class: "mk" }, dash), g);
    } else if (p.kind === "lane_off") {
      svg("circle", { cx, cy, r: 6.5, fill: "var(--off)", stroke: "var(--surface)", "stroke-width": 1.5, class: "mk" }, g);
      const k = 3;
      svg("path", { d: `M${cx - k},${cy - k} L${cx + k},${cy + k} M${cx - k},${cy + k} L${cx + k},${cy - k}`,
                    stroke: "var(--surface)", "stroke-width": 1.8, "stroke-linecap": "round" }, g);
    } else {
      svg("circle", { cx, cy, r: 6, fill: colour, stroke: "var(--surface)", "stroke-width": 1.5, class: "mk" }, g);
    }
  }

  function glyph(p, mode) {
    const s = svg("svg", { viewBox: "0 0 16 16", width: 16, height: 16, "aria-hidden": "true", class: "key" });
    marker(s, p, 8, 8, mode);
    return s;
  }

  function tipLines(p, board, decimals) {
    const lines = [[`${p.name} ${p.effort}`, "tip-head"],
                   [`${fmtScore(p.score, board.unit, decimals)} for ${fmtMoney(p.cost)}`, ""]];
    if (p.lanes.length) {
      for (const lane of p.lanes) lines.push([`${lane.name}, tier ${lane.tier ?? "—"}`, "mono"]);
    } else if (p.ours) {
      lines.push(["no lane runs this effort", "quiet"]);
    } else {
      lines.push(["not in your catalog", "quiet"]);
    }
    if (p.off) lines.push([`pre-screen proposes off: ${p.off}`, "off"]);
    else if (p.beatenBy) lines.push([`${p.beatenBy} beats it on most of this source`, "quiet"]);
    if (p.weak) lines.push([`weak provenance: ${p.provenance}`, "flag"]);
    if (p.published && p.published !== p.name) lines.push([`published as ${p.published}`, "quiet"]);
    return lines;
  }

  function makePanel(data, host, index, boardId, onRemove, everyPanel) {
    const boards = new Map(data.boards.map((b) => [b.id, b]));
    const st = { board: boardId, frontier: "lanes", colour: "kind", labels: "lanes", lines: true,
                 hiddenModels: new Set(), hiddenHarness: new Set(), hiddenEfforts: new Set(),
                 zoom: null, pinned: null, filter: "" };
    const root = el("section", { class: "plot", "aria-label": "Score against cost plot" }, null, host);
    let last = null;

    // head: which board, what its dollar is, and the sentence it says
    const head = el("div", { class: "plot-head" }, null, root);
    const pickLabel = el("label", { class: "pick" }, null, head);
    el("span", {}, "Benchmark", pickLabel);
    const select = el("select", {}, null, pickLabel);
    const bySource = new Map();
    for (const b of data.boards) {
      if (!bySource.has(b.source)) bySource.set(b.source, []);
      bySource.get(b.source).push(b);
    }
    for (const [source, list] of bySource) {
      const group = el("optgroup", { label: `${source}, ${list[0].basis}` }, null, select);
      for (const b of list) {
        el("option", { value: b.id }, b.benchmark + (b.composite ? " (composite)" : ""), group);
      }
    }
    const remove = el("button", { type: "button", class: "quiet-button" }, "Remove this plot", head);
    remove.addEventListener("click", () => onRemove(panel));
    const meta = el("p", { class: "meta" }, null, root);
    // what the chosen board measures, quoted from its source; redrawn with the board
    const about = el("div", { class: "about" }, null, root);
    const finding = el("p", { class: "finding" }, null, root);

    const body = el("div", { class: "plot-body" }, null, root);
    const wrap = el("div", { class: "chart" }, null, body);
    const chart = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" }, wrap);
    const tip = el("div", { class: "tip", role: "status" }, null, wrap);
    tip.hidden = true;
    // Always on screen, so the way back from a zoom never has to be found. It
    // sits under the plot, not over it, where it would cover the top-right labels.
    const hint = el("div", { class: "hint" }, null, wrap);
    const reset = el("button", { type: "button", class: "reset" }, "Reset zoom", hint);
    reset.addEventListener("click", () => { st.zoom = null; draw(); });
    el("span", {}, "Scroll over the plot to zoom about the pointer, or drag across it to zoom to a box. "
      + "Click a point to hold its model.", hint);
    const legend = el("div", { class: "plot-legend" }, null, root);
    const table = el("div", { class: "frontier-table" }, null, root);

    // the rail: every setting for this one plot
    const rail = el("form", { class: "rail", "aria-label": "Plot settings" }, null, body);
    rail.addEventListener("submit", (e) => e.preventDefault());
    function radios(title, key, options) {
      const fs = el("fieldset", {}, null, rail);
      el("legend", {}, title, fs);
      const row = el("div", { class: "radios" }, null, fs);
      for (const [value, text] of options) {
        const lab = el("label", {}, null, row);
        const input = el("input", { type: "radio", name: `${key}-${index}`, value }, null, lab);
        input.checked = st[key] === value;
        input.addEventListener("change", () => { st[key] = value; draw(); });
        lab.appendChild(document.createTextNode(text));
      }
      return fs;
    }
    radios("Frontier of", "frontier", [["lanes", "your lanes"], ["shown", "every point shown"], ["off", "none"]]);
    radios("Colour by", "colour", [["kind", "kind of point"], ["harness", "harness"], ["tier", "tier"]]);
    radios("Labels on", "labels", [["frontier", "the frontier"], ["lanes", "the frontier and your lanes"],
                                   ["all", "every point"], ["none", "nothing"]]);
    const linesLabel = el("label", { class: "check" }, null, rail);
    const linesBox = el("input", { type: "checkbox" }, null, linesLabel);
    linesBox.checked = st.lines;
    linesBox.addEventListener("change", () => { st.lines = linesBox.checked; draw(); });
    linesLabel.appendChild(document.createTextNode("Join each model's efforts"));

    function chips(title, values, hidden, words) {
      const fs = el("fieldset", {}, null, rail);
      el("legend", {}, title, fs);
      const row = el("div", { class: "chips" }, null, fs);
      const buttons = [];
      for (const v of values) {
        const b = el("button", { type: "button", class: "chip", "data-value": v }, words ? words(v) : v, row);
        b.addEventListener("click", () => {
          if (hidden.has(v)) hidden.delete(v); else hidden.add(v);
          draw();
        });
        buttons.push(b);
      }
      return () => buttons.forEach((b) => b.setAttribute("aria-pressed", String(!hidden.has(b.dataset.value))));
    }
    const syncHarness = chips("Harness", data.harnesses.concat([NO_HARNESS]), st.hiddenHarness,
                              (v) => (v === NO_HARNESS ? "not in catalog" : v));
    const syncEfforts = chips("Effort", data.efforts, st.hiddenEfforts);

    const models = el("fieldset", { class: "models" }, null, rail);
    el("legend", {}, "Models", models);
    const modelTools = el("div", { class: "model-tools" }, null, models);
    const filter = el("input", { type: "search", placeholder: "Filter by name", "aria-label": "Filter models by name" },
                      null, modelTools);
    filter.addEventListener("input", () => { st.filter = filter.value.toLowerCase(); fillModels(); });
    const bulk = el("div", { class: "bulk" }, null, models);
    for (const [text, how] of [["All", "all"], ["Your catalog", "ours"], ["None", "none"]]) {
      const b = el("button", { type: "button", class: "quiet-button" }, text, bulk);
      b.addEventListener("click", () => {
        for (const p of boards.get(st.board).points) {
          const hide = how === "none" || (how === "ours" && !p.ours);
          if (hide) st.hiddenModels.add(p.model); else st.hiddenModels.delete(p.model);
        }
        draw();
      });
    }
    const modelList = el("div", { class: "model-list" }, null, models);
    const copy = el("button", { type: "button", class: "quiet-button wide" }, "Use these settings on every plot", rail);
    copy.addEventListener("click", () => everyPanel((other) => other !== panel && other.adopt(st)));

    function modelsOfBoard(board) {
      const seen = new Map();
      for (const p of board.points) {
        const m = seen.get(p.model) || { model: p.model, name: p.name, ours: p.ours, harness: harnessKeys(p)[0], best: -Infinity };
        if (p.score !== null && p.score > m.best) m.best = p.score;
        seen.set(p.model, m);
      }
      return [...seen.values()].sort((a, b) => (b.ours - a.ours) || (b.best - a.best) || a.name.localeCompare(b.name));
    }

    function fillModels() {
      modelList.textContent = "";
      const all = modelsOfBoard(boards.get(st.board));
      let group = null;
      for (const m of all) {
        if (st.filter && !m.name.toLowerCase().includes(st.filter)) continue;
        const heading = m.ours ? "In your catalog" : "Not in your catalog";
        if (heading !== group) {
          el("p", { class: "group" }, heading, modelList);
          group = heading;
        }
        const lab = el("label", { class: "model-row", "data-m": m.model }, null, modelList);
        const box = el("input", { type: "checkbox" }, null, lab);
        box.checked = !st.hiddenModels.has(m.model);
        box.addEventListener("change", () => {
          if (box.checked) st.hiddenModels.delete(m.model); else st.hiddenModels.add(m.model);
          draw();
        });
        el("span", { class: m.ours ? "nm mono" : "nm" }, m.name, lab);
        if (m.ours) el("span", { class: "tag" }, m.harness, lab);
        lab.addEventListener("mouseenter", () => focus(m.model));
        lab.addEventListener("mouseleave", () => focus(null));
      }
    }

    function focus(model) {
      const hot = model || st.pinned;
      chart.classList.toggle("focusing", !!hot);
      for (const node of chart.querySelectorAll("[data-m]")) {
        node.classList.toggle("hot", node.getAttribute("data-m") === hot);
      }
      for (const row of table.querySelectorAll("tr[data-m]")) {
        row.classList.toggle("hot", row.getAttribute("data-m") === hot);
      }
    }

    function drawLegend(board) {
      legend.textContent = "";
      const items = [];
      const sample = (kind, extra) => Object.assign({ kind, weak: false, harness: [], tier: null, lanes: [] }, extra);
      if (st.colour === "kind") {
        items.push([sample("lane"), "a lane you carry"], [sample("lane_off"), "a lane the pre-screen proposes off"],
                   [sample("own_other"), "your model at an effort no lane runs"]);
      } else if (st.colour === "harness") {
        for (const h of data.harnesses) items.push([sample("lane", { harness: [h] }), h]);
      } else {
        for (const t of data.tiers) items.push([sample("lane", { tier: t }), `tier ${t}`]);
        items.push([sample("own_other", { tier: null }), "no lane at this effort"]);
      }
      items.push([sample("comparator"), "not in your catalog"], [sample("own_other", { weak: true }), "weak provenance"]);
      for (const [p, words] of items) {
        const item = el("span", { class: "item" }, null, legend);
        item.appendChild(glyph(p, st.colour));
        el("span", {}, words, item);
      }
      if (st.frontier !== "off") {
        const item = el("span", { class: "item" }, null, legend);
        const s = svg("svg", { viewBox: "0 0 22 16", width: 22, height: 16, "aria-hidden": "true", class: "key" }, item);
        svg("rect", { x: 0, y: 8, width: 22, height: 8, fill: "var(--frontier)", opacity: 0.12 }, s);
        svg("path", { d: "M1,12 H8 V5 H21", fill: "none", stroke: "var(--frontier)", "stroke-width": 2.2 }, s);
        el("span", {}, st.frontier === "lanes" ? "frontier of your lanes; the shade under it is beaten"
                                               : "frontier of every point shown; the shade under it is beaten", item);
      }
      if (board.composite) el("span", { class: "item note" }, "A composite index: shown, never counted by the pre-screen.", legend);
    }

    function drawTable(board, lay, decimals) {
      table.textContent = "";
      if (st.frontier === "off") return;
      const fr = lay.frontier;
      const title = st.frontier === "lanes" ? "Your lanes on the frontier" : "Every point shown on the frontier";
      el("h3", {}, title, table);
      el("p", { class: "quiet" }, fr.length
        ? "Cheapest first. Each row scores more than every row above it; the step column is what the extra money buys."
        : "No point shown is eligible. Turn on more models, harnesses or efforts.", table);
      if (!fr.length) return;
      const scroll = el("div", { class: "scroll" }, null, table);
      const t = el("table", { class: "frontier" }, null, scroll);
      const hr = el("tr", {}, null, el("thead", {}, null, t));
      for (const [h, num] of [["Cost", 1], ["Score", 1], ["Model", 0], ["Effort", 0], ["Lane", 0], ["Tier", 1], ["Step", 1]]) {
        el("th", num ? { class: "num" } : {}, h, hr);
      }
      const tb = el("tbody", {}, null, t);
      let prev = null;
      for (const p of fr) {
        const tr = el("tr", { "data-m": p.model, class: p.kind === "lane_off" ? "off-row" : "" }, null, tb);
        el("td", { class: "num" }, fmtMoney(p.cost), tr);
        el("td", { class: "num" }, fmtScore(p.score, board.unit, decimals), tr);
        el("td", { class: p.ours ? "mono" : "" }, p.name, tr);
        el("td", {}, p.effort, tr);
        const lane = el("td", {}, null, tr);
        if (p.lanes.length) {
          el("span", { class: "mono" }, p.lanes.map((l) => l.name).join(", "), lane);
          if (p.off) el("span", { class: "sub off" }, `proposed off: ${p.off}`, lane);
        } else {
          el("span", { class: "quiet" }, p.ours ? "no lane at this effort" : "not in catalog", lane);
        }
        el("td", { class: "num" }, p.lanes.length ? p.lanes.map((l) => l.tier ?? "—").join(", ") : "", tr);
        el("td", { class: "num quiet" }, prev
          ? `+${fmtScore(p.score - prev.score, board.unit, decimals)} for +${fmtMoney(p.cost - prev.cost)}` : "", tr);
        tr.addEventListener("mouseenter", () => focus(p.model));
        tr.addEventListener("mouseleave", () => focus(null));
        prev = p;
      }
    }

    function drawChart(board, lay, decimals) {
      chart.textContent = "";
      chart.setAttribute("aria-label", `Score against ${board.basis} on ${board.benchmark} from ${board.source}. `
        + `${lay.shown.length} points shown. ${board.finding} The frontier table follows.`);
      svg("rect", { x: 0, y: 0, width: W, height: H, fill: "var(--surface)" }, chart);
      if (!lay.plot) {
        const t = svg("text", { x: W / 2, y: H / 2, "text-anchor": "middle", class: "empty" }, chart);
        t.textContent = "Nothing shown. Turn on a model, a harness or an effort.";
        return;
      }
      const clipId = `plot-clip-${index}`;
      const clip = svg("clipPath", { id: clipId }, svg("defs", {}, chart));
      svg("rect", { x: PAD.l, y: PAD.t, width: W - PAD.l - PAD.r, height: H - PAD.t - PAD.b }, clip);
      for (const t of lay.yTicks) {
        svg("line", { x1: PAD.l, x2: W - PAD.r, y1: t.y, y2: t.y, class: "grid" }, chart);
        svg("text", { x: PAD.l - 8, y: t.y + 3.5, "text-anchor": "end", class: "tick" }, chart).textContent = t.text;
      }
      for (const t of lay.xTicks) {
        svg("line", { x1: t.x, x2: t.x, y1: PAD.t, y2: H - PAD.b, class: "grid" }, chart);
        svg("text", { x: t.x, y: H - PAD.b + 17, "text-anchor": "middle", class: "tick" }, chart).textContent = t.text;
      }
      svg("line", { x1: PAD.l, x2: W - PAD.r, y1: H - PAD.b, y2: H - PAD.b, class: "axis" }, chart);
      svg("text", { x: PAD.l + (W - PAD.l - PAD.r) / 2, y: H - 10, "text-anchor": "middle", class: "axis-title" }, chart)
        .textContent = `${board.basis}, dollars, log scale. Left is cheaper.`;
      svg("text", { x: 14, y: PAD.t + (H - PAD.t - PAD.b) / 2, "text-anchor": "middle", class: "axis-title",
                    transform: `rotate(-90 14 ${PAD.t + (H - PAD.t - PAD.b) / 2})` }, chart)
        .textContent = `score${board.unit === "%" ? ", percent" : ""}. Up is better.`;
      const clipped = svg("g", { "clip-path": `url(#${clipId})` }, chart);
      if (lay.wash) svg("path", { d: lay.wash, class: "wash" }, clipped);
      for (const s of lay.sweeps) {
        svg("polyline", { points: s.points, class: s.ours ? "sweep ours" : "sweep", "data-m": s.model }, clipped);
      }
      if (lay.steps) svg("path", { d: lay.steps, class: "steps" }, clipped);
      for (const q of lay.points) {
        const g = svg("g", { class: "pt", "data-m": q.p.model }, chart);
        if (q.frontier) svg("circle", { cx: q.x, cy: q.y, r: 10, class: "halo" }, g);
        svg("circle", { cx: q.x, cy: q.y, r: 11, fill: "transparent", class: "hit" }, g);
        marker(g, q.p, q.x, q.y, st.colour);
        g.addEventListener("pointerenter", () => showTip(q, board, decimals));
        g.addEventListener("pointerleave", () => { tip.hidden = true; focus(null); });
        g.addEventListener("pointerdown", (e) => { e.stopPropagation(); downOnPoint = q.p.model; });
      }
      for (const l of lay.labels) {
        const cls = "label" + (l.frontier ? " fr" : "") + (l.off ? " off" : "") + (l.ours ? "" : " cmp");
        svg("text", { x: l.x, y: l.y, "text-anchor": l.anchor, class: cls, "data-m": l.model }, chart).textContent = l.text;
      }
      band = svg("rect", { class: "band", x: 0, y: 0, width: 0, height: 0 }, chart);
      band.style.display = "none";
    }

    function drawAbout(board) {
      about.textContent = "";
      const a = board.about;
      if (!a) {
        el("p", { class: "cite" }, board.aboutMissing, about);
        return;
      }
      el("p", { class: "measures" }, a.measures, about);
      const dl = el("dl", {}, null, about);
      for (const [term, value] of [["Tasks", a.tasks], ["Score", a.score], ["Number shown", a.scale],
                                   ["Cost", a.cost], ["Speaks to", a.speaks_to]]) {
        if (!value) continue;
        el("dt", {}, term, dl);
        el("dd", {}, value, dl);
      }
      const cite = el("p", { class: "cite" }, "Quoted from ", about);
      el("a", { href: a.url }, a.url, cite);
      cite.appendChild(document.createTextNode(`, fetched ${a.fetched}. Number shown, cost and speaks to `
        + "are the wizard's reading, not the source's words."));
    }

    function showTip(q, board, decimals) {
      tip.textContent = "";
      for (const [text, cls] of tipLines(q.p, board, decimals)) el("div", cls ? { class: cls } : {}, text, tip);
      tip.hidden = false;
      const scale = chart.getBoundingClientRect().width / W;
      const left = q.x * scale, top = q.y * scale;
      const tw = tip.offsetWidth, wrapW = wrap.clientWidth;
      tip.style.left = `${left + 14 + tw > wrapW ? left - 14 - tw : left + 14}px`;
      tip.style.top = `${Math.max(4, top - 12)}px`;
      focus(q.p.model);
    }

    // drag to zoom, click to hold a model, double-click to reset
    let band = null, drag = null, downOnPoint = null;
    function toSvg(e) {
      const r = chart.getBoundingClientRect(), scale = r.width / W;
      return [(e.clientX - r.left) / scale, (e.clientY - r.top) / scale];
    }
    chart.addEventListener("pointerdown", (e) => {
      if (!last || !last.plot) return;
      const [x, y] = toSvg(e);
      drag = { x, y, x1: x, y1: y };
      try {
        chart.setPointerCapture(e.pointerId);
      } catch (_err) {
        // a pointer the browser no longer tracks; the drag still works inside the plot
      }
    });
    chart.addEventListener("pointermove", (e) => {
      if (!drag) return;
      [drag.x1, drag.y1] = toSvg(e);
      if (Math.abs(drag.x1 - drag.x) > 4 || Math.abs(drag.y1 - drag.y) > 4) {
        band.style.display = "";
        band.setAttribute("x", Math.min(drag.x, drag.x1));
        band.setAttribute("y", Math.min(drag.y, drag.y1));
        band.setAttribute("width", Math.abs(drag.x1 - drag.x));
        band.setAttribute("height", Math.abs(drag.y1 - drag.y));
      }
    });
    chart.addEventListener("pointerup", () => {
      if (!drag) return;
      const d = drag, model = downOnPoint;
      drag = null;
      downOnPoint = null;
      band.style.display = "none";
      if (Math.abs(d.x1 - d.x) > 10 && Math.abs(d.y1 - d.y) > 10) {
        const { xlo, xhi, ylo, yhi } = last.domain, p = last.plot;
        const cost = (x) => Math.pow(10, Math.log10(xlo) + (Math.min(Math.max(x, p.x0), p.x1) - p.x0) / (p.x1 - p.x0) * (Math.log10(xhi) - Math.log10(xlo)));
        const score = (y) => ylo + (p.y1 - Math.min(Math.max(y, p.y0), p.y1)) / (p.y1 - p.y0) * (yhi - ylo);
        st.zoom = { c0: cost(Math.min(d.x, d.x1)), c1: cost(Math.max(d.x, d.x1)),
                    s0: score(Math.max(d.y, d.y1)), s1: score(Math.min(d.y, d.y1)) };
        draw();
        return;
      }
      st.pinned = model && model !== st.pinned ? model : null;
      focus(null);
    });
    chart.addEventListener("dblclick", () => { st.zoom = null; draw(); });
    // The wheel zooms only over the plotting area; over the axes and margins it
    // scrolls the page as usual, so a reader scrolling past a plot is not caught.
    chart.addEventListener("wheel", (e) => {
      if (!last || !last.plot || drag) return;
      const [x, y] = toSvg(e), p = last.plot;
      if (x < p.x0 || x > p.x1 || y < p.y0 || y > p.y1) return;
      e.preventDefault();
      const step = e.deltaY * (e.deltaMode === 1 ? 0.05 : e.deltaMode === 2 ? 1 : 0.0015);
      const next = zoomAbout(last.domain, p, x, y, Math.exp(Math.max(-0.5, Math.min(0.5, step))));
      const full = layout(boards.get(st.board), Object.assign({}, st, { zoom: null })).domain;
      st.zoom = full && covers(next, full) ? null : next;
      draw();
    }, { passive: false });

    function draw() {
      const board = boards.get(st.board);
      select.value = st.board;
      meta.textContent = "";
      if (board.url) el("a", { href: board.url }, board.source, meta);
      else meta.appendChild(document.createTextNode(board.source));
      meta.appendChild(document.createTextNode(`, ${board.basis}, observed ${board.when}. `
        + `${board.rows} rows, ${board.models} models.`
        + (board.unplotted.length ? ` Not drawn, no usable score or cost: ${board.unplotted.join(", ")}.` : "")));
      drawAbout(board);
      finding.textContent = board.finding;
      const decimals = scoreDecimals(board);
      last = layout(board, st);
      drawChart(board, last, decimals);
      drawLegend(board);
      drawTable(board, last, decimals);
      fillModels();
      syncHarness();
      syncEfforts();
      reset.setAttribute("aria-disabled", String(!st.zoom));
      tip.hidden = true;
      remove.hidden = host.querySelectorAll("section.plot").length < 2;
      focus(null);
    }

    select.addEventListener("change", () => {
      st.board = select.value;
      st.zoom = null;
      st.pinned = null;
      draw();
    });

    const panel = {
      root,
      board: () => st.board,
      draw,
      adopt(other) {
        for (const key of ["frontier", "colour", "labels", "lines"]) st[key] = other[key];
        for (const key of ["hiddenModels", "hiddenHarness", "hiddenEfforts"]) {
          st[key].clear();
          other[key].forEach((v) => st[key].add(v));
        }
        for (const input of rail.querySelectorAll("input[type=radio]")) {
          input.checked = st[input.name.replace(/-\d+$/, "")] === input.value;
        }
        linesBox.checked = st.lines;
        draw();
      },
    };
    return panel;
  }

  function boot() {
    const source = document.getElementById("bench-data");
    const host = document.getElementById("plots");
    if (!source || !host) return;
    const data = JSON.parse(source.textContent);
    if (!data.boards.length) return;
    const panels = [];
    let count = 0;
    const every = (fn) => panels.forEach(fn);
    const remove = (panel) => {
      if (panels.length < 2) return;
      panels.splice(panels.indexOf(panel), 1);
      panel.root.remove();
      every((p) => p.draw());
    };
    const add = (boardId) => {
      const panel = makePanel(data, host, count++, boardId, remove, every);
      panels.push(panel);
      every((p) => p.draw());
      return panel;
    };
    for (const id of data.defaults) add(id);
    const more = document.getElementById("add-plot");
    if (more) {
      more.hidden = false;
      more.addEventListener("click", () => {
        const used = new Set(panels.map((p) => p.board()));
        const next = data.boards.find((b) => !used.has(b.id)) || data.boards[0];
        const still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        add(next.id).root.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
      });
    }
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { layout, frontier, logTicks, logDomain, niceLinear, fmtMoney, fmtTickMoney, place,
                       zoomAbout, covers, W, H, PAD };
  } else if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
    else boot();
  }
})();
