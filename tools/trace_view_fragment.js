/**
 * 链路追踪视图 — 依赖全局：RAW_NODES, RAW_EDGES, esc, aggregateMode, NODE_BY_ID, network
 */
(function traceViewInit() {
  var RAW_LINKS = RAW_EDGES.map(function (e) {
    return {
      source: e.from,
      target: e.to,
      relation: e.relation || 'relates_to',
      confidence: e.confidence || 'EXTRACTED',
      id: e.id,
    };
  });

  function computeDegreeMap(links) {
    var d = {};
    links.forEach(function (ev) {
      d[ev.source] = (d[ev.source] || 0) + 1;
      d[ev.target] = (d[ev.target] || 0) + 1;
    });
    return d;
  }

  var DEGREE_ALL = computeDegreeMap(RAW_LINKS);

  function filterCallsImports(links) {
    return links.filter(function (l) {
      return l.relation === 'calls' || l.relation === 'imports';
    });
  }

  function buildPredSucc(links) {
    var pred = new Map();
    var succ = new Map();
    function add(m, a, b) {
      if (!m.has(a)) m.set(a, []);
      if (m.get(a).indexOf(b) === -1) m.get(a).push(b);
    }
    links.forEach(function (e) {
      add(succ, e.source, e.target);
      add(pred, e.target, e.source);
    });
    return { pred: pred, succ: succ };
  }

  function findLink(links, from, to) {
    for (var i = 0; i < links.length; i++) {
      var e = links[i];
      if (e.source === from && e.target === to) return e;
    }
    return null;
  }

  /**
   * dir: 'up' = 沿反方向找 pred（谁指向我）; 'down' = succ
   */
  function exploreDirection(focus, links, dir, maxDepth, expandedOv) {
    expandedOv = expandedOv || new Set();
    var ps = buildPredSucc(links);
    var getNb =
      dir === 'up'
        ? function (id) {
            return ps.pred.get(id) || [];
          }
        : function (id) {
            return ps.succ.get(id) || [];
          };

    var visited = new Set();
    visited.add(focus);
    var nodesSeen = new Set();
    nodesSeen.add(focus);
    var edgesOut = [];
    var depths = {};
    depths[focus] = 0;
    var cycles = [];
    var overflows = [];

    var queue = [{ id: focus, depth: 0 }];

    while (queue.length) {
      var cur = queue.shift();
      var u = cur.id;
      var depth = cur.depth;
      if (depth >= maxDepth) continue;

      var rawNb = getNb(u);
      var nb = [];
      for (var i = 0; i < rawNb.length; i++) {
        if (nb.indexOf(rawNb[i]) === -1) nb.push(rawNb[i]);
      }

      var ovId = '__overflow_' + u + '_' + dir;
      if (nb.length > 15) {
        nb.sort(function (a, b) {
          return (DEGREE_ALL[b] || 0) - (DEGREE_ALL[a] || 0);
        });
        var hidden = nb.slice(10);
        nb = nb.slice(0, 10);
        if (hidden.length && !expandedOv.has(ovId)) {
          overflows.push({
            id: ovId,
            parentId: u,
            dir: dir,
            hiddenIds: hidden,
            count: hidden.length,
          });
          nb.push(ovId);
        } else if (expandedOv.has(ovId)) {
          nb = nb.concat(hidden);
        }
      }

      for (var j = 0; j < nb.length; j++) {
        var v = nb[j];
        if (String(v).indexOf('__overflow_') === 0) {
          nodesSeen.add(v);
          depths[v] = depth + 1;
          continue;
        }

        var lk =
          dir === 'up' ? findLink(links, v, u) : findLink(links, u, v);
        if (!lk) continue;

        if (visited.has(v)) {
          cycles.push({ from: dir === 'up' ? v : u, to: dir === 'up' ? u : v, link: lk });
          continue;
        }
        visited.add(v);
        nodesSeen.add(v);
        depths[v] = depth + 1;
        edgesOut.push(lk);
        queue.push({ id: v, depth: depth + 1 });
      }
    }

    return {
      nodes: nodesSeen,
      edges: edgesOut,
      depths: depths,
      cycles: cycles,
      overflows: overflows,
    };
  }

  function walkMainPath(focus, links, which) {
    var ps = buildPredSucc(links);
    var path = [];
    var cur = focus;
    for (var step = 0; step < 5; step++) {
      var nb =
        which === 'up'
          ? ps.pred.get(cur) || []
          : ps.succ.get(cur) || [];
      nb = nb.filter(function (x) {
        return String(x).indexOf('__') !== 0;
      });
      if (!nb.length) break;
      var best = nb[0];
      for (var i = 1; i < nb.length; i++) {
        if ((DEGREE_ALL[nb[i]] || 0) > (DEGREE_ALL[best] || 0)) best = nb[i];
      }
      path.push(best);
      cur = best;
    }
    return path;
  }

  window.computePathTrace = function (nodes, links, clickedNodeId, expandedOv) {
    expandedOv = expandedOv || new Set();
    var nodeById = new Map(nodes.map(function (n) {
      return [n.id, n];
    }));
    if (!nodeById.has(clickedNodeId)) {
      return {
        focusNodeId: clickedNodeId,
        upstreamNodes: [],
        downstreamNodes: [],
        upstreamLinks: [],
        downstreamLinks: [],
        mainPathNodeIds: [],
        overflowNodes: [],
        cycles: [],
        isolated: true,
        relaxed: false,
      };
    }

    var tryLinks = filterCallsImports(links);
    function reachableCount(tl) {
      var ps = buildPredSucc(tl);
      var up = exploreDirection(clickedNodeId, tl, 'up', 5, new Set()).nodes;
      var dn = exploreDirection(clickedNodeId, tl, 'down', 5, new Set()).nodes;
      var s = new Set();
      up.forEach(function (x) {
        s.add(x);
      });
      dn.forEach(function (x) {
        s.add(x);
      });
      return s.size;
    }

    var relaxed = false;
    if (reachableCount(tryLinks) < 3) {
      tryLinks = links.slice();
      relaxed = true;
    }

    var upR = exploreDirection(clickedNodeId, tryLinks, 'up', 5, expandedOv);
    var dnR = exploreDirection(clickedNodeId, tryLinks, 'down', 5, expandedOv);

    var upWalk = walkMainPath(clickedNodeId, tryLinks, 'up');
    var dnWalk = walkMainPath(clickedNodeId, tryLinks, 'down');
    var leftPart = upWalk.slice().reverse();
    var mainPathNodeIds = leftPart.concat([clickedNodeId]).concat(dnWalk);
    var mainSet = new Set(mainPathNodeIds);

    var allCycles = upR.cycles.concat(dnR.cycles);
    var allOverflow = upR.overflows.concat(dnR.overflows);

    var incident = tryLinks.some(function (e) {
      return e.source === clickedNodeId || e.target === clickedNodeId;
    });
    var isolated = !incident;

    return {
      focusNodeId: clickedNodeId,
      upstreamNodes: Array.from(upR.nodes),
      downstreamNodes: Array.from(dnR.nodes),
      upstreamLinks: upR.edges,
      downstreamLinks: dnR.edges,
      mainPathNodeIds: mainPathNodeIds,
      overflowNodes: allOverflow,
      cycles: allCycles,
      isolated: isolated,
      relaxed: relaxed,
      depthMap: mergeDepths(upR.depths, dnR.depths, clickedNodeId),
      allLinks: tryLinks,
      mainSet: mainSet,
    };
  };

  function mergeDepths(du, dd, focus) {
    var o = {};
    Object.keys(du).forEach(function (k) {
      if (k === focus) o[k] = { d: 0, side: 'focus' };
      else o[k] = { d: du[k], side: 'up' };
    });
    Object.keys(dd).forEach(function (k) {
      if (k === focus) o[k] = { d: 0, side: 'focus' };
      else if (!o[k]) o[k] = { d: dd[k], side: 'down' };
    });
    return o;
  }

  var networkTrace = null;
  var traceResizeObserver = null;
  var traceFocusId = null;
  var traceExpandedOverflow = new Set();
  var lastTraceEnterId = null;
  /** Suppress duplicate open when click-timing and doubleClick both fire */
  var _traceLastOpenTs = 0;
  var _traceClickTs = 0;
  var _traceClickNid = null;
  var COL_W = 260;
  var ROW_H = 90;

  function syncVmTraceButton() {
    var btnT = document.getElementById('vm-trace');
    if (!btnT) return;
    var sel = network.getSelectedNodes();
    var hasSel = sel && sel.length > 0;
    btnT.disabled = !hasSel && !lastTraceEnterId;
  }

  /** Resolve focused node for global graph events (doubleClick sometimes omits nodes[]) */
  function resolveGlobalTraceNodeId(params) {
    if (params.nodes && params.nodes.length) return params.nodes[0];
    var sel = network.getSelectedNodes();
    if (sel && sel.length) return sel[0];
    if (params.pointer && params.pointer.DOM && typeof network.getNodeAt === 'function') {
      try {
        var at = network.getNodeAt(params.pointer.DOM);
        if (at) return at;
      } catch (e0) {}
    }
    return null;
  }

  function openTraceFromGlobal(nodeId) {
    if (!nodeId) {
      return;
    }
    var now = Date.now();
    if (now - _traceLastOpenTs < 280) {
      return;
    }
    _traceLastOpenTs = now;
    traceExpandedOverflow = new Set();
    window.enterTraceView(nodeId, false);
    window.setViewMode('trace');
  }

  function layerOpacity(layer) {
    var m = { 1: 1.0, 2: 0.85, 3: 0.7, 4: 0.55, 5: 0.4 };
    return m[layer] != null ? m[layer] : 0.35;
  }

  function buildTraceVisData(trace, focusId) {
    var nodeIds = new Set();
    trace.upstreamNodes.forEach(function (x) {
      nodeIds.add(x);
    });
    trace.downstreamNodes.forEach(function (x) {
      nodeIds.add(x);
    });
    (trace.overflowNodes || []).forEach(function (o) {
      nodeIds.add(o.id);
    });

    var dm = trace.depthMap || {};

    function colOf(id) {
      if (id === focusId) return 0;
      var inf = dm[id];
      if (!inf) return 0;
      if (inf.side === 'focus') return 0;
      if (inf.side === 'up') return -inf.d;
      if (inf.side === 'down') return inf.d;
      return 0;
    }

    function layerOf(id) {
      if (id === focusId) return 1;
      var inf = dm[id];
      if (!inf) return 3;
      return Math.min(5, Math.max(1, inf.d));
    }

    var branchKey = {};
    var nodesArr = [];

    var ids = Array.from(nodeIds);
    ids.sort();

    for (var ii = 0; ii < ids.length; ii++) {
      var nid = ids[ii];
      var col = colOf(nid);
      var onMain = trace.mainSet && trace.mainSet.has(nid);
      var row = 0;
      if (nid !== focusId && !String(nid).startsWith('__')) {
        if (!onMain) {
          var ky = col + '_' + (col < 0 ? 'u' : 'd');
          branchKey[ky] = (branchKey[ky] || 0) + 1;
          var bi = branchKey[ky];
          row = col < 0 ? -((bi % 4) + 1) * 28 : ((bi % 4) + 1) * 28;
        }
      }

      var x = col * COL_W;
      var y = row;
      var L = layerOf(nid);
      var op = layerOpacity(L);
      var isMain = trace.mainSet && trace.mainSet.has(nid);
      var isFocus = nid === focusId;
      var size = isFocus ? 26 : isMain ? 22 : 14;
      var borderW = isFocus ? 4 : isMain ? 3 : 1.5;

      if (String(nid).indexOf('__overflow_') === 0) {
        nodesArr.push({
          id: nid,
          label: '还有 N 个…',
          x: x,
          y: y,
          fixed: { x: true, y: true },
          shape: 'box',
          color: {
            background: '#1e293b',
            border: '#64748b',
            highlight: { background: '#334155', border: '#94a3b8' },
          },
          borderWidth: 2,
          dashes: [4, 4],
          font: { color: '#cbd5e1', size: 11 },
          opacity: 0.95,
        });
        continue;
      }
      var raw = NODE_BY_ID.get(nid);
      var lab = raw ? raw.label : nid;
      var tt = [String(lab), raw && raw.file_type, raw && raw.source_file, raw != null && raw.source_location != null ? String(raw.source_location) : '']
        .filter(function (x) {
          return x;
        })
        .join('\n');

      nodesArr.push({
        id: nid,
        label: lab,
        title: tt,
        x: x,
        y: y,
        fixed: { x: true, y: true },
        shape: 'dot',
        size: size,
        borderWidth: borderW,
        color: isFocus
          ? {
              background: '#fbbf24',
              border: '#ea580c',
              highlight: { background: '#fcd34d', border: '#c2410c' },
            }
          : {
              background: isMain ? '#0ea5e9' : '#475569',
              border: isMain ? '#0284c7' : '#334155',
              highlight: { background: '#fff', border: '#0ea5e9' },
            },
        font: { color: '#f8fafc', size: isMain ? 12 : 10 },
        opacity: op,
      });
    }

    if (trace.isolated) {
      var rf = NODE_BY_ID.get(focusId);
      nodesArr = [
        {
          id: focusId,
          label: rf ? rf.label : focusId,
          title: rf ? [rf.label, rf.file_type, rf.source_file].filter(Boolean).join('\n') : '',
          x: 0,
          y: 0,
          fixed: { x: true, y: true },
          shape: 'dot',
          size: 30,
          borderWidth: 4,
          color: {
            background: '#fbbf24',
            border: '#ea580c',
            highlight: { background: '#fcd34d', border: '#c2410c' },
          },
          font: { color: '#0f172a', size: 13 },
        },
      ];
    }

    var cyclePair = new Set();
    trace.cycles.forEach(function (c) {
      cyclePair.add(c.link.source + '=>' + c.link.target);
    });

    var edgeArr = [];
    var seenK = new Set();

    function pushEdge(lk, isMainE, forceCycle) {
      var k = lk.source + '=>' + lk.target;
      if (seenK.has(k)) return;
      seenK.add(k);
      var cyc = forceCycle || cyclePair.has(k);
      edgeArr.push({
        id: 'te_' + lk.id,
        from: lk.source,
        to: lk.target,
        arrows: { to: { enabled: true, scaleFactor: 0.45 } },
        color: cyc
          ? { color: '#ef4444', opacity: 0.95 }
          : {
              color: isMainE ? '#38bdf8' : '#94a3b8',
              opacity: isMainE ? 0.92 : 0.5,
            },
        width: cyc ? 2 : isMainE ? 4 : 1.5,
        dashes: cyc,
        title: cyc
          ? esc(String(lk.relation || '')) + ' · 循环依赖'
          : esc(String(lk.relation || '')) +
            ' · ' +
            esc(String(lk.confidence || '')),
      });
    }

    trace.upstreamLinks.forEach(function (lk) {
      var mainE =
        trace.mainSet &&
        trace.mainSet.has(lk.source) &&
        trace.mainSet.has(lk.target);
      pushEdge(lk, mainE, false);
    });
    trace.downstreamLinks.forEach(function (lk) {
      var mainE =
        trace.mainSet &&
        trace.mainSet.has(lk.source) &&
        trace.mainSet.has(lk.target);
      pushEdge(lk, mainE, false);
    });

    trace.cycles.forEach(function (c) {
      if (c.link) pushEdge(c.link, false, true);
    });

    (trace.overflowNodes || []).forEach(function (ov) {
      var anchor = ov.parentId;
      var oid = ov.id;
      if (!nodeIds.has(anchor) || !nodeIds.has(oid)) return;
      var fromN = ov.dir === 'up' ? oid : anchor;
      var toN = ov.dir === 'up' ? anchor : oid;
      edgeArr.push({
        id: 'ov_' + oid,
        from: fromN,
        to: toN,
        arrows: { to: { enabled: ov.dir !== 'up', scaleFactor: 0.35 } },
        color: { color: '#64748b', opacity: 0.65 },
        width: 1,
        dashes: true,
        title: ov.dir === 'up' ? '折叠的上游邻居' : '折叠的下游邻居',
      });
    });

    return { nodes: nodesArr, edges: edgeArr };
  }

  function updateTraceFocusPanel(focusId) {
    var el = document.getElementById('trace-focus-info');
    if (!el) return;
    var raw = NODE_BY_ID.get(focusId);
    if (!raw) {
      el.innerHTML = '';
      return;
    }
    el.innerHTML =
      '<div class="field"><b>' +
      esc(raw.label) +
      '</b></div>' +
      '<div class="field">类型: ' +
      esc(raw.file_type || '') +
      '</div>' +
      '<div class="field">文件: ' +
      esc(raw.source_file || '') +
      '</div>';
  }

  window.enterTraceView = function (nodeId, smooth) {
    traceFocusId = nodeId;
    lastTraceEnterId = nodeId;
    var tr = computePathTrace(RAW_NODES, RAW_LINKS, nodeId, traceExpandedOverflow);
    /** 必须用独立变量名，勿用 `vis`，否则会遮蔽 window.vis（vis-network 全局命名空间） */
    var traceVisData = buildTraceVisData(tr, nodeId);
    (tr.overflowNodes || []).forEach(function (o) {
      if (String(o.id).indexOf('__overflow_') === 0) {
        for (var j = 0; j < traceVisData.nodes.length; j++) {
          if (traceVisData.nodes[j].id === o.id) {
            traceVisData.nodes[j].label = '还有 ' + o.count + ' 个…';
          }
        }
      }
    });

    var container = document.getElementById('graph-trace');
    if (!container) {
      return;
    }

    var gg = document.getElementById('graph-global');
    var gw = document.getElementById('graph-trace-wrap');
    if (gg) gg.style.display = 'none';
    if (gw) gw.style.display = 'flex';
    /** 从 display:none 切到可见后，同一 tick 内 clientWidth/height 常为 0，Vis 库会建 0×0 画布 → 空白 */
    if (gw) void gw.offsetHeight;
    void container.offsetHeight;

    if (networkTrace) {
      networkTrace.destroy();
      networkTrace = null;
    }
    if (traceResizeObserver) {
      try {
        traceResizeObserver.disconnect();
      } catch (eRo) {}
      traceResizeObserver = null;
    }

    function mountTraceNetwork(retries) {
      retries = retries || 0;
      var w = container.clientWidth;
      var h = container.clientHeight;
      if ((w < 2 || h < 2) && retries < 120) {
        requestAnimationFrame(function () {
          mountTraceNetwork(retries + 1);
        });
        return;
      }

      var visNs = typeof window !== 'undefined' ? window.vis : undefined;
      if (typeof visNs === 'undefined' || typeof visNs.Network !== 'function') {
        return;
      }

      try {
        networkTrace = new visNs.Network(
          container,
          {
            nodes: new visNs.DataSet(traceVisData.nodes),
            edges: new visNs.DataSet(traceVisData.edges),
          },
          {
            autoResize: true,
            physics: false,
            layout: {
              hierarchical: {
                enabled: false,
              },
            },
            interaction: {
              hover: true,
              tooltipDelay: 80,
              zoomView: true,
              dragView: true,
              dragNodes: false,
            },
            edges: {
              smooth: { type: 'cubicBezier', roundness: 0.25 },
            },
          }
        );
      } catch (eNet) {
        return;
      }

      networkTrace.on('doubleClick', function (p) {
        if (!p.nodes.length) return;
        var nid = p.nodes[0];
        if (String(nid).indexOf('__overflow_') === 0) {
          traceExpandedOverflow.add(nid);
          window.enterTraceView(traceFocusId, true);
          return;
        }
        traceExpandedOverflow = new Set();
        window.enterTraceView(nid, true);
      });

      function fitTraceView() {
        if (!networkTrace) return;
        try {
          networkTrace.fit({
            animation: smooth
              ? { duration: 380, easingFunction: 'easeInOutQuad' }
              : false,
          });
          networkTrace.redraw();
        } catch (e1) {}
      }

      setTimeout(fitTraceView, 40);

      if (typeof ResizeObserver !== 'undefined') {
        traceResizeObserver = new ResizeObserver(function () {
          if (!networkTrace || container.clientWidth < 2 || container.clientHeight < 2) return;
          try {
            traceResizeObserver.disconnect();
          } catch (eRo2) {}
          traceResizeObserver = null;
          fitTraceView();
        });
        traceResizeObserver.observe(container);
      }
    }

    requestAnimationFrame(function () {
      mountTraceNetwork(0);
    });

    updateTraceFocusPanel(nodeId);

    var iso = document.getElementById('trace-isolated-hint');
    if (iso) iso.style.display = tr.isolated ? 'block' : 'none';

    var btnTr = document.getElementById('vm-trace');
    if (btnTr) {
      btnTr.disabled = false;
      btnTr.classList.add('vm-active');
    }
    var btnG = document.getElementById('vm-global');
    if (btnG) btnG.classList.remove('vm-active');
    syncVmTraceButton();
  };

  window.setViewMode = function (mode) {
    var gg = document.getElementById('graph-global');
    var gw = document.getElementById('graph-trace-wrap');
    var btnG = document.getElementById('vm-global');
    var btnT = document.getElementById('vm-trace');
    if (mode === 'trace') {
      if (!lastTraceEnterId) return;
      if (gg) gg.style.display = 'none';
      if (gw) gw.style.display = 'flex';
      if (btnG) btnG.classList.remove('vm-active');
      if (btnT) {
        btnT.disabled = false;
        btnT.classList.add('vm-active');
      }
    } else {
      if (gg) gg.style.display = 'block';
      if (gw) gw.style.display = 'none';
      if (btnG) btnG.classList.add('vm-active');
      if (btnT) btnT.classList.remove('vm-active');
      if (lastTraceEnterId && typeof applySelectionHighlight === 'function') {
        applySelectionHighlight(lastTraceEnterId);
        if (typeof showInfo === 'function') showInfo(lastTraceEnterId);
      }
      syncVmTraceButton();
    }
  };

  network.on('click', function (params) {
    if (typeof aggregateMode !== 'undefined' && aggregateMode) return;
    syncVmTraceButton();
    var nid = resolveGlobalTraceNodeId(params);
    var now = Date.now();
    if (nid && _traceClickNid === nid && now - _traceClickTs < 480) {
      if (
        typeof document !== 'undefined' &&
        document.getElementById('cb-hierarchical') &&
        document.getElementById('cb-hierarchical').checked
      ) {
        _traceClickTs = 0;
        _traceClickNid = null;
        return;
      }
      openTraceFromGlobal(nid);
      _traceClickTs = 0;
      _traceClickNid = null;
      return;
    }
    _traceClickTs = now;
    _traceClickNid = nid;
  });

  network.on('doubleClick', function (params) {
    if (
      typeof document !== 'undefined' &&
      document.getElementById('cb-hierarchical') &&
      document.getElementById('cb-hierarchical').checked
    ) {
      return;
    }
    if (typeof aggregateMode !== 'undefined' && aggregateMode) return;
    var nid = resolveGlobalTraceNodeId(params);
    if (!nid) {
      return;
    }
    openTraceFromGlobal(nid);
  });

  var btnBack = document.getElementById('trace-back-btn');
  if (btnBack)
    btnBack.addEventListener('click', function () {
      setViewMode('global');
    });

  var vmG = document.getElementById('vm-global');
  var vmT = document.getElementById('vm-trace');
  if (vmG)
    vmG.addEventListener('click', function () {
      setViewMode('global');
    });
  if (vmT)
    vmT.addEventListener('click', function () {
      if (vmT.disabled) return;
      var sel = network.getSelectedNodes();
      var id = sel && sel.length ? sel[0] : lastTraceEnterId;
      if (!id) return;
      traceExpandedOverflow = new Set();
      window.enterTraceView(id, false);
      window.setViewMode('trace');
    });

  if (vmG) vmG.classList.add('vm-active');
  syncVmTraceButton();
})();
