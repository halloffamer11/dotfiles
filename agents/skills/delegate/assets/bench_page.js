// Inlined into the benchmark page by scripts/bench_page.py; never loaded on
// its own. It draws one score-against-cost plot per panel from the JSON in
// #bench-data, and beside the plots a panel of the tiers drawn on this page.
// Every decision in that JSON (which lane a point is, what the pre-screen
// proposes off, which effort beats which, the order lanes are listed in) was
// made in Python; this file only filters what is shown, finds the frontier of
// it, lays it out, and holds the page's own tier choices, which live in this
// browser's localStorage under the catalog's key and are written nowhere else
// (ticket 26). The pure functions have no DOM, so tests/test_bench_page.py
// runs them under node. Text from a benchmark page is set with textContent
// only, never as markup.
(function () {
  "use strict";

  const EFFORT_ORDER = ["none", "low", "medium", "high", "xhigh", "max", "ultra"];
  const W = 880, H = 500;
  const PAD = { l: 58, r: 18, t: 14, b: 50 };
  const CHAR_PX = 6.6, LABEL_H = 12;
  const NO_HARNESS = "none";
  const SVG_NS = "http://www.w3.org/2000/svg";
  const TIERS = [4, 3, 2, 1];

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

  // A drag of (dx, dy) SVG pixels while zoomed: the content follows the
  // pointer, so the domain moves the other way, in log space on the cost axis.
  function panBy(d, p, dx, dy) {
    const lx0 = Math.log10(d.xlo), lx1 = Math.log10(d.xhi);
    const sx = dx / (p.x1 - p.x0) * (lx1 - lx0), sy = dy / (p.y1 - p.y0) * (d.yhi - d.ylo);
    return { c0: Math.pow(10, lx0 - sx), c1: Math.pow(10, lx1 - sx), s0: d.ylo + sy, s1: d.yhi + sy };
  }

  // Whether a zoom shows at least the whole full view, so zooming out past it
  // is the full view again rather than empty margin around it.
  function covers(z, full) {
    return z.c0 <= full.xlo && z.c1 >= full.xhi && z.s0 <= full.ylo && z.s1 >= full.yhi;
  }

  // --- the tiers drawn on this page (pure) ------------------------------------

  // The tier a cost's band proposes: one more than the number of tier lines
  // at or below it. A guide, never a rule: nothing reads it but the tooltip
  // and the one button that applies it.
  function bandTier(cost, lines) {
    if (!lines || lines.length !== 3) return null;
    let tier = 1;
    for (const c of lines) if (cost >= c) tier++;
    return tier;
  }

  // Three lines at the log quartiles of the lane costs shown, to be dragged
  // from there; rounded to two figures so a line sits on a number a person
  // could have chosen.
  function defaultLines(costs) {
    const positive = costs.filter((c) => c > 0);
    if (!positive.length) return null;
    let lo = Math.min(...positive), hi = Math.max(...positive);
    if (hi / lo < 1.5) {
      const mid = Math.sqrt(lo * hi);
      lo = mid / 2;
      hi = mid * 2;
    }
    const llo = Math.log10(lo), lhi = Math.log10(hi);
    const exact = [0.25, 0.5, 0.75].map((f) => Math.pow(10, llo + f * (lhi - llo)));
    const rounded = exact.map((v) => +v.toPrecision(2));
    return rounded[0] < rounded[1] && rounded[1] < rounded[2] ? rounded : exact;
  }

  // The tier this page gives a point: its lanes' tier when they have one.
  function pointTier(p, tiers) {
    for (const lane of p.lanes || []) {
      const t = (tiers || {})[lane.name];
      if (t) return t;
    }
    return null;
  }

  // `ordered` regrouped by model: each group sits where its first lane sat,
  // and lists its efforts from most to least. The same rule as
  // setup_tui.group_lanes, applied here to an order only the page knows.
  function groupLanes(ordered) {
    const groups = new Map();
    for (const lane of ordered) {
      if (!groups.has(lane.group)) groups.set(lane.group, []);
      groups.get(lane.group).push(lane);
    }
    const out = [];
    for (const members of groups.values()) {
      out.push(...members.slice().sort((a, b) => effortIndex(b.effort) - effortIndex(a.effort)));
    }
    return out;
  }

  // The review page's order, given these tiers: best tier first, then the
  // benchmark order, then each model's group where its first lane sits.
  function reviewOrder(lanes, tiers) {
    const ordered = lanes.slice().sort((a, b) => ((tiers[b.name] || 0) - (tiers[a.name] || 0)) || (a.rank - b.rank));
    return groupLanes(ordered);
  }

  function tierLinesText(lanes, tiers) {
    return reviewOrder(lanes.filter((l) => tiers[l.name]), tiers).map((l) => `${l.name} ${tiers[l.name]}`).join("\n");
  }

  // The zoom that shows one tier: its band between the tier lines when there
  // are lines, else the points this page gives that tier; the score range
  // fits those points. Null when there is nothing to show.
  function focusDomain(board, st, tier) {
    const shown = board.points.filter((p) => isShown(p, st));
    const mine = shown.filter((p) => p.lanes.length && pointTier(p, st.tiers) === tier);
    const lines = st.tierLines;
    let costs, pool;
    if (lines && lines.length === 3) {
      const lo = tier > 1 ? lines[tier - 2] : null, hi = tier < 4 ? lines[tier - 1] : null;
      const inBand = shown.filter((p) => (lo === null || p.cost >= lo) && (hi === null || p.cost < hi));
      pool = mine.length ? mine : inBand;
      if (!pool.length) return null;
      const all = shown.map((p) => p.cost);
      costs = [lo === null ? Math.min(...all) : lo, hi === null ? Math.max(...all) : hi];
    } else {
      pool = mine;
      if (!pool.length) return null;
      costs = pool.map((p) => p.cost);
    }
    const [xlo, xhi] = logDomain(costs);
    const lin = niceLinear(Math.min(...pool.map((p) => p.score)), Math.max(...pool.map((p) => p.score)));
    return { c0: xlo, c1: xhi, s0: lin.lo, s1: lin.hi };
  }

  // Everything one plot draws, in SVG coordinates, from one board and one
  // panel's settings. `st.tiers`, `st.tierLines` and `st.focusTier` are the
  // page's, passed in so this stays pure. No DOM.
  function layout(board, st) {
    const shown = board.points.filter((p) => isShown(p, st));
    const out = { shown, points: [], labels: [], sweeps: [], frontier: [], xTicks: [], yTicks: [],
                  lines: [], bands: [], steps: "", wash: "", domain: null, plot: null };
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

    // the tier lines, and the name of each band they cut the axis into
    const tierLines = st.tierLines && st.tierLines.length === 3 ? st.tierLines : null;
    if (tierLines) {
      out.lines = tierLines.map((cost, index) => ({ cost, index, x: X(cost), inside: cost >= xlo && cost <= xhi }));
      const edges = [xlo, ...tierLines, xhi].map((c) => Math.min(Math.max(c, xlo), xhi));
      out.bands = TIERS.slice().reverse().map((tier, i) => ({ tier, x0: X(edges[i]), x1: X(edges[i + 1]) }))
        .filter((b) => b.x1 - b.x0 > 34);
    }

    const tiers = st.tiers || {};
    const inFrame = shown.filter((p) => p.cost >= xlo && p.cost <= xhi && p.score >= ylo && p.score <= yhi);
    out.points = inFrame
      .map((p) => {
        const tier = pointTier(p, tiers);
        return { p, x: X(p.cost), y: Y(p.score), frontier: onFrontier.has(p), tier,
                 band: bandTier(p.cost, tierLines), dim: !!st.focusTier && tier !== st.focusTier };
      })
      .sort((a, b) => KIND_RANK[a.p.kind] - KIND_RANK[b.p.kind] || a.frontier - b.frontier);

    const placed = out.points.map((q) => [q.x - 7, q.y - 7, q.x + 7, q.y + 7]);
    const frame = [PAD.l + 2, PAD.t + (out.bands.length ? 14 : 0), W - PAD.r, H - PAD.b];
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
                        ours: q.p.ours, dim: q.dim });
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

  function harnessColour(harness) {
    return `var(--h-${harness}, var(--accent))`;
  }

  function pointColour(p) {
    if (p.kind === "comparator") return "var(--muted)";
    return harnessColour(harnessKeys(p)[0]);
  }

  // Shape and fill carry the kind, a dashed outline weak provenance, colour
  // the harness, and in the tier view the digit inside a lane's dot is the
  // tier this page gives it; a hollow dot there has none yet. Never colour
  // alone.
  function marker(g, p, cx, cy, view) {
    const colour = pointColour(p);
    const dash = p.weak ? { "stroke-dasharray": "2.5 2" } : {};
    const tierView = view && view.tierView;
    if (p.kind === "comparator") {
      const r = 5.5;
      svg("path", Object.assign({ d: `M${cx},${cy - r} L${cx + r},${cy} L${cx},${cy + r} L${cx - r},${cy} Z`,
                                  fill: "var(--surface)", stroke: colour, "stroke-width": 1.6, class: "mk" }, dash), g);
    } else if (p.kind === "own_other" || p.weak) {
      svg("circle", Object.assign({ cx, cy, r: 4.8, fill: "var(--surface)", stroke: colour,
                                    "stroke-width": 2, class: "mk" }, dash), g);
    } else if (tierView) {
      const tier = view.tier;
      if (tier) {
        svg("circle", { cx, cy, r: 8.5, fill: colour, stroke: "var(--surface)", "stroke-width": 1.5, class: "mk" }, g);
        svg("text", { x: cx, y: cy + 3.8, class: "digit" }, g).textContent = String(tier);
      } else {
        svg("circle", { cx, cy, r: 7.5, fill: "var(--surface)", stroke: colour, "stroke-width": 2, class: "mk" }, g);
      }
      if (p.kind === "lane_off") svg("circle", { cx, cy, r: 11, fill: "none", stroke: "var(--off)", "stroke-width": 1.5 }, g);
    } else if (p.kind === "lane_off") {
      svg("circle", { cx, cy, r: 6.5, fill: colour, stroke: "var(--surface)", "stroke-width": 1.5, class: "mk" }, g);
      const k = 3;
      svg("path", { d: `M${cx - k},${cy - k} L${cx + k},${cy + k} M${cx - k},${cy + k} L${cx + k},${cy - k}`,
                    stroke: "var(--surface)", "stroke-width": 1.8, "stroke-linecap": "round" }, g);
    } else {
      svg("circle", { cx, cy, r: 6, fill: colour, stroke: "var(--surface)", "stroke-width": 1.5, class: "mk" }, g);
    }
  }

  function glyph(p, view) {
    const s = svg("svg", { viewBox: "0 0 24 24", width: 22, height: 22, "aria-hidden": "true", class: "key" });
    marker(s, p, 12, 12, view);
    return s;
  }

  function tipLines(p, board, decimals, page, tierLines) {
    const lines = [[`${p.name} ${p.effort}`, "tip-head"],
                   [`${fmtScore(p.score, board.unit, decimals)} for ${fmtMoney(p.cost)}`, ""]];
    if (p.lanes.length) {
      for (const lane of p.lanes) {
        const here = page.tiers[lane.name];
        lines.push([`${lane.name}: ${here ? `tier ${here} here` : "no tier here yet"}, `
                    + `${lane.tier ?? "—"} in the catalog`, "mono"]);
      }
      const band = bandTier(p.cost, tierLines);
      if (band) lines.push([`the band proposes tier ${band}`, "quiet"]);
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

  // Four boxes, one per tier, exactly one pressed when the lane has a tier:
  // the review page's marker, on the page.
  function tierBoxes(parent, names, page, size) {
    const boxes = el("span", { class: "boxes", role: "group", "aria-label": "Tier" }, null, parent);
    const current = page.tiers[names[0]] || null;
    for (const t of TIERS) {
      const b = el("button", { type: "button", class: "box", "aria-pressed": String(current === t),
                               "aria-label": `tier ${t}` }, String(t), boxes);
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        page.setTier(names, current === t ? null : t);
      });
    }
    return boxes;
  }

  function makePanel(data, host, index, boardId, onRemove, everyPanel, page) {
    const boards = new Map(data.boards.map((b) => [b.id, b]));
    const st = { board: boardId, frontier: "lanes", labels: "lanes", lines: true,
                 hiddenModels: new Set(), hiddenHarness: new Set(), hiddenEfforts: new Set(),
                 zoom: null, pinned: null, filter: "" };
    const root = el("section", { class: "plot", "aria-label": "Score against cost plot" }, null, host);
    let last = null, pickerOpen = false;

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
    const picker = el("div", { class: "picker" }, null, wrap);
    picker.hidden = true;
    // Always on screen, so the way back from a zoom never has to be found. It
    // sits under the plot, not over it, where it would cover the top-right labels.
    const hint = el("div", { class: "hint" }, null, wrap);
    const reset = el("button", { type: "button", class: "reset" }, "Reset zoom", hint);
    reset.addEventListener("click", () => { st.zoom = null; page.clearFocus(); draw(); });
    el("span", {}, "Scroll over the plot to zoom about the pointer, or drag across it to zoom to a box; "
      + "once zoomed, a drag pans. Click a dot, then press 1 to 4 for its tier. Drag a tier line to move it.", hint);
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
    radios("Labels on", "labels", [["frontier", "the frontier"], ["lanes", "the frontier and your lanes"],
                                   ["all", "every point"], ["none", "nothing"]]);
    const linesLabel = el("label", { class: "check" }, null, rail);
    const linesBox = el("input", { type: "checkbox" }, null, linesLabel);
    linesBox.checked = st.lines;
    linesBox.addEventListener("change", () => { st.lines = linesBox.checked; draw(); });
    linesLabel.appendChild(document.createTextNode("Join each model's efforts"));

    // the tier lines belong to the source, since its dollar is the axis: every
    // plot of that source draws the same three, and a drag on any moves all
    const tiersFs = el("fieldset", {}, null, rail);
    el("legend", {}, "Tier lines", tiersFs);
    const tierLinesLabel = el("label", { class: "check" }, null, tiersFs);
    const tierLinesBox = el("input", { type: "checkbox" }, null, tierLinesLabel);
    tierLinesLabel.appendChild(document.createTextNode("Draw the three lines on this source's cost axis"));
    tierLinesBox.addEventListener("change", () => {
      const board = boards.get(st.board);
      if (tierLinesBox.checked) {
        if (!page.lines[board.source]) {
          const costs = board.points.filter((p) => isShown(p, st) && p.lanes.length).map((p) => p.cost);
          const lines = defaultLines(costs.length ? costs : board.points.filter((p) => isShown(p, st)).map((p) => p.cost));
          if (lines) page.lines[board.source] = lines;
        }
      } else {
        delete page.lines[board.source];
      }
      page.save();
      page.redraw();
    });
    const bandsButton = el("button", { type: "button", class: "quiet-button bands-button" },
                           "Give every lane on this plot its band's tier", tiersFs);
    bandsButton.addEventListener("click", () => {
      const board = boards.get(st.board);
      const lines = page.lines[board.source];
      if (!lines) return;
      const changes = [];
      for (const p of board.points) {
        if (!isShown(p, st) || !p.lanes.length) continue;
        changes.push([p.lanes.map((l) => l.name), bandTier(p.cost, lines)]);
      }
      page.setTiers(changes);
    });

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
      const view = { tierView: page.tierView, tier: page.tierView ? 2 : null };
      const one = data.harnesses.length ? [data.harnesses[0]] : [];
      for (const h of data.harnesses) items.push([sample("lane", { harness: [h] }), `a ${h} lane`, view]);
      if (page.tierView) {
        items.push([sample("lane", { harness: one }), "the digit is the tier drawn here", view],
                   [sample("lane", { harness: one }), "hollow: no tier here yet", { tierView: true, tier: null }]);
      }
      items.push([sample("lane_off", { harness: one }), "a lane the pre-screen proposes off", view],
                 [sample("own_other", { harness: one }), "your model at an effort no lane runs", view],
                 [sample("comparator"), "not in your catalog", view],
                 [sample("own_other", { weak: true, harness: one }), "weak provenance", view]);
      for (const [p, words, v] of items) {
        const item = el("span", { class: "item" }, null, legend);
        item.appendChild(glyph(p, v));
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
      if (page.lines[board.source]) {
        el("span", { class: "item note" }, "The dashed lines are guides between tiers; a dot takes any tier you give it.", legend);
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
      for (const [h, num] of [["Cost", 1], ["Score", 1], ["Model", 0], ["Effort", 0], ["Lane", 0], ["Tier here", 1], ["Step", 1]]) {
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
        el("td", { class: "num" }, p.lanes.length ? p.lanes.map((l) => page.tiers[l.name] ?? "—").join(", ") : "", tr);
        el("td", { class: "num quiet" }, prev
          ? `+${fmtScore(p.score - prev.score, board.unit, decimals)} for +${fmtMoney(p.cost - prev.cost)}` : "", tr);
        tr.addEventListener("mouseenter", () => focus(p.model));
        tr.addEventListener("mouseleave", () => focus(null));
        prev = p;
      }
    }

    function selectedKey() {
      return page.selected ? page.selected.key : null;
    }

    function pointKey(p) {
      return `${p.model} ${p.effort}`;
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
      for (const b of lay.bands) {
        svg("text", { x: (b.x0 + b.x1) / 2, y: PAD.t + 11, "text-anchor": "middle", class: "band-name" }, chart)
          .textContent = `tier ${b.tier}`;
      }
      for (const l of lay.lines) {
        if (!l.inside) continue;
        const g = svg("g", { class: "tier-handle", "data-line": l.index }, chart);
        svg("line", { x1: l.x, x2: l.x, y1: PAD.t, y2: H - PAD.b, class: "tier-grip" }, g);
        svg("line", { x1: l.x, x2: l.x, y1: PAD.t, y2: H - PAD.b, class: "tier-line" }, g);
        g.addEventListener("pointerdown", (e) => {
          if (e.button !== 0) return;
          e.stopPropagation();
          e.preventDefault();
          lineDrag = { index: l.index, source: board.source };
          g.querySelector(".tier-line").classList.add("held");
          try { chart.setPointerCapture(e.pointerId); } catch (_err) { /* still drags inside the plot */ }
        });
      }
      const selected = selectedKey();
      for (const q of lay.points) {
        const g = svg("g", { class: "pt" + (q.dim ? " dim" : ""), "data-m": q.p.model }, chart);
        if (q.frontier) svg("circle", { cx: q.x, cy: q.y, r: 10, class: "halo" }, g);
        if (selected && pointKey(q.p) === selected) svg("circle", { cx: q.x, cy: q.y, r: 14, class: "sel" }, g);
        svg("circle", { cx: q.x, cy: q.y, r: 11, fill: "transparent", class: "hit" }, g);
        marker(g, q.p, q.x, q.y, { tierView: page.tierView, tier: q.tier });
        g.addEventListener("pointerenter", () => showTip(q, board, decimals));
        g.addEventListener("pointerleave", () => { tip.hidden = true; focus(null); });
        g.addEventListener("pointerdown", (e) => { if (e.button === 0) downOnPoint = q; });
      }
      for (const l of lay.labels) {
        const cls = "label" + (l.frontier ? " fr" : "") + (l.off ? " off" : "") + (l.ours ? "" : " cmp") + (l.dim ? " dim" : "");
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

    function placeNear(box, q) {
      const scale = chart.getBoundingClientRect().width / W;
      const left = q.x * scale, top = q.y * scale;
      const bw = box.offsetWidth, wrapW = wrap.clientWidth;
      box.style.left = `${left + 14 + bw > wrapW ? left - 14 - bw : left + 14}px`;
      box.style.top = `${Math.max(4, top - 12)}px`;
    }

    function showTip(q, board, decimals) {
      if (pickerOpen && selectedKey() === pointKey(q.p)) return;
      tip.textContent = "";
      for (const [text, cls] of tipLines(q.p, board, decimals, page, page.lines[board.source])) {
        el("div", cls ? { class: cls } : {}, text, tip);
      }
      tip.hidden = false;
      placeNear(tip, q);
      focus(q.p.model);
    }

    // The picker beside the selected dot: the lane's name, four boxes and
    // what the band proposes. Digits do the same from the keyboard.
    function drawPicker(board) {
      picker.textContent = "";
      const key = selectedKey();
      const q = key && last && last.points.find((c) => pointKey(c.p) === key);
      if (!pickerOpen || !q || !q.p.lanes.length) {
        picker.hidden = true;
        return;
      }
      el("div", { class: "who" }, q.p.lanes.map((l) => l.name).join(", "), picker);
      const row = el("div", { class: "row" }, null, picker);
      tierBoxes(row, q.p.lanes.map((l) => l.name), page);
      const none = el("button", { type: "button", class: "quiet-button" }, "none", row);
      none.addEventListener("click", (e) => { e.stopPropagation(); page.setTier(q.p.lanes.map((l) => l.name), null); });
      const band = bandTier(q.p.cost, page.lines[board.source]);
      el("p", { class: "quiet" }, band ? `Press 1 to 4. The band proposes tier ${band}.` : "Press 1 to 4.", picker);
      picker.hidden = false;
      placeNear(picker, q);
      tip.hidden = true;
    }

    // drag to zoom or pan, click to select a dot, double-click to reset
    let band = null, drag = null, downOnPoint = null, lineDrag = null, frame = null;
    function toSvg(e) {
      const r = chart.getBoundingClientRect(), scale = r.width / W;
      return [(e.clientX - r.left) / scale, (e.clientY - r.top) / scale];
    }
    function costAt(x) {
      const { xlo, xhi } = last.domain, p = last.plot;
      const f = (Math.min(Math.max(x, p.x0), p.x1) - p.x0) / (p.x1 - p.x0);
      return Math.pow(10, Math.log10(xlo) + f * (Math.log10(xhi) - Math.log10(xlo)));
    }
    function scoreAt(y) {
      const { ylo, yhi } = last.domain, p = last.plot;
      return ylo + (p.y1 - Math.min(Math.max(y, p.y0), p.y1)) / (p.y1 - p.y0) * (yhi - ylo);
    }
    function soon(fn) {
      if (frame) return;
      frame = requestAnimationFrame(() => { frame = null; fn(); });
    }
    chart.addEventListener("pointerdown", (e) => {
      if (!last || !last.plot || lineDrag) return;
      if (e.button !== 0 && e.button !== 1) return;
      const [x, y] = toSvg(e);
      // a left drag pans once zoomed and boxes a zoom before; the middle
      // button pans either way
      const pan = e.button === 1 || !!st.zoom;
      drag = { x, y, x1: x, y1: y, pan, moved: false, domain: last.domain, plot: last.plot, point: downOnPoint };
      downOnPoint = null;
      if (pan) e.preventDefault();
      try {
        chart.setPointerCapture(e.pointerId);
      } catch (_err) {
        // a pointer the browser no longer tracks; the drag still works inside the plot
      }
    });
    chart.addEventListener("mousedown", (e) => { if (e.button === 1) e.preventDefault(); });
    chart.addEventListener("auxclick", (e) => { if (e.button === 1) e.preventDefault(); });
    chart.addEventListener("pointermove", (e) => {
      if (lineDrag) {
        if (!last || !last.plot) return;
        const [x] = toSvg(e);
        const lines = page.lines[lineDrag.source];
        if (!lines) return;
        let cost = costAt(x);
        const i = lineDrag.index;
        if (i > 0) cost = Math.max(cost, lines[i - 1] * 1.02);
        if (i < 2) cost = Math.min(cost, lines[i + 1] / 1.02);
        lines[i] = cost;
        soon(() => page.redraw(lineDrag ? lineDrag.source : null));
        return;
      }
      if (!drag) return;
      const [x, y] = toSvg(e);
      const dx = x - drag.x1, dy = y - drag.y1;
      [drag.x1, drag.y1] = [x, y];
      if (!drag.moved && (Math.abs(x - drag.x) > 4 || Math.abs(y - drag.y) > 4)) {
        drag.moved = true;
        if (drag.pan) chart.classList.add("panning");
      }
      if (!drag.moved) return;
      if (drag.pan) {
        // from the domain pending, not the one drawn: two moves can land
        // between frames, and the second must not undo the first
        const from = st.zoom ? { xlo: st.zoom.c0, xhi: st.zoom.c1, ylo: st.zoom.s0, yhi: st.zoom.s1 } : last.domain;
        st.zoom = panBy(from, last.plot, dx, dy);
        tip.hidden = true;
        soon(draw);
      } else {
        band.style.display = "";
        band.setAttribute("x", Math.min(drag.x, drag.x1));
        band.setAttribute("y", Math.min(drag.y, drag.y1));
        band.setAttribute("width", Math.abs(drag.x1 - drag.x));
        band.setAttribute("height", Math.abs(drag.y1 - drag.y));
      }
    });
    function endDrag() {
      if (lineDrag) {
        lineDrag = null;
        page.save();
        page.redraw();
        return;
      }
      if (!drag) return;
      const d = drag;
      drag = null;
      chart.classList.remove("panning");
      if (band) band.style.display = "none";
      if (d.moved && !d.pan && Math.abs(d.x1 - d.x) > 10 && Math.abs(d.y1 - d.y) > 10) {
        st.zoom = { c0: costAt(Math.min(d.x, d.x1)), c1: costAt(Math.max(d.x, d.x1)),
                    s0: scoreAt(Math.max(d.y, d.y1)), s1: scoreAt(Math.min(d.y, d.y1)) };
        draw();
        return;
      }
      if (d.moved) {
        if (d.pan) {
          const full = layout(boards.get(st.board), pageState({ zoom: null })).domain;
          if (full && covers(st.zoom, full)) st.zoom = null;
          draw();
        }
        return;
      }
      // a press that did not move is a click: on a dot it selects the dot
      if (d.point && d.point.p.lanes.length) {
        const key = pointKey(d.point.p);
        if (selectedKey() === key && pickerOpen) {
          page.select(null);
        } else {
          pickerOpen = true;
          page.select({ key, lanes: d.point.p.lanes.map((l) => l.name) }, panel);
        }
      } else if (d.point) {
        st.pinned = d.point.p.model !== st.pinned ? d.point.p.model : null;
        focus(null);
      } else {
        page.select(null);
      }
    }
    chart.addEventListener("pointerup", endDrag);
    chart.addEventListener("pointercancel", endDrag);
    chart.addEventListener("dblclick", () => { st.zoom = null; page.clearFocus(); draw(); });
    // The wheel zooms only over the plotting area; over the axes and margins it
    // scrolls the page as usual, so a reader scrolling past a plot is not caught.
    chart.addEventListener("wheel", (e) => {
      if (!last || !last.plot || drag) return;
      const [x, y] = toSvg(e), p = last.plot;
      if (x < p.x0 || x > p.x1 || y < p.y0 || y > p.y1) return;
      e.preventDefault();
      const step = e.deltaY * (e.deltaMode === 1 ? 0.05 : e.deltaMode === 2 ? 1 : 0.0015);
      const next = zoomAbout(last.domain, p, x, y, Math.exp(Math.max(-0.5, Math.min(0.5, step))));
      const full = layout(boards.get(st.board), pageState({ zoom: null })).domain;
      st.zoom = full && covers(next, full) ? null : next;
      draw();
    }, { passive: false });

    // this panel's settings with the page's tiers, lines and focus beside them
    function pageState(extra) {
      const board = boards.get(st.board);
      return Object.assign({}, st, { tiers: page.tiers, tierLines: page.lines[board.source] || null,
                                     focusTier: page.focusTier }, extra || {});
    }

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
      last = layout(board, pageState());
      drawChart(board, last, decimals);
      drawLegend(board);
      drawTable(board, last, decimals);
      fillModels();
      syncHarness();
      syncEfforts();
      tierLinesBox.checked = !!page.lines[board.source];
      bandsButton.disabled = !page.lines[board.source];
      reset.setAttribute("aria-disabled", String(!st.zoom && !page.focusTier));
      tip.hidden = true;
      drawPicker(board);
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
      source: () => boards.get(st.board).source,
      draw,
      // the selection changed elsewhere: this panel's picker closes unless
      // it is the one the click landed on
      selected(owner) {
        pickerOpen = owner === panel && !!page.selected;
        draw();
      },
      // zoom to a tier's band, or back to the full view
      focusTier(tier) {
        st.zoom = tier ? focusDomain(boards.get(st.board), pageState(), tier) : null;
        draw();
      },
      adopt(other) {
        for (const key of ["frontier", "labels", "lines"]) st[key] = other[key];
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

  // --- the tier panel beside the plots -------------------------------------------

  function makeTierPanel(data, page, host) {
    host.hidden = false;
    const lanes = data.lanes.filter((l) => l.carried);
    el("h2", {}, "Tiers drawn here", host);
    const note = el("p", { class: "note" }, null, host);
    const counts = el("table", { class: "counts", "aria-label": "Lanes per tier and harness" }, null, host);
    const tools = el("div", { class: "tier-tools" }, null, host);
    const viewButton = el("button", { type: "button", class: "reset", "aria-pressed": "false" }, "Show tiers on the plots", tools);
    viewButton.addEventListener("click", () => {
      page.tierView = !page.tierView;
      page.save();
      page.redraw();
    });
    const copyButton = el("button", { type: "button", class: "reset" }, "Copy as lines", tools);
    const copyBox = el("textarea", { rows: 6, readonly: "", "aria-label": "Tiers as lines, lane then tier" }, null, host);
    copyBox.hidden = true;
    const copyNote = el("p", { class: "empty" }, null, host);
    copyNote.hidden = true;
    copyButton.addEventListener("click", () => {
      const text = tierLinesText(lanes, page.tiers);
      copyBox.value = text;
      copyBox.hidden = false;
      copyNote.hidden = false;
      copyBox.focus();
      copyBox.select();
      const lineCount = text ? text.split("\n").length : 0;
      const said = (how) => { copyNote.textContent = lineCount ? `${lineCount} lines, in the review page's order, ${how}.` : "No lane has a tier yet."; };
      if (lineCount && navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => said("copied"), () => said("selected: copy them"));
      } else {
        said("selected: copy them");
      }
    });
    const sections = el("div", {}, null, host);

    // One row per harness, one column per tier, best first, the way the
    // boxes run: how many lanes each harness has at each tier, and how many
    // are not placed yet. Counts, not judgements.
    function countsTable() {
      counts.textContent = "";
      const hr = el("tr", {}, null, el("thead", {}, null, counts));
      el("th", {}, "", hr);
      for (const tier of TIERS) el("th", { class: "h" }, `T${tier}`, hr);
      el("th", { class: "h unset" }, "none", hr);
      el("th", { class: "h" }, "all", hr);
      const tb = el("tbody", {}, null, counts);
      const rows = data.harnesses.map((h) => [h, lanes.filter((l) => l.harness === h)]).concat([["all", lanes]]);
      for (const [label, mine] of rows) {
        const tr = el("tr", { class: label === "all" ? "tot" : "" }, null, tb);
        const th = el("th", {}, null, tr);
        if (label !== "all") el("span", { class: "swatch", style: `background:${harnessColour(label)}` }, null, th);
        th.appendChild(document.createTextNode(label));
        for (const tier of TIERS.concat([null])) {
          const n = mine.filter((l) => (page.tiers[l.name] || null) === tier).length;
          el("td", { class: (n ? "" : "zero") + (tier ? "" : " unset") }, String(n), tr);
        }
        el("td", { class: "tot" }, String(mine.length), tr);
      }
    }

    function laneRow(lane, parent) {
      const row = el("div", { class: "lane-row", "data-lane": lane.name }, null, parent);
      tierBoxes(row, [lane.name], page);
      const name = el("button", { type: "button", class: "nm", title: `${lane.model} ${lane.effort}` }, lane.name, row);
      name.addEventListener("click", () => {
        page.select({ key: `${lane.model} ${lane.effort}`, lanes: [lane.name] }, null);
      });
      if (!lane.rows) el("span", { class: "tag" }, "no rows", row);
      if (lane.off) el("span", { class: "tag off", title: lane.off }, "proposed off", row);
    }

    function section(tier) {
      const mine = lanes.filter((l) => (page.tiers[l.name] || null) === tier);
      const sec = el("section", { class: "tier" }, null, sections);
      const h = el("h3", {}, null, sec);
      h.appendChild(document.createTextNode(tier ? `Tier ${tier}` : "Not placed"));
      el("span", { class: "n" }, `${mine.length} lane${mine.length === 1 ? "" : "s"}`, h);
      if (tier) {
        const focusButton = el("button", { type: "button", class: "quiet-button focus",
                                           "aria-pressed": String(page.focusTier === tier) }, "Focus", h);
        focusButton.addEventListener("click", () => page.focus(page.focusTier === tier ? null : tier));
        if (page.focusTier === tier) focusButton.textContent = "Focused";
      }
      if (!mine.length) {
        el("p", { class: "empty" }, tier ? "No lane yet. Click a dot and press " + tier + ", or press a box here." : "Every carried lane has a tier.", sec);
        return;
      }
      for (const harness of data.harnesses) {
        const ordered = mine.filter((l) => l.harness === harness).sort((a, b) => a.rank - b.rank);
        if (!ordered.length) continue;
        const h4 = el("h4", {}, null, sec);
        el("span", { class: "swatch", style: `background:${harnessColour(harness)}` }, null, h4);
        h4.appendChild(document.createTextNode(harness));
        el("span", { class: "n" }, String(ordered.length), h4);
        for (const lane of groupLanes(ordered)) laneRow(lane, sec);
      }
    }

    function draw() {
      note.textContent = page.storage === "unavailable"
        ? "This browser keeps nothing for a file page, so these tiers last until the tab closes. "
          + "The wizard is where tiers are written."
        : "Kept in this browser for this catalog until you set them in the wizard, which is where "
          + "tiers are written. Counts are counts; they judge nothing.";
      viewButton.setAttribute("aria-pressed", String(page.tierView));
      countsTable();
      sections.textContent = "";
      for (const tier of TIERS) section(tier);
      section(null);
      for (const row of sections.querySelectorAll(".lane-row")) {
        row.addEventListener("mouseenter", () => page.highlight(row.getAttribute("data-lane")));
        row.addEventListener("mouseleave", () => page.highlight(null));
      }
    }
    return { draw };
  }

  // --- the page's own state, kept in this browser -----------------------------------

  function makeStore(data) {
    const key = `delegate-bench-page:${data.catalogKey}`;
    let saved = {};
    try {
      saved = JSON.parse(localStorage.getItem(key) || "{}") || {};
    } catch (_err) {
      saved = {};
    }
    const known = new Set(data.lanes.map((l) => l.name));
    const tiers = {};
    for (const [name, t] of Object.entries(saved.tiers || {})) {
      if (known.has(name) && TIERS.includes(t)) tiers[name] = t;
    }
    const lines = {};
    for (const [source, xs] of Object.entries(saved.lines || {})) {
      if (Array.isArray(xs) && xs.length === 3 && xs.every((v) => typeof v === "number" && v > 0)) lines[source] = xs.slice();
    }
    const page = { tiers, lines, tierView: !!saved.tierView, focusTier: null, selected: null, storage: "ok" };
    page.save = () => {
      try {
        localStorage.setItem(key, JSON.stringify({ tiers, lines, tierView: page.tierView }));
        page.storage = "ok";
      } catch (_err) {
        page.storage = "unavailable";
      }
    };
    page.save();
    return page;
  }

  function boot() {
    const source = document.getElementById("bench-data");
    const host = document.getElementById("plots");
    if (!source || !host) return;
    const data = JSON.parse(source.textContent);
    if (!data.boards.length) return;
    data.lanes = (data.lanes || []).map((l, rank) => Object.assign({ rank }, l));
    const page = makeStore(data);
    const panels = [];
    let count = 0;
    const every = (fn) => panels.forEach(fn);
    const tierHost = document.getElementById("tiers");
    const tierPanel = tierHost ? makeTierPanel(data, page, tierHost) : null;

    page.redraw = (onlySource) => {
      every((p) => { if (!onlySource || p.source() === onlySource) p.draw(); });
      if (tierPanel && !onlySource) tierPanel.draw();
    };
    page.setTiers = (changes) => {
      for (const [names, tier] of changes) {
        for (const name of names) {
          if (tier) page.tiers[name] = tier; else delete page.tiers[name];
        }
      }
      page.save();
      page.redraw();
    };
    page.setTier = (names, tier) => page.setTiers([[names, tier]]);
    page.select = (selection, owner) => {
      page.selected = selection;
      every((p) => p.selected(owner));
    };
    page.focus = (tier) => {
      page.focusTier = tier;
      every((p) => p.focusTier(tier));
      if (tierPanel) tierPanel.draw();
    };
    page.clearFocus = () => {
      if (!page.focusTier) return;
      page.focusTier = null;
      every((p) => p.draw());
      if (tierPanel) tierPanel.draw();
    };
    page.highlight = (laneName) => {
      const lane = data.lanes.find((l) => l.name === laneName);
      for (const chart of host.querySelectorAll("svg[role=img]")) {
        chart.classList.toggle("focusing", !!lane);
        for (const node of chart.querySelectorAll("[data-m]")) {
          node.classList.toggle("hot", !!lane && node.getAttribute("data-m") === lane.model);
        }
      }
    };

    const remove = (panel) => {
      if (panels.length < 2) return;
      panels.splice(panels.indexOf(panel), 1);
      panel.root.remove();
      every((p) => p.draw());
    };
    const add = (boardId) => {
      const panel = makePanel(data, host, count++, boardId, remove, every, page);
      panels.push(panel);
      every((p) => p.draw());
      return panel;
    };
    for (const id of data.defaults) add(id);
    if (tierPanel) tierPanel.draw();
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
    // 1 to 4 set the selected lane's tier, 0 clears it, Escape lets go
    document.addEventListener("keydown", (e) => {
      const tag = e.target && e.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (!page.selected) return;
      if (/^[1-4]$/.test(e.key)) {
        page.setTier(page.selected.lanes, Number(e.key));
        e.preventDefault();
      } else if (e.key === "0" || e.key === "Backspace" || e.key === "Delete") {
        page.setTier(page.selected.lanes, null);
        e.preventDefault();
      } else if (e.key === "Escape") {
        page.select(null);
      }
    });
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { layout, frontier, logTicks, logDomain, niceLinear, fmtMoney, fmtTickMoney, place,
                       zoomAbout, covers, panBy, bandTier, defaultLines, pointTier, groupLanes, reviewOrder,
                       tierLinesText, focusDomain, W, H, PAD };
  } else if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
    else boot();
  }
})();
