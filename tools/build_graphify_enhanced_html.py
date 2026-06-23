#!/usr/bin/env python3
"""
从 graphify-out/graph.json 生成增强版 graph.html（内嵌 JSON，可直接 file:// 打开）。
同目录会复制 vis-network.min.js（来自 tools/third_party/vis-network.min.js），避免仅依赖 CDN 导致 vis 未加载。

功能：社区着色、度数缩放、滚轮缩放/拖拽画布/拖拽节点、节点详情（路径/位置/邻居）、
顶部按函数名/文件名搜索、代码/文档/概念类型筛选、选中时邻边高亮与其余节点变暗。

用法（在 graphify extract 或 /graphify 生成 graph.json 之后）：
  python tools/build_graphify_enhanced_html.py
  python tools/build_graphify_enhanced_html.py --graph graphify-out/graph.json --out graphify-out/graph.html

搜索：不隐藏其余节点，仅在类型/社区筛选范围内将「文本命中 ∪ 一跳邻居」高亮，其余变淡。
「显示标签」开关：关则仅保留高度数节点等少量标签（性能优先）；开则按可见子图度数阈值 + 搜索高亮子图显示更多标签。
「社区聚合」：概览为社区 meta 节点与跨社区边；点击某一社区即退出聚合并仅保留该社区成员全图。
「分层布局」：vis-network 自上而下树状分层（沿有向边 directed）；关闭则恢复力导向。
缩放/拖拽时不隐藏边（hideEdgesOnZoom / hideEdgesOnDrag 关闭）。
力导向默认参数已偏「散开」：较强斥力、较长弹簧、较高 avoidOverlap、稳定迭代略增（与关闭「分层布局」时一致）。
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path

COMMUNITY_COLORS = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
]

# graphify validate.VALID_FILE_TYPES 的子集 → UI「代码 / 文档 / 概念」
DOC_TYPES = frozenset({"document", "paper", "image"})
CODE_TYPES = frozenset({"code", "rationale"})


def _js_safe(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def _norm_type(ft: str | None) -> str:
    t = (ft or "concept").lower().strip()
    if t in CODE_TYPES:
        return "code"
    if t in DOC_TYPES:
        return "doc"
    return "concept"


def build_vis_payload(graph: dict) -> tuple[list[dict], list[dict], list[dict]]:
    nodes_raw = graph.get("nodes") or []
    links = graph.get("links") or graph.get("edges") or []

    degree: dict[str, int] = {}
    for e in links:
        s, t = e.get("source"), e.get("target")
        if not s or not t:
            continue
        degree[s] = degree.get(s, 0) + 1
        degree[t] = degree.get(t, 0) + 1
    max_deg = max(degree.values(), default=1) or 1

    comm_counts: dict[int, int] = {}
    for n in nodes_raw:
        cid = n.get("community")
        if cid is None:
            cid = 0
        comm_counts[cid] = comm_counts.get(cid, 0) + 1

    vis_nodes: list[dict] = []
    for n in nodes_raw:
        nid = n["id"]
        cid = int(n.get("community") or 0)
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        label = str(n.get("label") or nid)
        deg = degree.get(nid, 0)
        size = 10 + 32 * (deg / max_deg)
        # 仅高连接节点显示标签，减少文字绘制量
        font_size = 11 if deg >= max_deg * 0.18 else 0
        ui_type = _norm_type(n.get("file_type"))
        vis_nodes.append({
            "id": nid,
            "label": label,
            "color": {"background": color, "border": color, "highlight": {"background": "#ffffff", "border": color}},
            "size": round(size, 1),
            "font": {"size": font_size, "color": "#ffffff"},
            "title": html_mod.escape(label),
            "community": cid,
            "community_name": f"Community {cid}",
            "source_file": str(n.get("source_file") or ""),
            "norm_label": str(n.get("norm_label") or ""),
            "source_location": n.get("source_location"),
            "file_type": n.get("file_type") or "",
            "ui_type": ui_type,
            "degree": deg,
        })

    vis_edges: list[dict] = []
    for i, e in enumerate(links):
        u, v = e.get("source"), e.get("target")
        if u is None or v is None:
            continue
        true_src = e.get("_src", u)
        true_tgt = e.get("_tgt", v)
        confidence = e.get("confidence", "EXTRACTED")
        relation = e.get("relation", "")
        rel = (relation or "").strip() or "relates_to"
        # 不在边上绘制文字标签（Canvas 性能）；关系在悬停 title、详情面板与邻居列表中展示
        vis_edges.append({
            "id": i,
            "from": true_src,
            "to": true_tgt,
            "label": "",
            "title": html_mod.escape(f"{rel} [{confidence}]"),
            "dashes": confidence != "EXTRACTED",
            "width": 2 if confidence == "EXTRACTED" else 1,
            "color": {"color": "#8899aa", "opacity": 0.55, "highlight": "#7dd3fc"},
            "confidence": confidence,
            "relation": rel,
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.42}},
        })

    legend = []
    for cid in sorted(comm_counts.keys()):
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        legend.append({"cid": cid, "color": color, "label": f"Community {cid}", "count": comm_counts[cid]})

    return vis_nodes, vis_edges, legend


def build_meta_graph(
    vis_nodes: list[dict], vis_edges: list[dict], legend: list[dict]
) -> tuple[list[dict], list[dict]]:
    """社区层次：每个社区一个 meta 节点；跨社区边聚合为权重边（无箭头）。"""
    nid_to_c = {n["id"]: int(n["community"]) for n in vis_nodes}
    counts = {int(e["cid"]): int(e["count"]) for e in legend}
    max_cnt = max(counts.values(), default=1) or 1

    meta_nodes: list[dict] = []
    for entry in legend:
        cid = int(entry["cid"])
        color = entry["color"]
        lbl = entry["label"]
        cnt = int(entry["count"])
        sz = 14 + 34 * math.sqrt(cnt / max_cnt)
        meta_nodes.append({
            "id": f"__meta_{cid}",
            "cid": cid,
            "label": f"{lbl} ({cnt})",
            "color": {
                "background": color,
                "border": color,
                "highlight": {"background": "#ffffff", "border": color},
            },
            "size": round(sz, 1),
            "font": {"size": 13, "color": "#ffffff"},
            "title": html_mod.escape(f"{lbl} · {cnt} 个节点 · 点击展开该社区"),
        })

    pair_w: dict[tuple[int, int], int] = defaultdict(int)
    for e in vis_edges:
        c1 = nid_to_c.get(e["from"])
        c2 = nid_to_c.get(e["to"])
        if c1 is None or c2 is None or c1 == c2:
            continue
        a, b = (c1, c2) if c1 < c2 else (c2, c1)
        pair_w[(a, b)] += 1

    meta_edges: list[dict] = []
    for idx, ((a, b), w) in enumerate(sorted(pair_w.items())):
        meta_edges.append({
            "id": f"m_{a}_{b}_{idx}",
            "from": f"__meta_{a}",
            "to": f"__meta_{b}",
            "label": "",
            "title": html_mod.escape(f"{w} 条跨社区边"),
            "width": min(10.0, 1.2 + math.log(1 + w)),
            "color": {"color": "#94a3b8", "opacity": 0.72},
            "arrows": {"to": {"enabled": False}},
            "dashes": False,
        })

    return meta_nodes, meta_edges


def render_html(
    vis_nodes: list,
    vis_edges: list,
    legend: list,
    meta_nodes: list[dict],
    meta_edges: list[dict],
    stats: str,
    trace_fragment: str,
    tree_fragment: str,
) -> str:
    nodes_json = _js_safe(vis_nodes)
    edges_json = _js_safe(vis_edges)
    legend_json = _js_safe(legend)
    meta_nodes_json = _js_safe(meta_nodes)
    meta_edges_json = _js_safe(meta_edges)

    script_head = f"""
const RAW_NODES = {nodes_json};
const RAW_EDGES = {edges_json};
const LEGEND = {legend_json};
const META_NODES_RAW = {meta_nodes_json};
const META_EDGES_RAW = {meta_edges_json};
const NODE_BY_ID = new Map(RAW_NODES.map(n => [n.id, n]));
"""
    script = script_head + tree_fragment + f"""

let aggregateMode = false;
let _suppressAggCheckbox = false;
let _suppressHierCheckbox = false;
let _hierLayoutDebounce = null;
let readableTreeMode = false;
const treeExpandedOverflow = new Set();
let _treeLayoutCacheKey = '';
let _treeLayoutCacheRes = null;

function esc(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}}

/** 无向扩展用：任一端指向另一端即可遍历邻居 */
const ADJ = new Map();
RAW_EDGES.forEach(e => {{
  const add = (a, b) => {{
    if (!ADJ.has(a)) ADJ.set(a, []);
    ADJ.get(a).push(b);
  }};
  add(e.from, e.to);
  add(e.to, e.from);
}});

/** 从 fromId 看向 toId 的关系文案（沿存储的有向 from→to）；反向边则标注「反向」 */
function relationBetween(fromId, toId) {{
  const found = [];
  RAW_EDGES.forEach(e => {{
    if (e.from === fromId && e.to === toId) found.push(String(e.relation || 'relates_to'));
    else if (e.from === toId && e.to === fromId) found.push(String(e.relation || 'relates_to') + ' ⟵');
  }});
  return found.length ? [...new Set(found)].join(' · ') : '';
}}

function nodeToDatasetItem(n) {{
  return {{
    id: n.id, label: n.label, color: n.color, size: n.size,
    font: n.font, title: n.title,
    _community: n.community, _community_name: n.community_name,
    _source_file: n.source_file, _source_location: n.source_location,
    _file_type: n.file_type, _ui_type: n.ui_type, _degree: n.degree,
    norm_label: n.norm_label,
  }};
}}

function metaToDatasetItem(m) {{
  return {{
    id: m.id,
    label: m.label,
    color: m.color,
    size: m.size,
    font: m.font,
    title: m.title,
    _isMeta: true,
    _cid: m.cid,
  }};
}}

const nodesDS = new vis.DataSet(RAW_NODES.map(nodeToDatasetItem));

const edgesDS = new vis.DataSet(RAW_EDGES);

const container = document.getElementById('graph-global');
const network = new vis.Network(container, {{ nodes: nodesDS, edges: edgesDS }}, {{
  autoResize: true,
  clickToUse: false,
  physics: {{
    enabled: true,
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {{
      gravitationalConstant: -95,
      centralGravity: 0.004,
      springLength: 155,
      springConstant: 0.072,
      damping: 0.52,
      avoidOverlap: 0.82,
    }},
    maxVelocity: 36,
    minVelocity: 0.65,
    timestep: 0.38,
    stabilization: {{ iterations: 130, fit: true, updateInterval: 50 }},
  }},
  interaction: {{
    hover: true,
    hoverConnectedEdges: false,
    selectConnectedEdges: false,
    tooltipDelay: 220,
    hideEdgesOnDrag: false,
    hideEdgesOnZoom: false,
    navigationButtons: false,
    keyboard: false,
    multiselect: false,
    dragNodes: true,
    dragView: true,
    zoomView: true,
    zoomSpeed: 1.02,
  }},
  layout: {{ improvedLayout: true, randomSeed: 42 }},
  nodes: {{ shape: 'dot', borderWidth: 1 }},
  edges: {{
    smooth: false,
    selectionWidth: 3,
    font: {{ size: 0, strokeWidth: 0 }},
    arrows: {{ to: {{ enabled: true, scaleFactor: 0.42 }} }},
  }},
}});

network.once('stabilizationIterationsDone', () => {{
  network.setOptions({{ physics: {{ enabled: false }} }});
  try {{ network.storePositions(); }} catch (e) {{}}
  applyLabelPolicy();
}});

const BASE_FONT = new Map();
RAW_NODES.forEach(n => BASE_FONT.set(n.id, JSON.parse(JSON.stringify(n.font || {{ size: 0, color: '#ffffff' }}))));

const BASE_NODE = new Map();
RAW_NODES.forEach(n => BASE_NODE.set(n.id, JSON.parse(JSON.stringify(n.color))));

const BASE_EDGE = new Map();
RAW_EDGES.forEach(e => BASE_EDGE.set(e.id, {{
  color: JSON.parse(JSON.stringify(e.color)),
  width: e.width,
  arrows: e.arrows ? JSON.parse(JSON.stringify(e.arrows)) : {{ to: {{ enabled: true, scaleFactor: 0.42 }} }}
}}));

function fmtLoc(loc) {{
  if (loc == null || loc === '') return '-';
  if (typeof loc === 'number') return '行 ' + loc;
  if (typeof loc === 'object') return esc(JSON.stringify(loc));
  return esc(String(loc));
}}

function showInfo(nodeId) {{
  const n = nodesDS.get(nodeId);
  if (!n) return;
  if (n._isMeta) {{
    document.getElementById('info-content').innerHTML = `
      <div class="field"><b>${{esc(n.label)}}</b></div>
      <div class="field dim">社区聚合节点 · 点击该节点展开此社区的成员与标签</div>`;
    return;
  }}
  const neighborIds = network.getConnectedNodes(nodeId).filter(nid => {{
    const nd = nodesDS.get(nid);
    return nd && nd.hidden !== true;
  }});
  const neighborItems = neighborIds.map(nid => {{
    const nb = nodesDS.get(nid);
    const c = nb && nb.color ? nb.color.background : '#555';
    const rel = relationBetween(nodeId, nid);
    const relHtml = rel ? `<span class="rel-tag">${{esc(rel)}}</span>` : '';
    return `<div class="neighbor-row"><span class="neighbor-link" style="border-left-color:${{esc(c)}}" data-nid="${{esc(nid)}}">${{esc(nb ? nb.label : nid)}}</span>${{relHtml}}</div>`;
  }}).join('');
  let treeBlock = '';
  if (readableTreeMode && window.__lastReadableTreeMeta) {{
    const R = window.__lastReadableTreeMeta;
    const tm = R.nodeMeta && R.nodeMeta[nodeId];
    if (tm) {{
      treeBlock += `<div class="field dim">树状子图 · 层级 ${{tm.level}} · 上游展示/总数 ${{tm.upShown}}/${{tm.upTotal}} · 下游展示/总数 ${{tm.downShown}}/${{tm.downTotal}}</div>`;
    }}
    if (R.hiddenNodeCount || R.hiddenEdgeCount) {{
      treeBlock += `<div class="field dim">相对全图：约隐藏 ${{R.hiddenNodeCount}} 节点 · ${{R.hiddenEdgeCount}} 条边未入子图</div>`;
    }}
    if (R.overflowNodes && R.overflowNodes.length) {{
      treeBlock += `<div class="field dim">存在折叠分支：双击「还有 N 个…」可展开该向</div>`;
    }}
  }}
  document.getElementById('info-content').innerHTML = `
    <div class="field"><b>${{esc(n.label)}}</b></div>
    <div class="field">类型: ${{esc(n._file_type || n._ui_type || 'unknown')}}</div>
    <div class="field">社区: ${{esc(n._community_name)}}</div>
    <div class="field">文件: ${{esc(n._source_file || '-')}}</div>
    <div class="field">位置: ${{fmtLoc(n._source_location)}}</div>
    <div class="field">度数: ${{n._degree}}</div>
    ${{treeBlock}}
    ${{neighborIds.length ? `<div class="field dim">相邻节点与关系 (${{neighborIds.length}})</div><div id="neighbors-list">${{neighborItems}}</div>` : ''}}
  `;
  document.querySelectorAll('.neighbor-link').forEach(el => {{
    el.addEventListener('click', () => focusNode(el.getAttribute('data-nid')));
  }});
}}

function focusNode(nodeId) {{
  if (!nodeId || aggregateMode) return;
  network.focus(nodeId, {{ scale: 1.35, animation: false }});
  network.selectNodes([nodeId]);
  applySelectionHighlight(nodeId);
  showInfo(nodeId);
}}

function computeMaxVisibleDegree() {{
  if (readableTreeMode) {{
    let maxVisDeg = 1;
    nodesDS.getIds().forEach(id => {{
      const nd = nodesDS.get(id);
      if (!nd || nd.hidden) return;
      const raw = NODE_BY_ID.get(id);
      const d = raw && raw.degree != null ? raw.degree : 0;
      if (d > maxVisDeg) maxVisDeg = d;
    }});
    return maxVisDeg;
  }}
  let maxVisDeg = 1;
  RAW_NODES.forEach(n => {{
    const nd = nodesDS.get(n.id);
    if (!nd || nd.hidden) return;
    if (n.degree > maxVisDeg) maxVisDeg = n.degree;
  }});
  return maxVisDeg;
}}

/** 不含「选中高亮」规则；选中时在外层再 Math.max(fs, 10) */
function policyFontSizeForNode(n, maxVisDeg, focus) {{
  const showMore = document.getElementById('cb-show-labels').checked;
  const bf = BASE_FONT.get(n.id) || {{ size: 0, color: '#ffffff' }};
  let fs = bf.size;
  if (showMore) {{
    const inSearch = focus && focus.has(n.id);
    const hiDeg = n.degree >= Math.max(5, maxVisDeg * 0.10);
    if (inSearch || hiDeg) fs = Math.max(fs, 10);
  }}
  return {{ bf, fs }};
}}

/** 标签策略：关 = 仅 Python  baked 的高度数标签；开 = 可见子图内高分位度数 + 搜索焦点子图 */
function applyLabelPolicy() {{
  if (aggregateMode) return;
  if (readableTreeMode) {{
    const q = document.getElementById('search').value.toLowerCase().trim();
    const focus = q ? computeSearchFocusIds(q) : null;
    const maxVisDeg = computeMaxVisibleDegree();
    const nu = [];
    nodesDS.getIds().forEach(id => {{
      const nd = nodesDS.get(id);
      if (!nd || nd.hidden) return;
      const raw = NODE_BY_ID.get(id);
      if (!raw) return;
      const {{ bf, fs }} = policyFontSizeForNode(raw, maxVisDeg, focus);
      const big = nd._treeOnMain || raw.degree >= Math.max(5, maxVisDeg * 0.12);
      nu.push({{ id, font: {{ ...bf, size: big ? Math.max(fs, 11) : fs }} }});
    }});
    if (nu.length) nodesDS.update(nu);
    return;
  }}
  const q = document.getElementById('search').value.toLowerCase().trim();
  const focus = q ? computeSearchFocusIds(q) : null;
  const maxVisDeg = computeMaxVisibleDegree();
  const nu = [];
  RAW_NODES.forEach(n => {{
    const nd = nodesDS.get(n.id);
    if (!nd || nd.hidden) return;
    const {{ bf, fs }} = policyFontSizeForNode(n, maxVisDeg, focus);
    nu.push({{ id: n.id, font: {{ ...bf, size: fs }} }});
  }});
  if (nu.length) nodesDS.update(nu);
}}

/** 分层树状：可读子图 + 固定坐标 + 自上而下（上游在上）；全量 1000+ 节点不进入 vis 分层引擎 */
function setHierarchicalLayoutMode() {{
  if (aggregateMode) return;
  readableTreeMode = true;
  applyReadableTreeLayout(true);
}}

function treeLayoutCacheKey(focusId, opts) {{
  const hid = [...hiddenCommunities].sort((a, b) => a - b).join('-');
  const tc =
    (document.getElementById('f-code').checked ? '1' : '0') +
    (document.getElementById('f-doc').checked ? '1' : '0') +
    (document.getElementById('f-concept').checked ? '1' : '0');
  const ex = [...treeExpandedOverflow].sort().join('|');
  return [focusId || '', allowedNodesCountForTree(), hid, tc, ex, opts.maxDepth, opts.maxNodes, opts.maxEdges, opts.maxChildrenPerNode].join('#');
}}

function allowedNodesCountForTree() {{
  let c = 0;
  RAW_NODES.forEach(n => {{ if (baseEligible(n)) c++; }});
  return c;
}}

function applyReadableTreeLayout(force) {{
  if (!readableTreeMode || aggregateMode) return;
  const allowed = new Set();
  RAW_NODES.forEach(n => {{ if (baseEligible(n)) allowed.add(n.id); }});
  const focus = network.getSelectedNodes()[0] || null;
  const opts = {{
    focusNodeId: focus,
    allowedIds: allowed,
    rawNodes: RAW_NODES,
    rawEdges: RAW_EDGES,
    NODE_BY_ID,
    legend: LEGEND,
    expandedOverflow: treeExpandedOverflow,
    maxDepth: Math.max(1, Math.min(12, parseInt(document.getElementById('tree-max-depth').value, 10) || 4)),
    maxNodes: Math.max(20, Math.min(500, parseInt(document.getElementById('tree-max-nodes').value, 10) || 200)),
    maxEdges: Math.max(50, Math.min(1200, parseInt(document.getElementById('tree-max-edges').value, 10) || 400)),
    maxChildrenPerNode: Math.max(4, Math.min(40, parseInt(document.getElementById('tree-max-children').value, 10) || 12)),
  }};
  const ck = treeLayoutCacheKey(focus, opts);
  if (!force && ck === _treeLayoutCacheKey && _treeLayoutCacheRes) {{
    /* 使用缓存 */
  }} else {{
    _treeLayoutCacheRes = computeReadableTreeLayout(opts);
    _treeLayoutCacheKey = ck;
  }}
  const res = _treeLayoutCacheRes;
  window.__lastReadableTreeMeta = res;
  nodesDS.clear();
  edgesDS.clear();
  nodesDS.add(res.visNodes);
  edgesDS.add(res.visEdges);
  network.setOptions({{
    layout: {{ hierarchical: {{ enabled: false }}, improvedLayout: false, randomSeed: 42 }},
    physics: {{ enabled: false }},
    interaction: {{
      hover: true,
      hoverConnectedEdges: false,
      selectConnectedEdges: false,
      tooltipDelay: 220,
      hideEdgesOnDrag: true,
      hideEdgesOnZoom: true,
      dragNodes: false,
      dragView: true,
      zoomView: true,
      zoomSpeed: 1.02,
      navigationButtons: false,
      keyboard: false,
      multiselect: false,
    }},
    edges: {{
      smooth: false,
      selectionWidth: 3,
      font: {{ size: 0, strokeWidth: 0 }},
      arrows: {{ to: {{ enabled: true, scaleFactor: 0.42 }} }},
    }},
  }});
  try {{ network.fit({{ animation: false }}); }} catch (e0) {{}}
  applyLabelPolicy();
  const sel = res.focusNodeId;
  if (sel && nodesDS.get(sel)) {{
    network.selectNodes([sel]);
    applySelectionHighlight(sel);
    showInfo(sel);
  }} else {{
    network.unselectAll();
    applySelectionHighlight(null);
  }}
}}

function setForceDirectedLayoutMode() {{
  if (aggregateMode) return;
  readableTreeMode = false;
  _treeLayoutCacheKey = '';
  _treeLayoutCacheRes = null;
  treeExpandedOverflow.clear();
  nodesDS.clear();
  edgesDS.clear();
  nodesDS.add(RAW_NODES.map(nodeToDatasetItem));
  edgesDS.add(RAW_EDGES);
  network.setOptions({{
    layout: {{
      hierarchical: {{ enabled: false }},
      improvedLayout: true,
      randomSeed: 42,
    }},
    physics: {{
      enabled: true,
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {{
        gravitationalConstant: -95,
        centralGravity: 0.004,
        springLength: 155,
        springConstant: 0.072,
        damping: 0.52,
        avoidOverlap: 0.82,
      }},
      maxVelocity: 36,
      minVelocity: 0.65,
      timestep: 0.38,
      stabilization: {{ iterations: 130, fit: true, updateInterval: 50 }},
    }},
    edges: {{
      smooth: false,
    }},
    interaction: {{
      hover: true,
      hoverConnectedEdges: false,
      selectConnectedEdges: false,
      tooltipDelay: 220,
      hideEdgesOnDrag: false,
      hideEdgesOnZoom: false,
      hideEdgesOnViewportDrag: false,
      dragNodes: true,
      dragView: true,
      zoomView: true,
      zoomSpeed: 1.02,
      navigationButtons: false,
      keyboard: false,
      multiselect: false,
    }},
  }});
  applyFiltersImmediate();
  network.once('stabilizationIterationsDone', () => {{
    network.setOptions({{ physics: {{ enabled: false }} }});
    try {{ network.storePositions(); }} catch (e) {{}}
    applyLabelPolicy();
    applyVisualState();
  }});
  network.stabilize();
}}

function applyLayoutModeFromCheckbox() {{
  if (aggregateMode) return;
  if (document.getElementById('cb-hierarchical').checked) setHierarchicalLayoutMode();
  else setForceDirectedLayoutMode();
}}

let _zoomEndTimer = null;
network.on('zoomEnd', () => {{
  if (_zoomEndTimer) clearTimeout(_zoomEndTimer);
  _zoomEndTimer = setTimeout(() => {{
    _zoomEndTimer = null;
    applyVisualState();
  }}, 90);
}});

network.on('doubleClick', (params) => {{
  if (aggregateMode) return;
  if (!document.getElementById('cb-hierarchical').checked) return;
  const nid = params.nodes[0];
  if (!nid) return;
  if (String(nid).startsWith('__tree_ov__')) {{
    treeExpandedOverflow.add(nid);
    _treeLayoutCacheKey = '';
    applyReadableTreeLayout(true);
    return;
  }}
  network.selectNodes([nid]);
  _treeLayoutCacheKey = '';
  applyReadableTreeLayout(true);
}});

function setAggregateChrome(on) {{
  const tf = document.getElementById('type-filters');
  tf.style.opacity = on ? '0.45' : '1';
  tf.style.pointerEvents = on ? 'none' : 'auto';
  document.getElementById('search').disabled = !!on;
  const lw = document.getElementById('legend-wrap');
  lw.style.opacity = on ? '0.45' : '1';
  lw.style.pointerEvents = on ? 'none' : 'auto';
  const hcb = document.getElementById('cb-hierarchical');
  hcb.disabled = !!on;
  const tbox = document.getElementById('tree-hier-params');
  if (tbox) tbox.style.display = on ? 'none' : (hcb.checked ? 'block' : 'none');
  if (on) {{
    _suppressHierCheckbox = true;
    hcb.checked = false;
    _suppressHierCheckbox = false;
  }}
}}

function syncLegendCheckboxesFromHidden() {{
  document.querySelectorAll('.legend-item[data-community-id]').forEach(item => {{
    const cid = parseInt(item.dataset.communityId, 10);
    const cb = item.querySelector('.legend-cb');
    const hid = hiddenCommunities.has(cid);
    if (cb) cb.checked = !hid;
    item.classList.toggle('dimmed', hid);
  }});
  updateSelectAllState();
}}

function enterAggregateView() {{
  aggregateMode = true;
  readableTreeMode = false;
  _treeLayoutCacheKey = '';
  _treeLayoutCacheRes = null;
  treeExpandedOverflow.clear();
  network.unselectAll();
  setAggregateChrome(true);
  nodesDS.clear();
  edgesDS.clear();
  nodesDS.add(META_NODES_RAW.map(metaToDatasetItem));
  edgesDS.add(META_EDGES_RAW);
  network.setOptions({{ physics: {{ enabled: true }} }});
  network.once('stabilizationIterationsDone', () => {{
    network.setOptions({{ physics: {{ enabled: false }} }});
    try {{ network.storePositions(); }} catch (e) {{}}
    network.fit({{ animation: false }});
    applyVisualState();
  }});
  document.getElementById('info-content').innerHTML =
    '<span class="empty">社区聚合 · 点击某一社区节点展开其成员子图</span>';
}}

function rebuildFullGraphFromRaw() {{
  nodesDS.clear();
  edgesDS.clear();
  nodesDS.add(RAW_NODES.map(nodeToDatasetItem));
  edgesDS.add(RAW_EDGES);
  network.setOptions({{ physics: {{ enabled: true }} }});
  network.once('stabilizationIterationsDone', () => {{
    network.setOptions({{ physics: {{ enabled: false }} }});
    try {{ network.storePositions(); }} catch (e) {{}}
    applyFiltersImmediate();
  }});
}}

function exitAggregateViewManual() {{
  aggregateMode = false;
  setAggregateChrome(false);
  hiddenCommunities.clear();
  syncLegendCheckboxesFromHidden();
  rebuildFullGraphFromRaw();
}}

function expandCommunityFromMeta(nid) {{
  const cid = parseInt(String(nid).replace('__meta_', ''), 10);
  if (Number.isNaN(cid)) return;
  aggregateMode = false;
  _suppressAggCheckbox = true;
  document.getElementById('cb-aggregate').checked = false;
  _suppressAggCheckbox = false;
  setAggregateChrome(false);
  hiddenCommunities.clear();
  LEGEND.forEach(c => {{ if (c.cid !== cid) hiddenCommunities.add(c.cid); }});
  syncLegendCheckboxesFromHidden();
  rebuildFullGraphFromRaw();
}}

function applyAggregateHighlight(selId) {{
  const nu = [];
  META_NODES_RAW.forEach(m => {{
    const bc = JSON.parse(JSON.stringify(m.color));
    if (!selId) nu.push({{ id: m.id, color: bc, opacity: 1 }});
    else if (m.id === selId) nu.push({{ id: m.id, color: bc, opacity: 1 }});
    else nu.push({{ id: m.id, color: {{ background: '#1e293b', border: '#0f172a' }}, opacity: 0.32 }});
  }});
  const eu = [];
  META_EDGES_RAW.forEach(e => {{
    const hit = selId && (e.from === selId || e.to === selId);
    if (!selId) {{
      eu.push({{ id: e.id, color: JSON.parse(JSON.stringify(e.color)), width: e.width }});
    }} else if (hit) {{
      eu.push({{ id: e.id, width: Math.max(2.5, e.width),
        color: {{ color: '#38bdf8', opacity: 0.9 }} }});
    }} else {{
      eu.push({{ id: e.id, color: {{ color: '#475569', opacity: 0.15 }}, width: 1 }});
    }}
  }});
  if (nu.length) nodesDS.update(nu);
  if (eu.length) edgesDS.update(eu);
}}

function applyVisualState() {{
  if (aggregateMode) {{
    applyAggregateHighlight(network.getSelectedNodes()[0] || null);
    return;
  }}
  const sel = network.getSelectedNodes()[0] || null;
  const q = document.getElementById('search').value.toLowerCase().trim();
  if (sel) applySelectionHighlight(sel);
  else if (q) applySearchHighlight(q);
  else applySelectionHighlight(null);
}}

/** 搜索高亮子图：命中点 ∪ 一跳邻居（均在 baseEligible 内）；无命中则还原 */
function computeSearchFocusIds(q) {{
  if (!q) return null;
  const matched = new Set();
  RAW_NODES.forEach(n => {{
    if (baseEligible(n) && passesSearch(n, q)) matched.add(n.id);
  }});
  if (matched.size === 0) return null;
  const focus = new Set(matched);
  matched.forEach(id => {{
    (ADJ.get(id) || []).forEach(nb => {{
      const raw = NODE_BY_ID.get(nb);
      if (raw && baseEligible(raw)) focus.add(nb);
    }});
  }});
  return focus;
}}

function applySearchHighlight(q) {{
  if (readableTreeMode) {{
    applySelectionHighlight(network.getSelectedNodes()[0] || null);
    return;
  }}
  const focus = computeSearchFocusIds(q);
  if (!focus) {{
    applySelectionHighlight(null);
    return;
  }}
  const nu = [];
  const eu = [];
  RAW_NODES.forEach(n => {{
    const bc = BASE_NODE.get(n.id);
    if (!bc) return;
    const nd = nodesDS.get(n.id);
    if (nd && nd.hidden) {{
      nu.push({{ id: n.id, color: bc, opacity: 1 }});
      return;
    }}
    if (focus.has(n.id)) nu.push({{ id: n.id, color: bc, opacity: 1 }});
    else nu.push({{ id: n.id, color: {{ background: '#1e293b', border: '#0f172a' }}, opacity: 0.13 }});
  }});
  RAW_EDGES.forEach(e => {{
    const ed = edgesDS.get(e.id);
    if (!ed || ed.hidden) return;
    const be = BASE_EDGE.get(e.id);
    const arr = be && be.arrows ? be.arrows : {{ to: {{ enabled: true, scaleFactor: 0.42 }} }};
    const endsIn = focus.has(e.from) && focus.has(e.to);
    if (endsIn) {{
      eu.push({{ id: e.id, width: Math.max(2, e.width + 0.5),
        color: {{ color: '#22d3ee', opacity: 0.88 }}, arrows: arr }});
    }} else {{
      eu.push({{ id: e.id, color: {{ color: '#475569', opacity: 0.1 }}, width: 1, arrows: arr }});
    }}
  }});
  if (nu.length) nodesDS.update(nu);
  if (eu.length) edgesDS.update(eu);
  applyLabelPolicy();
}}

function applySelectionHighlight(selectedId) {{
  if (readableTreeMode) {{
    const nids = nodesDS.getIds();
    const nu = [];
    const eu = [];
    const neigh =
      selectedId && nodesDS.get(selectedId)
        ? new Set(
            [...network.getConnectedNodes(selectedId), selectedId].filter(id => {{
              const nd = nodesDS.get(id);
              return nd && nd.hidden !== true;
            }})
          )
        : null;
    nids.forEach(id => {{
      const nd = nodesDS.get(id);
      if (!nd) return;
      const baseC = BASE_NODE.get(id) || nd.color;
      const hi = !selectedId || neigh.has(id);
      nu.push({{
        id,
        color: hi ? baseC : {{ background: '#1e293b', border: '#0f172a' }},
        opacity: hi ? 1 : 0.2,
        borderWidth: selectedId && id === selectedId ? 4 : nd.borderWidth,
      }});
    }});
    edgesDS.getIds().forEach(eid => {{
      const ed = edgesDS.get(eid);
      const hit = selectedId && (ed.from === selectedId || ed.to === selectedId);
      eu.push({{
        id: eid,
        width: hit ? Math.max(3, ed.width || 1) : Math.max(0.5, (ed.width || 1) * 0.65),
        color: hit ? {{ color: '#38bdf8', opacity: 0.95 }} : {{ color: '#475569', opacity: 0.14 }},
        arrows: ed.arrows || {{ to: {{ enabled: true, scaleFactor: 0.42 }} }},
      }});
    }});
    if (nu.length) nodesDS.update(nu);
    if (eu.length) edgesDS.update(eu);
    return;
  }}
  const nu = [];
  const eu = [];
  const q = document.getElementById('search').value.toLowerCase().trim();
  const focus = q ? computeSearchFocusIds(q) : null;
  const maxVisDeg = computeMaxVisibleDegree();

  if (!selectedId) {{
    RAW_NODES.forEach(n => {{
      const bc = BASE_NODE.get(n.id);
      if (bc) nu.push({{ id: n.id, color: bc, opacity: 1 }});
    }});
    RAW_EDGES.forEach(e => {{
      const be = BASE_EDGE.get(e.id);
      if (be) eu.push({{ id: e.id, color: be.color, width: be.width, arrows: be.arrows }});
    }});
    if (nu.length) nodesDS.update(nu);
    if (eu.length) edgesDS.update(eu);
    applyLabelPolicy();
    return;
  }}

  const neigh = new Set(
    [...network.getConnectedNodes(selectedId), selectedId].filter(id => {{
      const nd = nodesDS.get(id);
      return nd && nd.hidden !== true;
    }})
  );

  RAW_NODES.forEach(n => {{
    const bc = BASE_NODE.get(n.id);
    if (!bc) return;
    const nd = nodesDS.get(n.id);
    const {{ bf, fs }} = policyFontSizeForNode(n, maxVisDeg, focus);
    const hi = neigh.has(n.id);
    const font = {{ ...bf, size: hi ? Math.max(fs, 10) : fs }};
    if (nd && nd.hidden) {{
      nu.push({{ id: n.id, color: bc, opacity: 1, font }});
      return;
    }}
    if (hi) nu.push({{ id: n.id, color: bc, opacity: 1, font }});
    else nu.push({{ id: n.id, color: {{ background: '#2a2a3a', border: '#1f1f2e' }}, opacity: 0.22, font }});
  }});
  RAW_EDGES.forEach(e => {{
    const ed = edgesDS.get(e.id);
    if (ed && ed.hidden) return;
    const be = BASE_EDGE.get(e.id);
    const arr = be && be.arrows ? be.arrows : {{ to: {{ enabled: true, scaleFactor: 0.42 }} }};
    const hit = e.from === selectedId || e.to === selectedId;
    if (hit) {{
      eu.push({{ id: e.id, width: Math.max(3, e.width + 1),
        color: {{ color: '#38bdf8', opacity: 0.95 }}, arrows: arr }});
    }} else {{
      eu.push({{ id: e.id, color: {{ color: '#334155', opacity: 0.12 }}, width: 1, arrows: arr }});
    }}
  }});
  if (nu.length) nodesDS.update(nu);
  if (eu.length) edgesDS.update(eu);
}}

network.on('click', params => {{
  if (aggregateMode && params.nodes.length > 0) {{
    const nid = params.nodes[0];
    if (String(nid).startsWith('__meta_')) {{
      expandCommunityFromMeta(nid);
      return;
    }}
  }}
  if (params.nodes.length > 0) {{
    const nid = params.nodes[0];
    applySelectionHighlight(nid);
    showInfo(nid);
  }} else if (params.edges.length > 0) {{
    network.unselectAll();
    const eid = params.edges[0];
    let ed = RAW_EDGES.find(x => x.id === eid);
    const aggEdge = aggregateMode;
    if (aggEdge) ed = META_EDGES_RAW.find(x => x.id === eid);
    const fa = ed ? nodesDS.get(ed.from) : null;
    const ta = ed ? nodesDS.get(ed.to) : null;
    const desc = ed ? (aggEdge ? (ed.title || '') : esc(String(ed.relation || 'relates_to'))) : '';
    document.getElementById('info-content').innerHTML = ed
      ? (aggEdge
        ? `<div class="field dim">聚合跨社区边</div>
           <div class="field"><b>${{desc}}</b></div>
           <div class="field">从: ${{esc(fa ? fa.label : ed.from)}}</div>
           <div class="field">到: ${{esc(ta ? ta.label : ed.to)}}</div>`
        : `<div class="field dim">边（有向）</div>
           <div class="field"><b>${{desc}}</b></div>
           <div class="field">从: ${{esc(fa ? fa.label : ed.from)}}</div>
           <div class="field">到: ${{esc(ta ? ta.label : ed.to)}}</div>`)
      : '<span class="empty">点击节点或边查看详情</span>';
    applyVisualState();
  }} else {{
    network.unselectAll();
    document.getElementById('info-content').innerHTML = '<span class="empty">点击节点查看详情</span>';
    applyVisualState();
  }}
}});

network.on('dragEnd', params => {{
  if (aggregateMode) return;
  if (params.nodes && params.nodes.length) {{
    applySelectionHighlight(params.nodes[0]);
    showInfo(params.nodes[0]);
  }}
}});

function passesTypeFilter(n) {{
  const cbCode = document.getElementById('f-code').checked;
  const cbDoc = document.getElementById('f-doc').checked;
  const cbConcept = document.getElementById('f-concept').checked;
  const t = n._ui_type;
  if (t === 'code' && !cbCode) return false;
  if (t === 'doc' && !cbDoc) return false;
  if (t === 'concept' && !cbConcept) return false;
  return true;
}}

function passesSearch(n, q) {{
  if (!q) return true;
  const hay = (n.label + '\\n' + (n._source_file || '') + '\\n' + (n.norm_label || '')).toLowerCase();
  return hay.includes(q);
}}

function nodeVisibleByCommunity(n) {{
  return !hiddenCommunities.has(n.community);
}}

function baseEligible(n) {{
  return passesTypeFilter(n) && nodeVisibleByCommunity(n);
}}

/** 仅类型 + 社区决定是否 hidden；搜索只做高亮不参与隐藏 */
function computeVisibleIds() {{
  const allowed = new Set();
  RAW_NODES.forEach(n => {{ if (baseEligible(n)) allowed.add(n.id); }});
  return allowed;
}}

function applyFiltersImmediate() {{
  if (aggregateMode) return;
  if (readableTreeMode) {{
    _treeLayoutCacheKey = '';
    applyReadableTreeLayout(true);
    return;
  }}
  const sel = network.getSelectedNodes()[0] || null;
  const allowed = computeVisibleIds();
  const nu = [];
  RAW_NODES.forEach(n => {{
    const vis = allowed.has(n.id);
    nu.push({{ id: n.id, hidden: !vis }});
  }});
  const eu = [];
  RAW_EDGES.forEach(e => {{
    const ok = allowed.has(e.from) && allowed.has(e.to);
    eu.push({{ id: e.id, hidden: !ok }});
  }});
  if (nu.length) nodesDS.update(nu);
  if (eu.length) edgesDS.update(eu);
  applyLabelPolicy();
  if (sel && !allowed.has(sel)) {{
    network.unselectAll();
    document.getElementById('info-content').innerHTML = '<span class="empty">当前筛选下无此节点</span>';
    applyVisualState();
  }} else {{
    applyVisualState();
  }}
  if (!aggregateMode && document.getElementById('cb-hierarchical').checked && readableTreeMode) {{
    if (_hierLayoutDebounce) clearTimeout(_hierLayoutDebounce);
    _hierLayoutDebounce = setTimeout(() => {{
      _hierLayoutDebounce = null;
      applyReadableTreeLayout(true);
    }}, 140);
  }}
}}

let _filterTimer = null;
function applyFilters() {{
  if (_filterTimer) clearTimeout(_filterTimer);
  _filterTimer = setTimeout(() => {{ applyFiltersImmediate(); _filterTimer = null; }}, 110);
}}

const searchResults = document.getElementById('search-results');
const searchInput = document.getElementById('search');
searchInput.addEventListener('input', () => {{
  applyFilters();
  const q = searchInput.value.toLowerCase().trim();
  searchResults.innerHTML = '';
  if (!q) {{ searchResults.style.display = 'none'; return; }}
  const matches = RAW_NODES.filter(n => baseEligible(n) && passesSearch(n, q)).slice(0, 24);
  if (!matches.length) {{ searchResults.style.display = 'none'; return; }}
  searchResults.style.display = 'block';
  matches.forEach(n => {{
    const el = document.createElement('div');
    el.className = 'search-item';
    el.textContent = n.label + (n._source_file ? '  ·  ' + n._source_file : '');
    el.style.borderLeft = '3px solid ' + n.color.background;
    el.onclick = () => {{
      focusNode(n.id);
      searchResults.style.display = 'none';
    }};
    searchResults.appendChild(el);
  }});
}});
['f-code','f-doc','f-concept'].forEach(id => {{
  document.getElementById(id).addEventListener('change', () => {{
    if (_filterTimer) clearTimeout(_filterTimer);
    applyFiltersImmediate();
  }});
}});
document.addEventListener('click', e => {{
  if (!searchResults.contains(e.target) && e.target !== searchInput)
    searchResults.style.display = 'none';
}});

const hiddenCommunities = new Set();
const selectAllCb = document.getElementById('select-all-cb');

function updateSelectAllState() {{
  const total = LEGEND.length;
  const hidden = hiddenCommunities.size;
  selectAllCb.checked = hidden === 0;
  selectAllCb.indeterminate = hidden > 0 && hidden < total;
}}

function toggleAllCommunities(hide) {{
  document.querySelectorAll('.legend-item').forEach(item => {{
    hide ? item.classList.add('dimmed') : item.classList.remove('dimmed');
  }});
  document.querySelectorAll('.legend-cb').forEach(cb => {{ cb.checked = !hide; }});
  LEGEND.forEach(c => {{ if (hide) hiddenCommunities.add(c.cid); else hiddenCommunities.delete(c.cid); }});
  if (_filterTimer) clearTimeout(_filterTimer);
  applyFiltersImmediate();
  updateSelectAllState();
}}

document.getElementById('cb-show-labels').addEventListener('change', () => {{
  applyLabelPolicy();
  applyVisualState();
}});
document.getElementById('cb-aggregate').addEventListener('change', (e) => {{
  if (_suppressAggCheckbox) return;
  if (e.target.checked) enterAggregateView();
  else exitAggregateViewManual();
}});
document.getElementById('cb-hierarchical').addEventListener('change', (e) => {{
  if (_suppressHierCheckbox) return;
  const box = document.getElementById('tree-hier-params');
  if (box) box.style.display = e.target.checked ? 'block' : 'none';
  applyLayoutModeFromCheckbox();
}});
let _treeParamTimer = null;
['tree-max-depth', 'tree-max-nodes', 'tree-max-edges', 'tree-max-children'].forEach((tid) => {{
  const el = document.getElementById(tid);
  if (!el) return;
  el.addEventListener('change', () => {{
    if (!document.getElementById('cb-hierarchical').checked) return;
    _treeLayoutCacheKey = '';
    if (_treeParamTimer) clearTimeout(_treeParamTimer);
    _treeParamTimer = setTimeout(() => {{
      _treeParamTimer = null;
      applyReadableTreeLayout(true);
    }}, 220);
  }});
}});

const legendEl = document.getElementById('legend');
LEGEND.forEach(c => {{
  const item = document.createElement('div');
  item.className = 'legend-item';
  item.dataset.communityId = String(c.cid);
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.className = 'legend-cb';
  cb.checked = true;
  cb.addEventListener('change', (e) => {{
    e.stopPropagation();
    if (cb.checked) {{
      hiddenCommunities.delete(c.cid);
      item.classList.remove('dimmed');
    }} else {{
      hiddenCommunities.add(c.cid);
      item.classList.add('dimmed');
    }}
    if (_filterTimer) clearTimeout(_filterTimer);
    applyFiltersImmediate();
    updateSelectAllState();
  }});
  item.innerHTML = `<div class="legend-dot" style="background:${{c.color}}"></div>
    <span class="legend-label">${{esc(c.label)}}</span>
    <span class="legend-count">${{c.count}}</span>`;
  item.prepend(cb);
  item.onclick = (e) => {{
    if (e.target === cb) return;
    cb.checked = !cb.checked;
    cb.dispatchEvent(new Event('change'));
  }};
  legendEl.appendChild(item);
}});
"""

    styles = """<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0b0f14; color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; height: 100vh; overflow: hidden; display: flex; flex-direction: column; }
  #topbar { flex-shrink: 0; display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: #111827; border-bottom: 1px solid #1f2937; flex-wrap: wrap; }
  #topbar .grow { flex: 1; min-width: 140px; position: relative; }
  #search { width: 100%; background: #0b0f14; border: 1px solid #334155; color: #e6edf3; padding: 8px 12px; border-radius: 8px; font-size: 13px; outline: none; }
  #search:focus { border-color: #38bdf8; }
  #search-results { display: none; position: absolute; left: 0; right: 0; top: 100%; margin-top: 4px; max-height: 200px; overflow-y: auto; background: #111827; border: 1px solid #334155; border-radius: 8px; z-index: 20; box-shadow: 0 8px 24px rgba(0,0,0,0.45); }
  .search-item { padding: 6px 10px; cursor: pointer; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .search-item:hover { background: #1e293b; }
  #type-filters { display: flex; align-items: center; gap: 14px; font-size: 12px; color: #94a3b8; flex-shrink: 0; }
  #type-filters label { display: flex; align-items: center; gap: 6px; cursor: pointer; user-select: none; }
  #type-filters label:hover { color: #e2e8f0; }
  #main { flex: 1; display: flex; min-height: 0; }
  .graph-stack { flex: 1; min-width: 0; min-height: 0; position: relative; background: #0b0f14; }
  #graph-global, #graph-trace-wrap { position: absolute; inset: 0; }
  #graph-global { z-index: 1; }
  #graph-trace-wrap { z-index: 2; display: none; flex-direction: column; }
  #graph-trace { flex: 1; min-height: 0; width: 100%; background: #0b0f14; }
  .view-mode-bar { display: flex; gap: 8px; align-items: center; margin-right: 12px; flex-shrink: 0; }
  .vm-btn { padding: 6px 14px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #94a3b8; font-size: 12px; cursor: pointer; }
  .vm-btn:hover:not(:disabled) { color: #e2e8f0; border-color: #475569; }
  .vm-btn.vm-active { background: #1e3a5f; border-color: #38bdf8; color: #e0f2fe; }
  .vm-btn:disabled { opacity: 0.45; cursor: not-allowed; }
  #trace-overlay-bar { flex-shrink: 0; padding: 8px 12px; background: rgba(15,23,42,0.92); border-bottom: 1px solid #1f2937; display: flex; flex-wrap: wrap; align-items: flex-start; gap: 12px; }
  #trace-back-btn { padding: 6px 12px; border-radius: 6px; border: 1px solid #334155; background: #111827; color: #cbd5e1; font-size: 12px; cursor: pointer; }
  #trace-back-btn:hover { border-color: #38bdf8; color: #fff; }
  #trace-focus-info { font-size: 12px; color: #cbd5e1; flex: 1; min-width: 200px; }
  #trace-isolated-hint { width: 100%; color: #f87171; font-size: 12px; padding-top: 4px; }
  #sidebar { width: 300px; background: #111827; border-left: 1px solid #1f2937; display: flex; flex-direction: column; overflow: hidden; }
  #info-panel { padding: 14px; border-bottom: 1px solid #1f2937; min-height: 160px; }
  #info-panel h3 { font-size: 12px; color: #64748b; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.06em; }
  #info-content { font-size: 13px; color: #cbd5e1; line-height: 1.65; }
  #info-content .field { margin-bottom: 6px; }
  #info-content .field b { color: #f1f5f9; }
  #info-content .dim { color: #64748b; font-size: 11px; margin-top: 8px; }
  #info-content .empty { color: #475569; font-style: italic; }
  .neighbor-link { display: block; padding: 3px 8px; margin: 2px 0; border-radius: 4px; cursor: pointer; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-left: 3px solid #334155; }
  .neighbor-link:hover { background: #1e293b; }
  .neighbor-row {{ display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; margin: 2px 0; }}
  .rel-tag {{ font-size: 11px; color: #94a3b8; flex: 1; min-width: 0; word-break: break-word; }}
  #neighbors-list { max-height: 220px; overflow-y: auto; margin-top: 4px; }
  #legend-wrap { flex: 1; overflow-y: auto; padding: 12px 14px; }
  #legend-wrap h3 { font-size: 12px; color: #64748b; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.06em; }
  .legend-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; cursor: pointer; border-radius: 4px; font-size: 12px; }
  .legend-item:hover { background: #1e293b; }
  .legend-item.dimmed { opacity: 0.35; }
  .legend-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
  .legend-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .legend-count { color: #64748b; font-size: 11px; }
  #stats { padding: 10px 14px; border-top: 1px solid #1f2937; font-size: 11px; color: #475569; }
  #legend-controls { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  #legend-controls label { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; color: #94a3b8; user-select: none; }
  .legend-cb, #select-all-cb { appearance: none; -webkit-appearance: none; width: 14px; height: 14px; border: 1.5px solid #475569; border-radius: 3px; background: #0b0f14; cursor: pointer; position: relative; flex-shrink: 0; }
  .legend-cb:checked, #select-all-cb:checked { background: #38bdf8; border-color: #38bdf8; }
  .legend-cb:checked::after, #select-all-cb:checked::after { content: ''; position: absolute; left: 3.5px; top: 1px; width: 4px; height: 7px; border: solid #0b0f14; border-width: 0 2px 2px 0; transform: rotate(45deg); }
  #select-all-cb:indeterminate { background: #38bdf8; border-color: #38bdf8; }
  #select-all-cb:indeterminate::after { content: ''; position: absolute; left: 2px; top: 5px; width: 8px; height: 2px; background: #0b0f14; border: none; transform: none; }
  .hint { font-size: 11px; color: #475569; padding: 0 14px 8px; }
</style>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Graphify 增强视图 · fpai</title>
<script src="vis-network.min.js" onerror="this.onerror=null;this.src='https://cdn.jsdelivr.net/npm/vis-network@9.1.9/standalone/umd/vis-network.min.js'"></script>
{styles}
</head>
<body>
<div id="topbar">
  <div class="view-mode-bar">
    <button type="button" class="vm-btn vm-active" id="vm-global">全局视图</button>
    <button type="button" class="vm-btn" id="vm-trace" disabled title="双击节点进入">链路视图</button>
  </div>
  <div class="grow">
    <input id="search" type="search" placeholder="函数名 / 文件路径（高亮匹配子图，其余仍显示）…" autocomplete="off">
    <div id="search-results"></div>
  </div>
  <div id="type-filters">
    <span style="color:#64748b">类型</span>
    <label><input type="checkbox" id="f-code" checked> 代码</label>
    <label><input type="checkbox" id="f-doc" checked> 文档</label>
    <label><input type="checkbox" id="f-concept" checked> 概念</label>
  </div>
</div>
<p class="hint">缩放/拖拽时边保持绘制 · 「分层树状」为<strong>可读子图</strong>（≤200 节点 / 400 边，固定坐标）· 「社区聚合」与分层互斥（聚合时自动关分层）</p>
<div id="main">
  <div class="graph-stack">
    <div id="graph-global"></div>
    <div id="graph-trace-wrap">
      <div id="trace-overlay-bar">
        <button type="button" id="trace-back-btn">← 返回全局视图</button>
        <div id="trace-focus-info"></div>
        <div id="trace-isolated-hint" style="display:none;">该节点没有上下游调用关系（当前过滤：calls / imports；节点过少时已放宽全部关系）</div>
      </div>
      <div id="graph-trace"></div>
    </div>
  </div>
  <div id="sidebar">
    <div id="view-controls" style="padding:12px 14px;border-bottom:1px solid #1f2937;">
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#cbd5e1;cursor:pointer;margin-bottom:10px;user-select:none;">
        <input type="checkbox" id="cb-show-labels"> 显示更多标签（高度数 + 搜索子图）
      </label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#cbd5e1;cursor:pointer;user-select:none;">
        <input type="checkbox" id="cb-aggregate"> 社区聚合概览（点社区展开）
      </label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#cbd5e1;cursor:pointer;margin-top:10px;user-select:none;">
        <input type="checkbox" id="cb-hierarchical"> 分层树状布局（可读子图 · 固定坐标 · 自上而下）
      </label>
      <div id="tree-hier-params" style="display:none;margin-top:10px;padding-top:10px;border-top:1px solid #1f2937;font-size:12px;color:#94a3b8;">
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
          <label>最大层数 <input type="number" id="tree-max-depth" value="4" min="1" max="12" style="width:48px;background:#0b0f14;border:1px solid #334155;color:#e2e8f0;border-radius:4px;padding:2px 4px"></label>
          <label>最多节点 <input type="number" id="tree-max-nodes" value="200" min="20" max="500" style="width:52px;background:#0b0f14;border:1px solid #334155;color:#e2e8f0;border-radius:4px;padding:2px 4px"></label>
          <label>最多边 <input type="number" id="tree-max-edges" value="400" min="50" max="1200" style="width:56px;background:#0b0f14;border:1px solid #334155;color:#e2e8f0;border-radius:4px;padding:2px 4px"></label>
          <label>每节点子数 <input type="number" id="tree-max-children" value="12" min="4" max="40" style="width:48px;background:#0b0f14;border:1px solid #334155;color:#e2e8f0;border-radius:4px;padding:2px 4px"></label>
        </div>
        <div style="margin-top:6px;font-size:11px;color:#64748b">双击节点以之为中心重算子图；双击「还有 N 个…」展开该向分支。拖拽/缩放时自动隐藏边以减负。</div>
      </div>
    </div>
    <div id="info-panel">
      <h3>节点详情</h3>
      <div id="info-content"><span class="empty">点击图中节点</span></div>
    </div>
    <div id="legend-wrap">
      <h3>社区（Leiden 着色）</h3>
      <div id="legend-controls">
        <label><input type="checkbox" id="select-all-cb" checked onchange="toggleAllCommunities(!this.checked)">全选社区</label>
      </div>
      <div id="legend"></div>
    </div>
    <div id="stats">{stats}</div>
  </div>
</div>
<script>
{script}
{trace_fragment}
</script>
</body>
</html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", type=Path, default=Path("graphify-out/graph.json"))
    ap.add_argument("--out", type=Path, default=Path("graphify-out/graph.html"))
    args = ap.parse_args()
    path = args.graph
    if not path.is_file():
        raise SystemExit(f"找不到 {path.resolve()}，请先运行 graphify extract 或 /graphify .")
    data = json.loads(path.read_text(encoding="utf-8"))
    vis_nodes, vis_edges, legend = build_vis_payload(data)
    meta_nodes, meta_edges = build_meta_graph(vis_nodes, vis_edges, legend)
    n, e = len(vis_nodes), len(vis_edges)
    ccount = len({x["community"] for x in vis_nodes})
    stats = f"{n} 节点 · {e} 边 · {ccount} 个社区 — 由 tools/build_graphify_enhanced_html.py 自 graph.json 生成"
    frag_path = Path(__file__).resolve().parent / "trace_view_fragment.js"
    trace_js = frag_path.read_text(encoding="utf-8") if frag_path.is_file() else ""
    tree_path = Path(__file__).resolve().parent / "tree_layout_fragment.js"
    tree_js = tree_path.read_text(encoding="utf-8") if tree_path.is_file() else ""
    html = render_html(vis_nodes, vis_edges, legend, meta_nodes, meta_edges, stats, trace_js, tree_js)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    vis_bundle = Path(__file__).resolve().parent / "third_party" / "vis-network.min.js"
    vis_out = args.out.parent / "vis-network.min.js"
    if vis_bundle.is_file():
        shutil.copy2(vis_bundle, vis_out)
        print(f"Wrote {args.out.resolve()} ({n} nodes) and {vis_out.resolve()}")
    else:
        print(
            f"Wrote {args.out.resolve()} ({n} nodes); 警告: 缺少 {vis_bundle}，"
            "graph.html 将仅靠 onerror 回退 CDN 加载 vis-network",
        )


if __name__ == "__main__":
    main()
