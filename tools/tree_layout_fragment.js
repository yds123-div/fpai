/**
 * 可读树状子图：固定坐标、限制规模、主干/分支视觉权重。
 * 依赖全局：RAW_NODES, RAW_EDGES, NODE_BY_ID（由 graph.html 内联脚本提供）
 */
(function (global) {
  var DEFAULTS = {
    maxDepth: 4,
    maxNodes: 200,
    maxEdges: 400,
    maxChildrenPerNode: 12,
  };

  function addUnique(arr, x) {
    if (arr.indexOf(x) === -1) arr.push(x);
  }

  function buildPredSucc(rawEdges, allowedIds) {
    var pred = new Map();
    var succ = new Map();
    function add(m, a, b) {
      if (!allowedIds.has(a) || !allowedIds.has(b)) return;
      if (!m.has(a)) m.set(a, []);
      if (m.get(a).indexOf(b) === -1) m.get(a).push(b);
    }
    for (var i = 0; i < rawEdges.length; i++) {
      var e = rawEdges[i];
      add(succ, e.from, e.to);
      add(pred, e.to, e.from);
    }
    return { pred: pred, succ: succ };
  }

  function communityBoostMap(legend) {
    var m = {};
    var maxC = 1;
    if (legend && legend.length) {
      for (var i = 0; i < legend.length; i++) {
        maxC = Math.max(maxC, legend[i].count || 1);
      }
    }
    if (legend && legend.length) {
      for (var j = 0; j < legend.length; j++) {
        var L = legend[j];
        m[L.cid] = (6 * (L.count || 0)) / maxC;
      }
    }
    return m;
  }

  function scoreOf(id, pred, succ, commBoost, rawById) {
    var raw = rawById.get(id);
    var cid = raw && raw.community != null ? raw.community : 0;
    var p = (pred.get(id) || []).length;
    var s = (succ.get(id) || []).length;
    return p + s + (commBoost[cid] || 0);
  }

  function pickFocus(focusNodeId, allowedIds, pred, succ, rawById, commBoost) {
    if (focusNodeId && allowedIds.has(focusNodeId)) return focusNodeId;
    var best = null;
    var bestSc = -1;
    allowedIds.forEach(function (id) {
      var sc = scoreOf(id, pred, succ, commBoost, rawById);
      if (sc > bestSc) {
        bestSc = sc;
        best = id;
      }
    });
    return best;
  }

  function walkMainGreedy(start, predOrSucc, rawById, pred, succ, commBoost) {
    var path = [];
    var cur = start;
    for (var step = 0; step < 24; step++) {
      var nb = predOrSucc.get(cur) || [];
      if (!nb.length) break;
      var best = nb[0];
      var bestS = scoreOf(best, pred, succ, commBoost, rawById);
      for (var i = 1; i < nb.length; i++) {
        var sc = scoreOf(nb[i], pred, succ, commBoost, rawById);
        if (sc > bestS) {
          bestS = sc;
          best = nb[i];
        }
      }
      path.push(best);
      cur = best;
    }
    return path;
  }

  /**
   * @param {object} opts
   * @param {string|null} opts.focusNodeId
   * @param {Set<string>} opts.allowedIds
   * @param {Set<string>} [opts.expandedOverflow]
   * @param {object[]} opts.rawNodes — 同 RAW_NODES
   * @param {object[]} opts.rawEdges — 同 RAW_EDGES
   * @param {Map} opts.NODE_BY_ID
   * @param {object[]} [opts.legend] — LEGEND
   */
  global.computeReadableTreeLayout = function (opts) {
    var o = Object.assign({}, DEFAULTS, opts || {});
    var allowedIds = o.allowedIds;
    var expandedOverflow = o.expandedOverflow || new Set();
    var rawNodes = o.rawNodes || [];
    var rawEdges = o.rawEdges || [];
    var legend = o.legend || [];
    var NODE_BY_ID = o.NODE_BY_ID || new Map();
    var maxDepth = o.maxDepth;
    var maxNodes = o.maxNodes;
    var maxEdges = o.maxEdges;
    var maxChildrenPerNode = o.maxChildrenPerNode;

    var commBoost = communityBoostMap(legend);
    var ps = buildPredSucc(rawEdges, allowedIds);
    var pred = ps.pred;
    var succ = ps.succ;

    var focus = pickFocus(o.focusNodeId || null, allowedIds, pred, succ, NODE_BY_ID, commBoost);
    if (!focus) {
      return {
        visNodes: [],
        visEdges: [],
        hiddenNodeCount: 0,
        hiddenEdgeCount: 0,
        levels: {},
        mainPath: [],
        nodeMeta: {},
        overflowNodes: [],
        focusNodeId: null,
      };
    }

    var outNodes = new Set();
    outNodes.add(focus);
    var level = new Map();
    level.set(focus, 0);
    var pseudoMeta = [];

    function capNeighbors(parent, neighbors, dir) {
      var cap = maxChildrenPerNode;
      if (neighbors.length <= cap) return { take: neighbors.slice(), overflow: 0, ovId: null };
      var ovId = '__tree_ov__' + parent + '__' + dir;
      if (expandedOverflow.has(ovId)) {
        var lim = Math.min(neighbors.length, Math.max(cap, cap * 4));
        var take = neighbors.slice(0, lim);
        var overflow = neighbors.length - lim;
        return { take: take, overflow: overflow, ovId: overflow > 0 ? ovId : null };
      }
      var take = neighbors.slice(0, cap - 1);
      var overflow = neighbors.length - take.length;
      return { take: take, overflow: overflow, ovId: ovId };
    }

    for (var du = 1; du <= maxDepth; du++) {
      if (outNodes.size >= maxNodes) break;
      var layer = [];
      outNodes.forEach(function (id) {
        if (String(id).indexOf('__tree_ov__') === 0) return;
        if (level.get(id) === -(du - 1)) layer.push(id);
      });
      for (var li = 0; li < layer.length; li++) {
        if (outNodes.size >= maxNodes) break;
        var u = layer[li];
        var nb = (pred.get(u) || []).filter(function (id) {
          return allowedIds.has(id);
        });
        nb.sort(function (a, b) {
          return scoreOf(b, pred, succ, commBoost, NODE_BY_ID) - scoreOf(a, pred, succ, commBoost, NODE_BY_ID);
        });
        var capU = capNeighbors(u, nb, 'up');
        for (var ci = 0; ci < capU.take.length; ci++) {
          if (outNodes.size >= maxNodes) break;
          var v = capU.take[ci];
          outNodes.add(v);
          level.set(v, Math.min(level.get(v) != null ? level.get(v) : 999, -du));
        }
        if (capU.overflow > 0 && capU.ovId && outNodes.size < maxNodes) {
          outNodes.add(capU.ovId);
          level.set(capU.ovId, -du);
          pseudoMeta.push({
            id: capU.ovId,
            parentId: u,
            dir: 'up',
            count: capU.overflow,
            hiddenIds: nb.filter(function (x) {
              return capU.take.indexOf(x) === -1;
            }),
          });
        }
      }
    }

    for (var dd = 1; dd <= maxDepth; dd++) {
      if (outNodes.size >= maxNodes) break;
      var layerD = [];
      outNodes.forEach(function (id) {
        if (String(id).indexOf('__tree_ov__') === 0) return;
        if (level.get(id) === dd - 1) layerD.push(id);
      });
      for (var lj = 0; lj < layerD.length; lj++) {
        if (outNodes.size >= maxNodes) break;
        var u2 = layerD[lj];
        var nb2 = (succ.get(u2) || []).filter(function (id) {
          return allowedIds.has(id);
        });
        nb2.sort(function (a, b) {
          return scoreOf(b, pred, succ, commBoost, NODE_BY_ID) - scoreOf(a, pred, succ, commBoost, NODE_BY_ID);
        });
        var capD = capNeighbors(u2, nb2, 'down');
        for (var cj = 0; cj < capD.take.length; cj++) {
          if (outNodes.size >= maxNodes) break;
          var w = capD.take[cj];
          outNodes.add(w);
          level.set(w, Math.max(level.get(w) != null ? level.get(w) : -999, dd));
        }
        if (capD.overflow > 0 && capD.ovId && outNodes.size < maxNodes) {
          outNodes.add(capD.ovId);
          level.set(capD.ovId, dd);
          pseudoMeta.push({
            id: capD.ovId,
            parentId: u2,
            dir: 'down',
            count: capD.overflow,
            hiddenIds: nb2.filter(function (x) {
              return capD.take.indexOf(x) === -1;
            }),
          });
        }
      }
    }

    var upWalk = walkMainGreedy(focus, pred, NODE_BY_ID, pred, succ, commBoost);
    var dnWalk = walkMainGreedy(focus, succ, NODE_BY_ID, pred, succ, commBoost);
    var mainSet = new Set();
    mainSet.add(focus);
    upWalk.forEach(function (x) {
      mainSet.add(x);
    });
    dnWalk.forEach(function (x) {
      mainSet.add(x);
    });
    var mainPath = upWalk
      .slice()
      .reverse()
      .concat([focus])
      .concat(dnWalk);

    var edgeList = [];
    var edgeSeen = new Set();
    for (var ei = 0; ei < rawEdges.length; ei++) {
      var e = rawEdges[ei];
      if (!outNodes.has(e.from) || !outNodes.has(e.to)) continue;
      var ek = e.from + '=>' + e.to;
      if (edgeSeen.has(ek)) continue;
      edgeSeen.add(ek);
      edgeList.push(e);
    }

    function edgeMain(e) {
      return mainSet.has(e.from) && mainSet.has(e.to);
    }
    edgeList.sort(function (a, b) {
      var ma = edgeMain(a) ? 1 : 0;
      var mb = edgeMain(b) ? 1 : 0;
      if (mb !== ma) return mb - ma;
      return (b.width || 1) - (a.width || 1);
    });
    var hiddenEdgeCount = 0;
    if (edgeList.length > maxEdges) {
      hiddenEdgeCount = edgeList.length - maxEdges;
      edgeList = edgeList.slice(0, maxEdges);
    }

    var LEVEL_GAP = 118;
    var COL_GAP = 92;
    var levels = {};
    outNodes.forEach(function (nid) {
      var L = level.get(nid) != null ? level.get(nid) : 0;
      var k = String(L);
      if (!levels[k]) levels[k] = [];
      levels[k].push(nid);
    });
    Object.keys(levels).forEach(function (k) {
      levels[k].sort(function (a, b) {
        var ma = mainSet.has(a) ? 1 : 0;
        var mb = mainSet.has(b) ? 1 : 0;
        if (mb !== ma) return mb - ma;
        return (
          scoreOf(b, pred, succ, commBoost, NODE_BY_ID) - scoreOf(a, pred, succ, commBoost, NODE_BY_ID)
        );
      });
    });

    var pos = new Map();
    Object.keys(levels).forEach(function (k) {
      var arr = levels[k];
      var n = arr.length;
      var totalW = (n - 1) * COL_GAP;
      var startX = -totalW / 2;
      for (var ii = 0; ii < n; ii++) {
        var nid = arr[ii];
        var stagger = mainSet.has(nid) ? 0 : (ii % 2 === 0 ? -14 : 14);
        pos.set(nid, { x: startX + ii * COL_GAP, y: parseInt(k, 10) * LEVEL_GAP + stagger });
      }
    });

    function nodeToVisItem(raw, extra) {
      if (!raw) return null;
      var o2 = Object.assign(
        {
          id: raw.id,
          label: raw.label,
          color: raw.color,
          size: raw.size,
          font: raw.font,
          title: raw.title,
          _community: raw.community,
          _community_name: raw.community_name,
          _source_file: raw.source_file,
          _source_location: raw.source_location,
          _file_type: raw.file_type,
          _ui_type: raw.ui_type,
          _degree: raw.degree,
          norm_label: raw.norm_label,
        },
        extra || {}
      );
      return o2;
    }

    var visNodes = [];
    outNodes.forEach(function (nid) {
      var p = pos.get(nid) || { x: 0, y: 0 };
      if (String(nid).indexOf('__tree_ov__') === 0) {
        var pm = null;
        for (var pi = 0; pi < pseudoMeta.length; pi++) {
          if (pseudoMeta[pi].id === nid) pm = pseudoMeta[pi];
        }
        visNodes.push({
          id: nid,
          label: pm ? '还有 ' + pm.count + ' 个…' : '…',
          x: p.x,
          y: p.y,
          fixed: { x: true, y: true },
          shape: 'box',
          color: { background: '#1e293b', border: '#64748b', highlight: { background: '#334155', border: '#94a3b8' } },
          font: { color: '#cbd5e1', size: 11 },
          borderWidth: 2,
          _isTreeOverflow: true,
          _treeParent: pm && pm.parentId,
          _treeDir: pm && pm.dir,
        });
        return;
      }
      var raw = NODE_BY_ID.get(nid);
      if (!raw) return;
      var onMain = mainSet.has(nid);
      var Lv = level.get(nid) || 0;
      var dist = Math.abs(Lv);
      var op = Math.max(0.35, 1 - dist * 0.12);
      var sz = onMain ? Math.max(18, (raw.size || 12) * 1.15) : Math.max(10, (raw.size || 10) * 0.75);
      var bw = onMain ? 3 : 1.2;
      var fs = onMain ? Math.max(11, (raw.font && raw.font.size) || 0) : raw.font && raw.font.size;
      var font = raw.font ? Object.assign({}, raw.font, fs ? { size: fs } : {}) : { size: onMain ? 11 : 0, color: '#e2e8f0' };
      visNodes.push(
        nodeToVisItem(raw, {
          x: p.x,
          y: p.y,
          fixed: { x: true, y: true },
          size: sz,
          borderWidth: bw,
          opacity: op,
          font: font,
          _treeLevel: Lv,
          _treeOnMain: onMain,
        })
      );
    });

    var visEdges = [];
    var ei2 = 0;
    for (var ej = 0; ej < edgeList.length; ej++) {
      var ed = edgeList[ej];
      var mainE = mainSet.has(ed.from) && mainSet.has(ed.to);
      var ec = ed.color ? JSON.parse(JSON.stringify(ed.color)) : { color: '#8899aa', opacity: 0.55 };
      if (!mainE) {
        ec.opacity = (ec.opacity != null ? ec.opacity : 0.55) * 0.35;
      }
      visEdges.push({
        id: '__tree_e_' + ed.id + '_' + ei2++,
        from: ed.from,
        to: ed.to,
        label: '',
        title: ed.title,
        dashes: ed.dashes,
        width: mainE ? Math.max(2.5, (ed.width || 1) + 1.2) : Math.max(0.6, (ed.width || 1) * 0.65),
        color: ec,
        arrows: ed.arrows ? JSON.parse(JSON.stringify(ed.arrows)) : { to: { enabled: true, scaleFactor: 0.42 } },
      });
    }

    for (var pk = 0; pk < pseudoMeta.length; pk++) {
      var ov = pseudoMeta[pk];
      if (!outNodes.has(ov.id)) continue;
      if (ov.dir === 'up') {
        visEdges.push({
          id: '__tree_ov_e_' + ov.id,
          from: ov.id,
          to: ov.parentId,
          arrows: { to: { enabled: true, scaleFactor: 0.38 } },
          color: { color: '#64748b', opacity: 0.55 },
          width: 1,
          dashes: true,
          title: '折叠的上游',
        });
      } else {
        visEdges.push({
          id: '__tree_ov_e_' + ov.id,
          from: ov.parentId,
          to: ov.id,
          arrows: { to: { enabled: true, scaleFactor: 0.38 } },
          color: { color: '#64748b', opacity: 0.55 },
          width: 1,
          dashes: true,
          title: '折叠的下游',
        });
      }
    }

    var nodeMeta = {};
    var upTotal = (pred.get(focus) || []).length;
    var downTotal = (succ.get(focus) || []).length;
    var upShown = (pred.get(focus) || []).filter(function (id) {
      return outNodes.has(id) && String(id).indexOf('__tree_ov__') !== 0;
    }).length;
    var downShown = (succ.get(focus) || []).filter(function (id) {
      return outNodes.has(id) && String(id).indexOf('__tree_ov__') !== 0;
    }).length;
    outNodes.forEach(function (nid) {
      if (String(nid).indexOf('__tree_ov__') === 0) return;
      var L0 = level.get(nid) != null ? level.get(nid) : 0;
      var ut = (pred.get(nid) || []).length;
      var dt = (succ.get(nid) || []).length;
      var us = (pred.get(nid) || []).filter(function (x) {
        return outNodes.has(x);
      }).length;
      var ds = (succ.get(nid) || []).filter(function (x) {
        return outNodes.has(x);
      }).length;
      nodeMeta[nid] = {
        level: L0,
        upTotal: ut,
        downTotal: dt,
        upShown: us,
        downShown: ds,
        folded: hiddenEdgeCount > 0 || pseudoMeta.length > 0,
      };
    });
    nodeMeta[focus] = {
      level: 0,
      upTotal: upTotal,
      downTotal: downTotal,
      upShown: upShown,
      downShown: downShown,
      folded: hiddenEdgeCount > 0 || pseudoMeta.length > 0,
    };

    var realCount = 0;
    outNodes.forEach(function (n) {
      if (String(n).indexOf('__tree_ov__') !== 0) realCount++;
    });
    var hiddenNodeCount = Math.max(0, allowedIds.size - realCount);

    return {
      visNodes: visNodes,
      visEdges: visEdges,
      hiddenNodeCount: hiddenNodeCount,
      hiddenEdgeCount: hiddenEdgeCount,
      levels: levels,
      mainPath: mainPath,
      nodeMeta: nodeMeta,
      overflowNodes: pseudoMeta,
      focusNodeId: focus,
    };
  };
})(typeof window !== 'undefined' ? window : this);
