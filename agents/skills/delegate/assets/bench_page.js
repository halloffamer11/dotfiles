// Inlined into the benchmark page by scripts/bench_page.py; never loaded on
// its own. It draws one score-against-cost plot per panel from the JSON in
// #bench-data, and beside the plots a panel of the tiers drawn on this page.
// Every decision in that JSON (which lane a point is, what the pre-screen
// proposes off, which effort beats which, the order lanes are listed in) was
// made in Python; this file only filters what is shown, finds the frontier of
// it, lays it out, and holds the page's own tier choices, which live in this
// browser's localStorage under the catalog's key and are written nowhere else
// (ticket 26). A lane may also be turned off here, and "Copy as lines" gives
// every decision as `<lane> <1-4|off>` for the wizard's review page to paste;
// the sensitivity table and "beaten by" are display aids drawn from the page's
// own tiers (ticket 27). The pure functions have no DOM, so tests/test_bench_page.py
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
  // what a lane turned off on this page holds in place of a tier
  const OFF = "off";
  // meter name -> { name, harness, shade }, from the page's data; set at boot
  let SHADES = new Map();
  function setShades(meters) { SHADES = new Map((meters || []).map((m) => [m.name, m])); }

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

  // Score thresholds belong to one benchmark, whose scale is independent.
  function bandTier(score, lines) {
    if (!lines || lines.length !== 3) return null;
    return 1 + lines.filter((line) => score >= line).length;
  }

  function defaultLines(scores) {
    const values = scores.filter(Number.isFinite);
    if (!values.length) return null;
    let lo = Math.min(...values), hi = Math.max(...values);
    if (lo === hi) { lo -= Math.abs(lo) * 0.1 || 1; hi += Math.abs(hi) * 0.1 || 1; }
    return [0.25, 0.5, 0.75].map((f) => lo + f * (hi - lo));
  }

  function applyBands(board, lines, lanes, tiers, manual) {
    const carried = new Set(lanes.filter((l) => l.carried).map((l) => l.name));
    for (const p of board.points) {
      if (!p.plotted) continue;
      for (const lane of p.lanes) {
        if (carried.has(lane.name) && !manual[lane.name]) tiers[lane.name] = bandTier(p.score, lines);
      }
    }
  }

  function boardKey(board) { return JSON.stringify([board.source, board.benchmark]); }

  // The tier this page gives a point: its lanes' tier when they have one.
  // An off lane has no tier.
  function pointTier(p, tiers) {
    for (const lane of p.lanes || []) {
      const t = (tiers || {})[lane.name];
      if (TIERS.includes(t)) return t;
    }
    return null;
  }

  // Whether every lane of a point is turned off on this page.
  function pointOff(p, tiers) {
    return !!(p.lanes && p.lanes.length) && p.lanes.every((lane) => (tiers || {})[lane.name] === OFF);
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

  // One line per decided lane, `<lane> <1-4|off>`: the placed lanes in the
  // review page's order, then the off lanes, which the review page does not
  // list, in benchmark order grouped by model. A lane not placed is not written.
  // setup_tui.parse_tier_lines reads exactly this.
  function tierLinesText(lanes, tiers) {
    const placed = lanes.filter((l) => TIERS.includes(tiers[l.name]));
    const off = lanes.filter((l) => tiers[l.name] === OFF).sort((a, b) => a.rank - b.rank);
    return reviewOrder(placed, tiers).map((l) => `${l.name} ${tiers[l.name]}`)
      .concat(groupLanes(off).map((l) => `${l.name} ${OFF}`)).join("\n");
  }

  // The lanes still carried on this page: carried in the catalog, not off here.
  function carriedNames(lanes, tiers) {
    return new Set(lanes.filter((l) => l.carried && (tiers || {})[l.name] !== OFF).map((l) => l.name));
  }

  // The lanes this page may place (ticket 35). A tier is picked on a dot, and a
  // dot is a lane with rows, so a lane the catalog does not carry is placeable
  // as soon as a board draws it: the wizard carries whatever a line names. A
  // carried lane with no rows stays listed, because it still takes a tier.
  // `ultra` is never placeable — `parse_tier_lines` refuses it, so offering it
  // would only write a line the wizard throws away.
  function placeable(lanes) {
    return (lanes || []).filter((l) => (l.carried || l.rows) && l.effort !== "ultra");
  }

  // At least the score for no more money, and strictly better in one of the
  // two: the pre-screen's comparison (setup_tui._beats), here across models.
  function beats(o, q) {
    return o.score >= q.score && o.cost <= q.cost && (o.score > q.score || o.cost < q.cost);
  }

  // {lane: the carried lane that beats it on this one board}. A display aid
  // like the frontier (ticket 27, item 5): any model may beat any other, costs
  // are compared only inside the board, and the carry rule is not this. When
  // several beat a lane, the one named scores most, then costs least.
  function beatenByLane(board, carried) {
    const carriedOf = (p) => p.lanes.filter((l) => carried.has(l.name)).map((l) => l.name);
    const pts = board.points.filter((p) => p.plotted && carriedOf(p).length);
    const out = {};
    for (const q of pts) {
      const own = carriedOf(q);
      let best = null;
      for (const o of pts) {
        if (o === q || carriedOf(o).some((n) => own.includes(n)) || !beats(o, q)) continue;
        if (!best || o.score > best.score || (o.score === best.score
            && (o.cost < best.cost || (o.cost === best.cost && carriedOf(o)[0] < carriedOf(best)[0])))) best = o;
      }
      if (best) for (const name of own) out[name] = carriedOf(best)[0];
    }
    return out;
  }

  // The tier panel's grouping, which the sensitivity table follows: tiers 4
  // to 1, then off, then not placed; inside each, one group per meter in the
  // page's meter order; inside that, benchmark order grouped by model.
  function panelGroups(lanes, tiers, meters) {
    const order = (meters || []).map((m) => m.name);
    return TIERS.concat([OFF, null]).map((tier) => {
      const mine = placeable(lanes).filter((l) => ((tiers || {})[l.name] || null) === tier);
      const names = order.concat([...new Set(mine.map((l) => l.meter))].filter((m) => !order.includes(m)));
      const groups = [];
      for (const meter of names) {
        const ms = mine.filter((l) => l.meter === meter).sort((a, b) => a.rank - b.rank);
        if (ms.length) groups.push({ meter, lanes: groupLanes(ms) });
      }
      return { tier, count: mine.length, meters: groups };
    });
  }

  // The tier each board alone would give each placed lane (ticket 27, item 4):
  // the board ranks the placed lanes it measured by score (a lane on two points
  // takes its best) and cuts that ranking in the proportions of the page's tier
  // counts, tier 4 first. Lanes that tie on score take the better tier. A
  // board's composite index is shown and never counted in `agree`.
  function sensitivity(boards, lanes, tiers, meters) {
    const groups = panelGroups(lanes, tiers, meters).filter((g) => TIERS.includes(g.tier));
    const counts = {};
    for (const g of groups) counts[g.tier] = g.count;
    const placed = groups.flatMap((g) => g.meters.flatMap((m) => m.lanes));
    const names = new Set(placed.map((l) => l.name));
    const given = {};
    for (const b of boards) {
      const best = new Map();
      for (const p of b.points) {
        if (!p.plotted) continue;
        for (const l of p.lanes) {
          if (names.has(l.name) && (!best.has(l.name) || p.score > best.get(l.name))) best.set(l.name, p.score);
        }
      }
      const ranked = [...best.entries()].sort((x, y) => y[1] - x[1] || (x[0] < y[0] ? -1 : 1));
      const ends = [];
      let cum = 0;
      for (const t of TIERS) {
        cum += counts[t] || 0;
        ends.push([t, Math.round(ranked.length * cum / placed.length)]);
      }
      const mine = given[b.id] = {};
      let tieStart = 0;
      ranked.forEach(([name, score], i) => {
        if (i > 0 && score !== ranked[i - 1][1]) tieStart = i;
        mine[name] = (ends.find(([, end]) => tieStart < end) || ends[ends.length - 1])[0];
      });
    }
    const row = (l) => {
      const tier = tiers[l.name];
      const cells = boards.map((b) => {
        const t = given[b.id][l.name];
        return t === undefined ? null : { tier: t, differs: t !== tier };
      });
      const counted = cells.filter((c, i) => c && !boards[i].composite);
      return { name: l.name, meter: l.meter, tier, cells,
               agree: counted.filter((c) => !c.differs).length, measured: counted.length };
    };
    return { counts,
             columns: boards.map((b) => ({ id: b.id, benchmark: b.benchmark, source: b.source, composite: !!b.composite })),
             groups: groups.map((g) => ({ tier: g.tier, count: g.count, rows: g.meters.flatMap((m) => m.lanes.map(row)) })) };
  }

  // The zoom that shows one tier: its band between the tier lines when there
  // are lines, else the points this page gives that tier. Hand assignments
  // remain in view even outside their score band. Null when there is nothing to show.
  function focusDomain(board, st, tier) {
    const shown = board.points.filter((p) => isShown(p, st));
    const mine = shown.filter((p) => p.lanes.length && pointTier(p, st.tiers) === tier);
    const lines = st.tierLines;
    let pool = mine, scores;
    if (lines && lines.length === 3) {
      const lo = tier > 1 ? lines[tier - 2] : Math.min(...shown.map((p) => p.score));
      const hi = tier < 4 ? lines[tier - 1] : Math.max(...shown.map((p) => p.score));
      pool = shown.filter((p) => bandTier(p.score, lines) === tier);
      pool = [...new Set([...pool, ...mine])];
      scores = [lo, hi, ...mine.map((p) => p.score)];
    } else scores = mine.map((p) => p.score);
    if (!pool.length) return null;
    const [xlo, xhi] = logDomain(pool.map((p) => p.cost));
    const lin = niceLinear(Math.min(...scores), Math.max(...scores));
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
    const H = st.height || 500;
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
      out.lines = tierLines.map((score, index) => ({ score, index, y: Y(score), inside: score >= ylo && score <= yhi }));
      const edges = [ylo, ...tierLines, yhi].map((s) => Math.min(Math.max(s, ylo), yhi));
      out.bands = TIERS.slice().reverse().map((tier, i) => ({ tier, y0: Y(edges[i + 1]), y1: Y(edges[i]) }))
        .filter((b) => b.y1 - b.y0 > 14);
    }

    const tiers = st.tiers || {};
    const inFrame = shown.filter((p) => p.cost >= xlo && p.cost <= xhi && p.score >= ylo && p.score <= yhi);
    out.points = inFrame
      .map((p) => {
        const tier = pointTier(p, tiers);
        return { p, x: X(p.cost), y: Y(p.score), frontier: onFrontier.has(p), tier, off: pointOff(p, tiers),
                 band: bandTier(p.score, tierLines), dim: !!st.focusTier && tier !== st.focusTier };
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

  // Colour is the meter (ticket 27): a meter takes its harness's colour, and a
  // second meter on one harness a shade of it (`--h-claude-1`). A shade the
  // style does not define falls back to the harness colour.
  function meterColour(meter) {
    const m = SHADES.get(meter);
    if (!m) return "var(--accent)";
    return m.shade ? `var(--h-${m.harness}-${m.shade}, var(--h-${m.harness}, var(--accent)))` : harnessColour(m.harness);
  }

  function pointColour(p) {
    if (p.kind === "comparator") return "var(--muted)";
    if (p.meter && p.meter.length && SHADES.has(p.meter[0])) return meterColour(p.meter[0]);
    return harnessColour(harnessKeys(p)[0]);
  }

  // Shape and fill carry the kind, a dashed outline weak provenance, colour
  // the meter, and in the tier view the digit inside a lane's dot is the
  // tier this page gives it; a hollow dot there has none yet, and a struck one
  // is off. Never colour alone.
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
      } else if (view.off) {
        svg("circle", { cx, cy, r: 6.5, fill: "var(--surface)", stroke: colour, "stroke-width": 1.5, class: "mk" }, g);
        svg("path", { d: `M${cx - 8},${cy} L${cx + 8},${cy}`, stroke: "var(--off)", "stroke-width": 2.2,
                      "stroke-linecap": "round" }, g);
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

  function tipLines(p, board, decimals, page, tierLines, beaten) {
    const lines = [[`${p.name} ${p.effort}`, "tip-head"],
                   [`${fmtScore(p.score, board.unit, decimals)} for ${fmtMoney(p.cost)}`, ""]];
    if (p.lanes.length) {
      for (const lane of p.lanes) {
        const here = page.tiers[lane.name];
        lines.push([`${lane.name}: ${here === OFF ? "off here" : here ? `tier ${here} here` : "no tier here yet"}, `
                    + `${lane.tier ?? "—"} in the catalog`, "mono"]);
      }
      for (const lane of p.lanes) {
        if (beaten && beaten[lane.name]) lines.push([`beaten by ${beaten[lane.name]} on this board`, "beaten"]);
      }
      const band = bandTier(p.score, tierLines);
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

  // Four boxes, one per tier, and off beside them, at most one pressed: the
  // review page's marker, on the page, with the carry decision after it.
  function tierBoxes(parent, names, page, size) {
    const boxes = el("span", { class: "boxes", role: "group", "aria-label": "Tier or off" }, null, parent);
    const current = page.tiers[names[0]] || null;
    for (const t of TIERS.concat([OFF])) {
      const b = el("button", { type: "button", class: t === OFF ? "box off-box" : "box", "aria-pressed": String(current === t),
                               "aria-label": t === OFF ? "off" : `tier ${t}` }, String(t), boxes);
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
    let H = 500;

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
    const canvas = el("div", { class: "plot-canvas" }, null, wrap);
    const chart = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" }, canvas);
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

    // Each benchmark has its own score scale and thresholds.
    const tiersFs = el("fieldset", {}, null, rail);
    el("legend", {}, "Tier lines", tiersFs);
    const tierLinesLabel = el("label", { class: "check" }, null, tiersFs);
    const tierLinesBox = el("input", { type: "checkbox" }, null, tierLinesLabel);
    tierLinesLabel.appendChild(document.createTextNode("Draw the three lines on this benchmark's score axis"));
    tierLinesBox.addEventListener("change", () => {
      const board = boards.get(st.board);
      if (tierLinesBox.checked) {
        if (!page.lines[boardKey(board)]) {
          const scores = board.points.filter((p) => isShown(p, st) && p.lanes.length).map((p) => p.score);
          const lines = defaultLines(scores.length ? scores : board.points.filter((p) => isShown(p, st)).map((p) => p.score));
          if (lines) page.lines[boardKey(board)] = lines;
        }
      } else {
        delete page.lines[boardKey(board)];
      }
      page.save();
      page.redraw();
    });
    const bandsButton = el("button", { type: "button", class: "quiet-button bands-button" },
                           "Give every lane on this plot its band's tier", tiersFs);
    bandsButton.addEventListener("click", () => {
      const board = boards.get(st.board);
      const lines = page.lines[boardKey(board)];
      if (!lines) return;
      applyBands(board, lines, data.lanes, page.tiers, page.manual);
      page.save();
      page.redraw();
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
      const sample = (kind, extra) => Object.assign({ kind, weak: false, harness: [], meter: [], tier: null, lanes: [] }, extra);
      const view = { tierView: page.tierView, tier: page.tierView ? 2 : null };
      const one = data.harnesses.length ? [data.harnesses[0]] : [];
      const meters = data.meters || [];
      for (const m of meters) items.push([sample("lane", { harness: [m.harness], meter: [m.name] }), `a ${m.name} lane`, view]);
      if (!meters.length) for (const h of data.harnesses) items.push([sample("lane", { harness: [h] }), `a ${h} lane`, view]);
      if (page.tierView) {
        items.push([sample("lane", { harness: one }), "the digit is the tier drawn here", view],
                   [sample("lane", { harness: one }), "hollow: no tier here yet", { tierView: true, tier: null }],
                   [sample("lane", { harness: one }), "struck: off here", { tierView: true, tier: null, off: true }]);
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
      if (page.lines[boardKey(board)]) {
        el("span", { class: "item note" }, "Dragging a score line assigns bands. Hand-set tiers stay until cleared.", legend);
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
        svg("text", { x: W - PAD.r - 5, y: (b.y0 + b.y1) / 2, "text-anchor": "end", class: "band-name" }, chart)
          .textContent = `tier ${b.tier}`;
      }
      for (const l of lay.lines) {
        if (!l.inside) continue;
        const g = svg("g", { class: "tier-handle", "data-line": l.index }, chart);
        svg("line", { x1: PAD.l, x2: W - PAD.r, y1: l.y, y2: l.y, class: "tier-grip" }, g);
        svg("line", { x1: PAD.l, x2: W - PAD.r, y1: l.y, y2: l.y, class: "tier-line" }, g);
        g.addEventListener("pointerdown", (e) => {
          if (e.button !== 0) return;
          e.stopPropagation();
          e.preventDefault();
          lineDrag = { index: l.index, key: boardKey(board) };
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
        marker(g, q.p, q.x, q.y, { tierView: page.tierView, tier: q.tier, off: q.off });
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
      const scale = chart.clientWidth / W;
      const left = q.x * scale, top = q.y * scale;
      const bw = box.offsetWidth, wrapW = wrap.clientWidth;
      box.style.left = `${left + 14 + bw > wrapW ? left - 14 - bw : left + 14}px`;
      box.style.top = `${Math.max(4, top - 12)}px`;
    }

    function showTip(q, board, decimals) {
      if (pickerOpen && selectedKey() === pointKey(q.p)) return;
      tip.textContent = "";
      const beaten = beatenByLane(board, carriedNames(data.lanes, page.tiers));
      for (const [text, cls] of tipLines(q.p, board, decimals, page, page.lines[boardKey(board)], beaten)) {
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
      const band = bandTier(q.p.score, page.lines[boardKey(board)]);
      el("p", { class: "quiet" }, band ? `Press 1 to 4, or o for off. The band proposes tier ${band}.`
                                       : "Press 1 to 4, or o for off.", picker);
      picker.hidden = false;
      placeNear(picker, q);
      tip.hidden = true;
    }

    // drag to zoom or pan, click to select a dot, double-click to reset
    let band = null, drag = null, downOnPoint = null, lineDrag = null, frame = null;
    function toSvg(e) {
      const r = chart.getBoundingClientRect(), scale = chart.clientWidth / W;
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
        const [, y] = toSvg(e);
        const lines = page.lines[lineDrag.key];
        if (!lines) return;
        let score = scoreAt(y);
        const i = lineDrag.index;
        if (i > 0) score = Math.max(score, lines[i - 1] + (last.domain.yhi - last.domain.ylo) * 0.001);
        if (i < 2) score = Math.min(score, lines[i + 1] - (last.domain.yhi - last.domain.ylo) * 0.001);
        lines[i] = score;
        applyBands(boards.get(st.board), lines, data.lanes, page.tiers, page.manual);
        soon(() => page.redraw());
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
      return Object.assign({}, st, { height: H, tiers: page.tiers, tierLines: page.lines[boardKey(board)] || null,
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
      H = Math.max(PAD.t + PAD.b + 50, chart.clientHeight / (chart.clientWidth || W) * W);
      chart.setAttribute("viewBox", `0 0 ${W} ${H}`);
      last = layout(board, pageState());
      drawChart(board, last, decimals);
      drawLegend(board);
      drawTable(board, last, decimals);
      fillModels();
      syncHarness();
      syncEfforts();
      tierLinesBox.checked = !!page.lines[boardKey(board)];
      bandsButton.disabled = !page.lines[boardKey(board)];
      reset.setAttribute("aria-disabled", String(!st.zoom && !page.focusTier));
      tip.hidden = true;
      drawPicker(board);
      remove.hidden = host.querySelectorAll("section.plot").length < 2;
      focus(null);
      highlightLane();
    }

    select.addEventListener("change", () => {
      st.board = select.value;
      st.zoom = null;
      st.pinned = null;
      draw();
      // the panel's "beaten by" is judged on the boards shown
      if (page.boardChanged) page.boardChanged();
    });

    function highlightLane() {
      chart.querySelectorAll(".lane-highlight").forEach((n) => n.remove());
      const names = page.hovered ? [page.hovered] : (page.selected ? page.selected.lanes : []);
      for (const q of (last ? last.points : [])) {
        if (!q.p.lanes.some((l) => names.includes(l.name))) continue;
        const g = svg("g", { class: "lane-highlight", "pointer-events": "none" }, chart);
        svg("circle", { cx: q.x, cy: q.y, r: 14, class: "sel" }, g);
        const text = names.filter((n) => q.p.lanes.some((l) => l.name === n)).join(", ");
        const x = Math.min(W - PAD.r - text.length * CHAR_PX, Math.max(PAD.l, q.x + 16));
        svg("text", { x, y: Math.max(PAD.t + 14, q.y - 16), class: "label hot" }, g).textContent = text;
      }
    }
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(() => { if (last) draw(); }).observe(canvas);
    }

    const panel = {
      root,
      highlightLane,
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

  function makeTierPanel(data, page, host, sensHost) {
    host.hidden = false;
    const lanes = placeable(data.lanes);
    const meters = (data.meters || []).filter((m) => lanes.some((l) => l.meter === m.name));
    el("h2", {}, "Tiers drawn here", host);
    const note = el("p", { class: "note" }, null, host);
    const counts = el("table", { class: "counts", "aria-label": "Lanes per tier and meter" }, null, host);
    const tools = el("div", { class: "tier-tools" }, null, host);
    const viewButton = el("button", { type: "button", class: "reset", "aria-pressed": "false" }, "Show tiers on the plots", tools);
    viewButton.addEventListener("click", () => {
      page.tierView = !page.tierView;
      page.save();
      page.redraw();
    });
    const copyButton = el("button", { type: "button", class: "reset" }, "Copy as lines", tools);
    // It drops drawn work, so it asks first, once (ticket 36).
    const resetButton = el("button", { type: "button", class: "reset" }, "Reset every tier", tools);
    resetButton.addEventListener("click", () => {
      const drawn = Object.keys(page.tiers).length;
      const asked = typeof window !== "undefined" && window.confirm
        ? window.confirm(drawn
            ? `Clear the ${drawn} tier${drawn === 1 ? "" : "s"} drawn here, and every tier line? `
              + "The catalog's own tiers are not touched."
            : "Clear every tier line drawn here? The catalog's own tiers are not touched.")
        : true;
      if (!asked) return;
      page.resetAll();
      page.redraw();
    });
    const copyBox = el("textarea", { rows: 6, readonly: "", "aria-label": "Decisions as lines, lane then tier or off" }, null, host);
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
      const lines = text ? text.split("\n") : [];
      const lineCount = lines.length;
      const offCount = lines.filter((line) => line.endsWith(` ${OFF}`)).length;
      const said = (how) => {
        copyNote.textContent = lineCount
          ? `${lineCount} lines, ${lineCount - offCount} with a tier and ${offCount} off, in the review page's order, ${how}. `
            + "On the wizard's review page, press v to apply them; or save them to a file for setup.py --tiers-from."
          : "No lane has a tier or is off yet.";
      };
      if (lineCount && navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => said("copied"), () => said("selected: copy them"));
      } else {
        said("selected: copy them");
      }
    });
    const sections = el("div", {}, null, host);

    // One row per meter, one column per tier, best first, the way the boxes
    // run, then off: how many lanes each meter has at each tier, how many are
    // off, and how many are not placed yet. Counts, not judgements.
    function countsTable() {
      counts.textContent = "";
      const hr = el("tr", {}, null, el("thead", {}, null, counts));
      el("th", {}, "", hr);
      for (const tier of TIERS) el("th", { class: "h" }, `T${tier}`, hr);
      el("th", { class: "h" }, "off", hr);
      el("th", { class: "h unset" }, "none", hr);
      el("th", { class: "h" }, "all", hr);
      const tb = el("tbody", {}, null, counts);
      const rows = meters.map((m) => [m.name, lanes.filter((l) => l.meter === m.name)]).concat([["all", lanes]]);
      for (const [label, mine] of rows) {
        const tr = el("tr", { class: label === "all" ? "tot" : "" }, null, tb);
        const th = el("th", {}, null, tr);
        if (label !== "all") el("span", { class: "swatch", style: `background:${meterColour(label)}` }, null, th);
        th.appendChild(document.createTextNode(label));
        for (const tier of TIERS.concat([OFF, null])) {
          const n = mine.filter((l) => (page.tiers[l.name] || null) === tier).length;
          el("td", { class: (n ? "" : "zero") + (tier ? "" : " unset") }, String(n), tr);
        }
        el("td", { class: "tot" }, String(mine.length), tr);
      }
    }

    // {lane: [{by, benchmark}]} over the boards the plots show, each board once
    function beatenOnShown() {
      const carried = carriedNames(data.lanes, page.tiers);
      const out = {};
      for (const board of page.shownBoards ? page.shownBoards() : []) {
        for (const [name, by] of Object.entries(beatenByLane(board, carried))) {
          (out[name] = out[name] || []).push({ by, benchmark: board.benchmark });
        }
      }
      return out;
    }

    function laneRow(lane, parent, beaten) {
      const isOff = page.tiers[lane.name] === OFF;
      const row = el("div", { class: "lane-row" + (isOff ? " is-off" : ""), "data-lane": lane.name }, null, parent);
      tierBoxes(row, [lane.name], page);
      const name = el("button", { type: "button", class: "nm", title: `${lane.model} ${lane.effort}` }, lane.name, row);
      name.addEventListener("click", () => {
        page.select({ key: `${lane.model} ${lane.effort}`, lanes: [lane.name] }, null);
      });
      if (!lane.rows) el("span", { class: "tag" }, "no rows", row);
      // the page places a lane the catalog does not carry (ticket 35), and says
      // so, because a line that carries it is a change the wizard will make
      if (!lane.carried) {
        el("span", { class: "tag", title: "the catalog does not carry this lane; a tier here carries it" },
           "not carried", row);
      }
      if (lane.off) el("span", { class: "tag off", title: lane.off }, "proposed off", row);
      const by = beaten[lane.name];
      if (by) {
        el("span", { class: "tag beaten", title: by.map((b) => `on ${b.benchmark}: beaten by ${b.by}`).join("\n") },
           `beaten by ${[...new Set(by.map((b) => b.by))].join(", ")}`, row);
      }
    }

    function section(group, beaten) {
      const tier = group.tier;
      const sec = el("section", { class: "tier" }, null, sections);
      const h = el("h3", {}, null, sec);
      h.appendChild(document.createTextNode(tier === OFF ? "Off" : tier ? `Tier ${tier}` : "Not placed"));
      el("span", { class: "n" }, `${group.count} lane${group.count === 1 ? "" : "s"}`, h);
      if (TIERS.includes(tier)) {
        const focusButton = el("button", { type: "button", class: "quiet-button focus",
                                           "aria-pressed": String(page.focusTier === tier) }, "Focus", h);
        focusButton.addEventListener("click", () => page.focus(page.focusTier === tier ? null : tier));
        if (page.focusTier === tier) focusButton.textContent = "Focused";
      }
      if (!group.count) {
        el("p", { class: "empty" }, tier === OFF ? "No lane is off. Press off on a lane's line, or click a dot and press o."
          : tier ? "No lane yet. Click a dot and press " + tier + ", or press a box here."
          : "Every lane here has a tier or is off.", sec);
        return;
      }
      for (const m of group.meters) {
        const h4 = el("h4", {}, null, sec);
        el("span", { class: "swatch", style: `background:${meterColour(m.meter)}` }, null, h4);
        h4.appendChild(document.createTextNode(m.meter));
        el("span", { class: "n" }, String(m.lanes.length), h4);
        for (const lane of m.lanes) laneRow(lane, sec, beaten);
      }
    }

    // The sensitivity table under the plots: what each board alone would give.
    function drawSensitivity() {
      if (!sensHost) return;
      sensHost.hidden = false;
      sensHost.textContent = "";
      el("h2", {}, "What each board alone would give", sensHost);
      const s = sensitivity(data.boards, lanes, page.tiers, data.meters);
      if (!s.groups.some((g) => g.count)) {
        el("p", { class: "lede" }, "Give lanes a tier and this table shows, for each board, the tier its "
          + "ranking alone would give each of them in the proportions you chose.", sensHost);
        return;
      }
      const shares = TIERS.map((t) => `${s.counts[t] || 0} on tier ${t}`).join(", ");
      el("p", { class: "lede" }, "Each board ranks the placed lanes it measured by score and cuts them in "
        + `the proportions you gave: ${shares}. A marked cell differs from your tier; a dash is a board `
        + "that did not measure the lane. The last column counts the boards that agree out of the boards "
        + "that measured the lane; a shaded column is a composite index, shown and never counted.", sensHost);
      const scroll = el("div", { class: "scroll" }, null, sensHost);
      const t = el("table", { class: "sens" }, null, scroll);
      const hr = el("tr", {}, null, el("thead", {}, null, t));
      el("th", { class: "lane" }, "Lane", hr);
      el("th", { class: "cell" }, "Yours", hr);
      for (const c of s.columns) {
        const th = el("th", { class: "cell" + (c.composite ? " composite" : ""), title: `${c.benchmark}, ${c.source}` },
                      c.benchmark, hr);
        el("span", { class: "sub" }, c.composite ? `${c.source}, not counted` : c.source, th);
      }
      el("th", { class: "cell" }, "Agree", hr);
      const tb = el("tbody", {}, null, t);
      for (const g of s.groups) {
        if (!g.rows.length) continue;
        const gh = el("th", { colspan: String(s.columns.length + 3) }, `Tier ${g.tier}`, el("tr", { class: "grp" }, null, tb));
        el("span", { class: "n" }, `${g.count} lane${g.count === 1 ? "" : "s"}`, gh);
        for (const r of g.rows) {
          const tr = el("tr", { "data-lane": r.name }, null, tb);
          const td = el("td", { class: "lane" }, null, tr);
          el("span", { class: "swatch", style: `background:${meterColour(r.meter)}` }, null, td);
          td.appendChild(document.createTextNode(r.name));
          el("td", { class: "mine" }, String(r.tier), tr);
          r.cells.forEach((cell, i) => {
            const comp = s.columns[i].composite ? " composite" : "";
            if (!cell) {
              el("td", { class: "cell none" + comp }, "—", tr);
              return;
            }
            const attrs = { class: "cell" + (cell.differs ? " diff" : "") + comp };
            if (cell.differs) attrs.title = `${s.columns[i].benchmark} alone: tier ${cell.tier}; yours: tier ${r.tier}`;
            el("span", {}, String(cell.tier), el("td", attrs, null, tr));
          });
          el("td", { class: "agree" }, r.measured ? `${r.agree}/${r.measured}` : "—", tr);
          tr.addEventListener("mouseenter", () => page.highlight(r.name));
          tr.addEventListener("mouseleave", () => page.highlight(null));
        }
      }
    }

    function draw() {
      note.textContent = page.storage === "unavailable"
        ? "This browser keeps nothing for a file page, so these tiers last until the tab closes. "
          + "The wizard is where tiers are written."
        : "Kept in this browser for this catalog until you paste them into the wizard, which is where "
          + "tiers are written. Counts are per meter, and judge nothing.";
      viewButton.setAttribute("aria-pressed", String(page.tierView));
      countsTable();
      sections.textContent = "";
      const beaten = beatenOnShown();
      for (const group of panelGroups(lanes, page.tiers, data.meters)) section(group, beaten);
      drawSensitivity();
      page.highlight(page.hovered);
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
      if (known.has(name) && (TIERS.includes(t) || t === OFF)) tiers[name] = t;
    }
    const manual = {};
    for (const name of Object.keys(tiers)) {
      if (saved.version !== 2 || (saved.manual || {})[name]) manual[name] = true;
    }
    const lines = {};
    for (const [key, xs] of Object.entries(saved.version === 2 ? saved.lines || {} : {})) {
      if (data.boards.some((b) => boardKey(b) === key) && Array.isArray(xs) && xs.length === 3
          && xs.every(Number.isFinite) && xs[0] < xs[1] && xs[1] < xs[2]) lines[key] = xs.slice();
    }
    const page = { tiers, lines, manual, hovered: null, tierView: !!saved.tierView, focusTier: null, selected: null, storage: "ok" };
    page.save = () => {
      try {
        localStorage.setItem(key, JSON.stringify({ version: 2, tiers, lines, manual, tierView: page.tierView }));
        page.storage = "ok";
      } catch (_err) {
        page.storage = "unavailable";
      }
    };
    // Everything this page holds for this catalog, gone: every tier and off
    // drawn, every manual mark, and the three lines on every board, which go
    // back to undrawn and are recomputed from the scores when they are asked
    // for again. What stays is the tier view toggle, which is how the page is
    // read rather than what it holds. The focused tier goes too: there is
    // nothing left to focus on, and a page still hiding dots for it would read
    // as empty. Nothing outside the browser is touched, as nothing here ever is
    // (ticket 36).
    page.resetAll = () => {
      for (const holder of [tiers, manual, lines]) {
        for (const name of Object.keys(holder)) delete holder[name];
      }
      page.focusTier = null;
      page.save();
    };
    page.save();
    return page;
  }

  // --- price per model ---------------------------------------------------------
  // One row per model, two dots on one log axis: what the vendor lists per 1M
  // tokens in and out (ticket 36). Efforts collapsed, because every effort of a
  // model is charged the same. Colour is the meter, as everywhere else here;
  // identity is the row's own name beside it, so colour carries nothing alone.
  // Input is an open dot and output a filled one, the two marks a row needs,
  // rather than a second hue for the same money.

  const PRICE_ROW = 26, PRICE_PAD = { l: 200, r: 64, t: 10, b: 34 };
  // the page's surface, for an open dot's fill and a filled dot's ring
  const SURFACE = "var(--surface, #ffffff)";

  function priceValues(rows) {
    const out = [];
    for (const row of rows) {
      for (const key of ["in", "out"]) {
        if (typeof row[key] === "number" && row[key] > 0) out.push(row[key]);
        const span = row[`${key}_range`];
        if (Array.isArray(span)) for (const v of span) if (v > 0) out.push(v);
      }
    }
    return out;
  }

  function drawPrices(rows, host) {
    host.textContent = "";
    const values = priceValues(rows);
    const height = PRICE_PAD.t + rows.length * PRICE_ROW + PRICE_PAD.b;
    const frame = svg("svg", {
      viewBox: `0 0 ${W} ${height}`, class: "price-plot", role: "img",
      "aria-label": "List price per 1M tokens, input and output, per model, on a log scale",
    }, host);
    if (!values.length) return frame;
    const [lo, hi] = logDomain(values);
    const x0 = PRICE_PAD.l, x1 = W - PRICE_PAD.r;
    const at = (v) => x0 + (Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo)) * (x1 - x0);
    const bottom = height - PRICE_PAD.b;

    for (const tick of logTicks(lo, hi)) {
      const x = at(tick);
      svg("line", { x1: x, y1: PRICE_PAD.t, x2: x, y2: bottom, class: "grid" }, frame);
      svg("text", { x, y: bottom + 16, class: "tick mid" }, frame).textContent = fmtTickMoney(tick);
    }
    svg("text", { x: (x0 + x1) / 2, y: bottom + 30, class: "axis-title mid" }, frame)
      .textContent = "USD per 1M tokens (log)";

    rows.forEach((row, index) => {
      const y = PRICE_PAD.t + index * PRICE_ROW + PRICE_ROW / 2;
      const colour = meterColour(row.meter);
      const name = svg("text", { x: x0 - 12, y: y + 4, class: "price-name" + (row.carried ? "" : " quiet"),
                                 "text-anchor": "end" }, frame);
      // the gutter is fixed, so a name too long for it is cut rather than drawn
      // off the edge; the row's own tooltip still says it whole
      const room = Math.floor((x0 - 16) / CHAR_PX);
      name.textContent = row.model.length > room ? row.model.slice(0, room - 1) + "\u2026" : row.model;
      const said = [`${row.model}: ${row.efforts.length} effort${row.efforts.length === 1 ? "" : "s"}`,
                    row.meter ? `meter ${row.meter}` : null,
                    row.carried ? "carried" : "not carried",
                    `in ${fmtMoney(row.in)}`, `out ${fmtMoney(row.out)}`].filter(Boolean);
      svg("title", {}, svg("rect", { x: 0, y: y - PRICE_ROW / 2, width: W, height: PRICE_ROW,
                                     class: "price-hit" }, frame)).textContent = said.join(" · ");
      if (row.in === null && row.out === null) {
        svg("text", { x: x0, y: y + 4, class: "price-none" }, frame).textContent = "no published price";
        return;
      }
      if (row.in !== null && row.out !== null) {
        svg("line", { x1: at(row.in), y1: y, x2: at(row.out), y2: y,
                      class: "price-link", stroke: colour }, frame);
      }
      for (const key of ["in", "out"]) {
        const value = row[key];
        if (value === null) continue;
        const span = row[`${key}_range`];
        if (span) {
          svg("line", { x1: at(span[0]), y1: y, x2: at(span[1]), y2: y,
                        class: "price-span", stroke: colour }, frame);
        }
        // the filled dot takes its 2px ring from the surface in CSS, so it stays
        // legible where two rows' dots meet; the open one is the meter's colour
        const dot = svg("circle", { cx: at(value), cy: y, r: 5,
                                    class: key === "out" ? "price-dot out" : "price-dot in",
                                    fill: key === "out" ? colour : SURFACE }, frame);
        if (key === "in") dot.setAttribute("stroke", colour);
        svg("title", {}, dot).textContent =
          `${row.model} · ${key === "out" ? "output" : "input"} ${fmtMoney(value)} per 1M tokens`
          + (span ? ` · efforts disagree: ${fmtMoney(span[0])} to ${fmtMoney(span[1])}` : "");
        // the cheaper end labels left and the dearer right, so the two never sit
        // on top of each other however close the prices are; a label that would
        // reach into the name gutter flips to the right of its dot instead. A
        // disagreement reads as the range itself, which is the whole of what
        // there is to say about it.
        const text = span ? `${fmtMoney(span[0])}\u2013${fmtMoney(span[1])}` : fmtMoney(value);
        const other = key === "in" ? row.out : row.in;
        let left = other !== null && value <= other;
        if (left && at(value) - 10 - (text.length * CHAR_PX + 6) < x0 - 4) left = false;
        svg("text", { x: at(value) + (left ? -10 : 10), y: y + 4, class: "price-value",
                      "text-anchor": left ? "end" : "start" }, frame).textContent = text;
      }
    });
    return frame;
  }

  function bootPrices() {
    const source = document.getElementById("price-data");
    const host = document.getElementById("price-chart");
    if (!source || !host) return;
    const data = JSON.parse(source.textContent);
    if (!SHADES.size) setShades(data.meters);
    const key = el("p", { class: "price-key" }, null, host);
    svg("circle", { cx: 6, cy: 6, r: 4, class: "price-dot in", fill: SURFACE, stroke: "var(--muted)" },
        svg("svg", { viewBox: "0 0 12 12", class: "key", "aria-hidden": "true" }, key));
    key.appendChild(document.createTextNode(" input  "));
    svg("circle", { cx: 6, cy: 6, r: 4, class: "price-dot out", fill: "var(--muted)" },
        svg("svg", { viewBox: "0 0 12 12", class: "key", "aria-hidden": "true" }, key));
    key.appendChild(document.createTextNode(" output"));
    drawPrices(data.rows || [], el("div", { class: "price-body" }, null, host));
  }

  function boot() {
    bootPrices();
    const source = document.getElementById("bench-data");
    const host = document.getElementById("plots");
    if (!source || !host) return;
    const data = JSON.parse(source.textContent);
    if (!data.boards.length) return;
    data.lanes = (data.lanes || []).map((l, rank) => Object.assign({ rank }, l));
    setShades(data.meters);
    const page = makeStore(data);
    const panels = [];
    let count = 0;
    const every = (fn) => panels.forEach(fn);
    const tierHost = document.getElementById("tiers");
    const tierPanel = tierHost ? makeTierPanel(data, page, tierHost, document.getElementById("sensitivity")) : null;
    page.shownBoards = () => {
      const ids = new Set(panels.map((p) => p.board()));
      return data.boards.filter((b) => ids.has(b.id));
    };
    page.boardChanged = () => { if (tierPanel) tierPanel.draw(); };

    page.redraw = (onlySource) => {
      every((p) => { if (!onlySource || p.source() === onlySource) p.draw(); });
      if (tierPanel && !onlySource) tierPanel.draw();
    };
    page.setTiers = (changes) => {
      for (const [names, tier] of changes) {
        for (const name of names) {
          if (tier) { page.tiers[name] = tier; page.manual[name] = true; }
          else { delete page.tiers[name]; delete page.manual[name]; }
        }
      }
      page.save();
      page.redraw();
    };
    page.setTier = (names, tier) => page.setTiers([[names, tier]]);
    page.select = (selection, owner) => {
      page.selected = selection;
      every((p) => p.selected(owner));
      page.highlight(null);
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
      page.hovered = laneName;
      every((p) => p.highlightLane());
      const names = page.selected ? page.selected.lanes : [];
      for (const row of tierHost.querySelectorAll(".lane-row")) {
        row.classList.toggle("selected", names.includes(row.dataset.lane));
      }
    };

    const remove = (panel) => {
      if (panels.length < 2) return;
      panels.splice(panels.indexOf(panel), 1);
      panel.root.remove();
      every((p) => p.draw());
      page.boardChanged();
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
        page.boardChanged();
      });
    }
    // 1 to 4 set the selected lane's tier, o turns it off, 0 clears it, Escape lets go
    document.addEventListener("keydown", (e) => {
      const tag = e.target && e.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (!page.selected) return;
      if (/^[1-4]$/.test(e.key)) {
        page.setTier(page.selected.lanes, Number(e.key));
        e.preventDefault();
      } else if (e.key === "o" || e.key === "O") {
        page.setTier(page.selected.lanes, OFF);
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
                       tierLinesText, focusDomain, applyBands, makeStore, boardKey, pointOff, carriedNames,
                       placeable, beatenByLane, panelGroups, sensitivity, meterColour, setShades,
                       priceValues, drawPrices, OFF, W, H, PAD };
  } else if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
    else boot();
  }
})();
