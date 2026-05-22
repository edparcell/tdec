"""Local HTTP server and standalone HTML export for viewing TDEC run results."""

from __future__ import annotations

import json
import socket
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _load_all_debates(run_dir: Path) -> dict:
    debates_dir = run_dir / "debates"
    result = {}
    for f in sorted(debates_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        result[data["id"]] = data
    return result


def _load_all_judgements(run_dir: Path) -> dict:
    judgements_dir = run_dir / "judgements"
    result: dict[str, list] = {}
    for f in sorted(judgements_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        debate_id = data["debate_id"]
        result.setdefault(debate_id, []).append(data)
    return result


def _make_handler(run_dir: Path):
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    debates_dir = run_dir / "debates"
    judgements_dir = run_dir / "judgements"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = unquote(self.path)
            if path == "/" or path == "":
                self._serve_html()
            elif path == "/api/summary":
                self._serve_json(summary)
            elif path.startswith("/api/debates/"):
                debate_id = path[len("/api/debates/"):]
                self._serve_file(debates_dir / f"{debate_id}.json")
            elif path.startswith("/api/judgements/"):
                debate_id = path[len("/api/judgements/"):]
                files = sorted(judgements_dir.glob(f"{debate_id}__*.json"))
                results = []
                for f in files:
                    results.append(json.loads(f.read_text(encoding="utf-8")))
                self._serve_json(results)
            else:
                self.send_error(404)

        def _serve_html(self):
            html = _render_template(
                summary_json=json.dumps(summary),
                run_name=run_dir.name,
                debates_json="null",
                judgements_json="null",
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        def _serve_json(self, data):
            body = json.dumps(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def _serve_file(self, filepath: Path):
            if not filepath.exists():
                self.send_error(404)
                return
            self._serve_json(json.loads(filepath.read_text(encoding="utf-8")))

        def log_message(self, format, *args):
            pass

    return Handler


def serve(run_dir: Path, port: int | None = None) -> None:
    if port is None:
        port = _find_free_port()
    handler = _make_handler(run_dir)
    server = HTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Serving {run_dir.name} at {url}")
    print("Press Ctrl+C to stop.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


def export_html(run_dir: Path, output: Path) -> None:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    debates = _load_all_debates(run_dir)
    judgements = _load_all_judgements(run_dir)
    html = _render_template(
        summary_json=json.dumps(summary),
        run_name=run_dir.name,
        debates_json=json.dumps(debates),
        judgements_json=json.dumps(judgements),
    )
    output.write_text(html, encoding="utf-8")


def _render_template(
    summary_json: str, run_name: str, debates_json: str, judgements_json: str
) -> str:
    return (
        _HTML_TEMPLATE.replace("__SUMMARY_JSON__", summary_json)
        .replace("__RUN_NAME__", run_name)
        .replace("__ALL_DEBATES_JSON__", debates_json)
        .replace("__ALL_JUDGEMENTS_JSON__", judgements_json)
    )


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TDEC Viewer — __RUN_NAME__</title>
<style>
:root {
  --bg: #0f1117;
  --surface: #1a1d27;
  --surface2: #242836;
  --border: #2e3345;
  --text: #e1e4ed;
  --text-dim: #8b90a0;
  --pro-color: #22c55e;
  --con-color: #ef4444;
  --pro-bg: rgba(34,197,94,0.15);
  --con-bg: rgba(239,68,68,0.15);
  --tie-color: #eab308;
  --accent: #6366f1;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
  min-height: 100vh;
}

.header {
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}

.header h1 {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 4px;
}

.header .run-name {
  color: var(--accent);
}

.stats-bar {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  margin-top: 10px;
  font-size: 13px;
}

.stat { color: var(--text-dim); }
.stat strong { color: var(--text); font-weight: 500; }

.main-layout {
  display: flex;
  height: calc(100vh - 80px);
}

.left-panel {
  flex: 0 0 auto;
  overflow-y: auto;
  padding: 20px 24px;
  border-right: 1px solid var(--border);
  min-width: 320px;
  max-width: 55vw;
}

.right-panel {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  display: none;
}

.right-panel.active { display: block; }

.section-title {
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-dim);
  margin-bottom: 12px;
}

/* Elo table */
.elo-table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 24px;
  font-size: 13px;
}

.elo-table th {
  text-align: left;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
  font-weight: 500;
}

.elo-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
}

.elo-table .model-name { font-weight: 500; }
.elo-table .elo-val { text-align: right; font-variant-numeric: tabular-nums; }

/* Cross-table */
.matrix-container {
  margin-bottom: 24px;
}

.matrix-topic {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  margin: 20px 0 4px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.matrix-topic:first-child {
  margin-top: 0;
  padding-top: 0;
  border-top: none;
}

.matrix-wrapper {
  overflow-x: auto;
}

table.matrix {
  border-collapse: collapse;
  font-size: 13px;
  white-space: nowrap;
}

table.matrix th, table.matrix td {
  padding: 8px 12px;
  border: 1px solid var(--border);
  text-align: center;
}

table.matrix th {
  background: var(--surface2);
  color: var(--text-dim);
  font-weight: 500;
}

table.matrix th.row-header {
  text-align: right;
  font-weight: 500;
  color: var(--text);
}

table.matrix th.corner {
  background: var(--surface);
}

table.matrix td.cell {
  cursor: pointer;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  transition: outline 0.1s;
  min-width: 64px;
}

table.matrix td.cell:hover {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

table.matrix td.cell.selected {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

table.matrix td.cell.self-debate {
  font-style: italic;
  opacity: 0.7;
}

table.matrix td.total-cell {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

table.matrix th.total-header {
  font-weight: 600;
}

/* Detail panel */
.detail-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--text-dim);
  font-size: 14px;
  text-align: center;
}

.detail-header {
  margin-bottom: 20px;
}

.detail-header h2 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
}

.detail-header .matchup {
  font-size: 13px;
  color: var(--text-dim);
}

.back-btn {
  display: none;
  background: var(--surface2);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 6px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  margin-bottom: 16px;
}

.back-btn:hover { background: var(--border); }

/* Judge cards */
.judge-cards {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 24px;
}

.judge-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  flex: 1 1 280px;
  min-width: 260px;
}

.judge-card .judge-name {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 8px;
}

.judge-card .verdict {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
}

.verdict.pro { background: var(--pro-bg); color: var(--pro-color); }
.verdict.con { background: var(--con-bg); color: var(--con-color); }
.verdict.tie { background: rgba(234,179,8,0.15); color: var(--tie-color); }

.judge-card .scores {
  font-size: 12px;
  color: var(--text-dim);
  margin-top: 6px;
}

.judge-card .confidence {
  font-size: 12px;
  color: var(--text-dim);
}

.judge-card .summary-text {
  font-size: 13px;
  margin-top: 8px;
  line-height: 1.5;
}

.judge-card .reasons {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.6;
}

.judge-card .reasons li {
  margin-bottom: 4px;
  margin-left: 16px;
}

/* Rubric mini-table */
.rubric-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin-top: 10px;
}

.rubric-table th, .rubric-table td {
  padding: 3px 6px;
  border-bottom: 1px solid var(--border);
  text-align: center;
}

.rubric-table th {
  color: var(--text-dim);
  font-weight: 500;
  text-align: left;
}

.rubric-table td.pro-score { color: var(--pro-color); }
.rubric-table td.con-score { color: var(--con-color); }

/* Transcript */
.transcript {
  margin-top: 8px;
}

.transcript-title {
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-dim);
  margin-bottom: 12px;
}

.turn {
  margin-bottom: 20px;
  border-left: 3px solid var(--border);
  padding-left: 16px;
}

.turn.pro { border-left-color: var(--pro-color); }
.turn.con { border-left-color: var(--con-color); }

.turn-header {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 6px;
  display: flex;
  gap: 8px;
  align-items: center;
}

.turn-header .side-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.side-badge.pro { background: var(--pro-bg); color: var(--pro-color); }
.side-badge.con { background: var(--con-bg); color: var(--con-color); }

.turn-header .model-label {
  color: var(--text-dim);
  font-weight: 400;
}

.turn-header .round-label {
  color: var(--text-dim);
  font-weight: 400;
  margin-left: auto;
}

.turn-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text);
  word-wrap: break-word;
}

.turn-content h1, .turn-content h2, .turn-content h3, .turn-content h4 {
  font-size: 15px;
  font-weight: 600;
  margin: 16px 0 8px;
  color: var(--text);
}

.turn-content h1 { font-size: 17px; }
.turn-content h2 { font-size: 16px; }

.turn-content p { margin: 8px 0; }

.turn-content ul, .turn-content ol {
  margin: 8px 0;
  padding-left: 24px;
}

.turn-content li { margin: 4px 0; }

.turn-content hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 16px 0;
}

.turn-content strong { font-weight: 600; }
.turn-content em { font-style: italic; }

/* Loading spinner */
.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: var(--text-dim);
}

.loading::after {
  content: "";
  width: 20px;
  height: 20px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  margin-left: 10px;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* Responsive */
@media (max-width: 900px) {
  .main-layout { flex-direction: column; }
  .left-panel {
    max-width: 100%;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  .left-panel.hidden { display: none; }
  .right-panel { flex: none; }
  .back-btn { display: inline-block; }
}
</style>
</head>
<body>

<div class="header">
  <h1>TDEC <span class="run-name">__RUN_NAME__</span></h1>
  <div class="stats-bar" id="stats-bar"></div>
</div>

<div class="main-layout">
  <div class="left-panel" id="left-panel">
    <div id="elo-section"></div>
    <div id="matrix-section"></div>
  </div>
  <div class="right-panel" id="right-panel">
    <button class="back-btn" id="back-btn" onclick="showList()">Back to matrix</button>
    <div id="detail-content">
      <div class="detail-placeholder">Click a cell in the cross-table to view the debate.</div>
    </div>
  </div>
</div>

<script>
const SUMMARY = __SUMMARY_JSON__;
const ALL_DEBATES = __ALL_DEBATES_JSON__;
const ALL_JUDGEMENTS = __ALL_JUDGEMENTS_JSON__;

// ── Render stats bar ──
function renderStats() {
  const bar = document.getElementById('stats-bar');
  const cost = SUMMARY.total_cost_usd;
  const latency = SUMMARY.total_latency_seconds;
  const debateCount = SUMMARY.debates.length;
  const modelCount = SUMMARY.models.length;
  const motions = SUMMARY.motions || [];

  let html = `
    <span class="stat"><strong>$${cost.toFixed(4)}</strong> total cost</span>
    <span class="stat"><strong>${formatTime(latency)}</strong> total latency</span>
    <span class="stat"><strong>${debateCount}</strong> debates</span>
    <span class="stat"><strong>${modelCount}</strong> models</span>
  `;

  for (const m of motions) {
    html += `<span class="stat"><strong>${m.topic_id}</strong>: ${m.result} (${m.pro_judges}P/${m.con_judges}C/${m.tie_judges}T)</span>`;
  }

  bar.innerHTML = html;
}

function formatTime(s) {
  if (s < 60) return s.toFixed(1) + 's';
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${m}m${sec}s`;
}

// ── Render Elo table ──
function renderElo() {
  const section = document.getElementById('elo-section');
  const debaters = SUMMARY.models.filter(m => m.elo !== null).sort((a, b) => b.elo - a.elo);
  if (debaters.length === 0) return;

  let html = '<div class="section-title">Debater Rankings</div>';
  html += '<table class="elo-table"><thead><tr><th>Model</th><th style="text-align:right">Elo</th><th style="text-align:right">Cost</th></tr></thead><tbody>';
  for (const m of debaters) {
    html += `<tr><td class="model-name">${m.model_id}</td><td class="elo-val">${m.elo.toFixed(1)}</td><td class="elo-val">$${m.cost_usd.toFixed(4)}</td></tr>`;
  }
  html += '</tbody></table>';
  section.innerHTML = html;
}

// ── Build cross-table matrices ──
function buildMatrix() {
  const topics = [...new Set(SUMMARY.pairs.map(p => p.topic_id))];
  const section = document.getElementById('matrix-section');
  let html = '';

  for (const topic of topics) {
    const pairs = SUMMARY.pairs.filter(p => p.topic_id === topic);
    const models = getOrderedModels(pairs);
    const lookup = {};
    for (const p of pairs) {
      lookup[p.pro_model_id + '|' + p.con_model_id] = p;
    }

    const rowTotals = {};
    const colTotals = {};
    for (const m of models) {
      rowTotals[m] = { pro: 0, con: 0, total: 0 };
      colTotals[m] = { pro: 0, con: 0, total: 0 };
    }
    for (const p of pairs) {
      rowTotals[p.pro_model_id].pro += p.pro_judges;
      rowTotals[p.pro_model_id].con += p.con_judges;
      rowTotals[p.pro_model_id].total += p.pro_judges + p.con_judges;
      colTotals[p.con_model_id].pro += p.pro_judges;
      colTotals[p.con_model_id].con += p.con_judges;
      colTotals[p.con_model_id].total += p.pro_judges + p.con_judges;
    }

    if (topics.length > 1) {
      const motion = findMotion(topic);
      html += `<div class="matrix-topic">${motion || topic}</div>`;
    }
    html += '<div class="section-title">Cross-Table (Pro &#8595; / Con &#8594;)</div>';
    html += '<div class="matrix-wrapper"><table class="matrix">';

    html += '<tr><th class="corner"></th>';
    for (const col of models) {
      html += `<th>${shortName(col)}</th>`;
    }
    html += '<th class="total-header">Total</th></tr>';

    for (const row of models) {
      html += `<tr><th class="row-header">${shortName(row)}</th>`;
      for (const col of models) {
        const key = row + '|' + col;
        const p = lookup[key];
        if (p) {
          const isSelf = row === col;
          const ratio = p.pro_judges + p.con_judges > 0
            ? (p.pro_judges - p.con_judges) / (p.pro_judges + p.con_judges)
            : 0;
          const bg = cellGradient(ratio);
          const cls = isSelf ? 'cell self-debate' : 'cell';
          html += `<td class="${cls}" style="background:${bg}" data-debate="${p.debate_id}" onclick="selectCell(this, '${p.debate_id}')">${p.pro_judges}/${p.con_judges}</td>`;
        } else {
          html += '<td class="cell" style="opacity:0.3">-</td>';
        }
      }
      const rt = rowTotals[row];
      const rRatio = rt.total > 0 ? (rt.pro - rt.con) / rt.total : 0;
      html += `<td class="total-cell" style="background:${cellGradient(rRatio)}">${rt.pro}/${rt.con}</td>`;
      html += '</tr>';
    }

    html += '<tr><th class="row-header total-header">Total</th>';
    for (const col of models) {
      const ct = colTotals[col];
      const cRatio = ct.total > 0 ? (ct.pro - ct.con) / ct.total : 0;
      html += `<td class="total-cell" style="background:${cellGradient(cRatio)}">${ct.pro}/${ct.con}</td>`;
    }
    let grandPro = 0, grandCon = 0;
    for (const p of pairs) { grandPro += p.pro_judges; grandCon += p.con_judges; }
    const gRatio = (grandPro + grandCon) > 0 ? (grandPro - grandCon) / (grandPro + grandCon) : 0;
    html += `<td class="total-cell" style="background:${cellGradient(gRatio)}">${grandPro}/${grandCon}</td>`;
    html += '</tr></table></div>';
  }

  section.innerHTML = html;
}

function findMotion(topicId) {
  if (!ALL_DEBATES) return null;
  for (const d of Object.values(ALL_DEBATES)) {
    if (d.topic && d.topic.id === topicId) return d.topic.motion;
  }
  return null;
}

function getOrderedModels(pairs) {
  const debaters = SUMMARY.models.filter(m => m.elo !== null).sort((a, b) => b.elo - a.elo);
  const ordered = debaters.map(m => m.model_id);
  const allInPairs = new Set();
  for (const p of pairs) {
    allInPairs.add(p.pro_model_id);
    allInPairs.add(p.con_model_id);
  }
  for (const m of allInPairs) {
    if (!ordered.includes(m)) ordered.push(m);
  }
  return ordered.filter(m => allInPairs.has(m));
}

function shortName(id) {
  return id.replace(/_/g, ' ');
}

function cellGradient(ratio) {
  if (ratio > 0) {
    const alpha = Math.min(ratio * 0.5, 0.45);
    return `rgba(34,197,94,${alpha.toFixed(2)})`;
  } else if (ratio < 0) {
    const alpha = Math.min(Math.abs(ratio) * 0.5, 0.45);
    return `rgba(239,68,68,${alpha.toFixed(2)})`;
  }
  return 'transparent';
}

// ── Cell selection and detail loading ──
let selectedCell = null;

function selectCell(el, debateId) {
  if (selectedCell) selectedCell.classList.remove('selected');
  el.classList.add('selected');
  selectedCell = el;
  loadDetail(debateId);

  if (window.innerWidth <= 900) {
    document.getElementById('left-panel').classList.add('hidden');
    document.getElementById('right-panel').classList.add('active');
  } else {
    document.getElementById('right-panel').classList.add('active');
  }
}

function showList() {
  document.getElementById('left-panel').classList.remove('hidden');
  document.getElementById('right-panel').classList.remove('active');
}

async function loadDetail(debateId) {
  const content = document.getElementById('detail-content');

  try {
    let debate, judgements;
    if (ALL_DEBATES) {
      debate = ALL_DEBATES[debateId];
      judgements = ALL_JUDGEMENTS[debateId] || [];
      renderDetail(debate, judgements, content);
    } else {
      content.innerHTML = '<div class="loading">Loading</div>';
      const [debateRes, judgementsRes] = await Promise.all([
        fetch(`/api/debates/${debateId}`),
        fetch(`/api/judgements/${debateId}`)
      ]);
      debate = await debateRes.json();
      judgements = await judgementsRes.json();
      renderDetail(debate, judgements, content);
    }
  } catch (e) {
    content.innerHTML = `<div class="detail-placeholder">Failed to load: ${e.message}</div>`;
  }
}

function renderDetail(debate, judgements, container) {
  let html = '';

  html += '<div class="detail-header">';
  html += `<h2>${escapeHtml(debate.topic.motion)}</h2>`;
  html += `<div class="matchup"><span style="color:var(--pro-color)">PRO: ${debate.pro_model.id}</span> vs <span style="color:var(--con-color)">CON: ${debate.con_model.id}</span> &middot; ${debate.rounds} rounds</div>`;
  html += '</div>';

  html += '<div class="section-title">Judge Verdicts</div>';
  html += '<div class="judge-cards">';
  for (const j of judgements) {
    html += renderJudgeCard(j);
  }
  html += '</div>';

  html += '<div class="transcript">';
  html += '<div class="transcript-title">Debate Transcript</div>';
  for (const turn of debate.turns) {
    const sideClass = turn.side;
    html += `<div class="turn ${sideClass}">`;
    html += '<div class="turn-header">';
    html += `<span class="side-badge ${sideClass}">${turn.side}</span>`;
    html += `<span class="model-label">${turn.speaker_model_id}</span>`;
    html += `<span class="round-label">Round ${turn.turn_number}</span>`;
    html += '</div>';
    html += `<div class="turn-content">${renderMarkdown(turn.content)}</div>`;
    html += '</div>';
  }
  html += '</div>';

  container.innerHTML = html;
}

function renderJudgeCard(j) {
  const parsed = j.parsed || {};
  const winner = parsed.winner || 'unknown';
  const verdictClass = winner === 'pro' ? 'pro' : winner === 'con' ? 'con' : 'tie';

  let html = '<div class="judge-card">';
  html += `<div class="judge-name">${j.judge_model_id}</div>`;
  html += `<span class="verdict ${verdictClass}">${winner}</span>`;

  if (parsed.confidence !== undefined) {
    const pct = parsed.confidence > 1 ? parsed.confidence : parsed.confidence * 100;
    html += ` <span class="confidence">${pct.toFixed(0)}% confidence</span>`;
  }

  if (parsed.pro_score !== undefined && parsed.con_score !== undefined) {
    html += `<div class="scores">Pro: ${parsed.pro_score} &middot; Con: ${parsed.con_score}</div>`;
  }

  if (parsed.summary) {
    html += `<div class="summary-text">${escapeHtml(parsed.summary)}</div>`;
  }

  if (parsed.rubric) {
    html += '<table class="rubric-table"><thead><tr><th>Category</th><th>Pro</th><th>Con</th></tr></thead><tbody>';
    for (const [cat, scores] of Object.entries(parsed.rubric)) {
      html += `<tr><th>${cat.replace(/_/g, ' ')}</th><td class="pro-score">${scores.pro}</td><td class="con-score">${scores.con}</td></tr>`;
    }
    html += '</tbody></table>';
  }

  if (parsed.decisive_reasons && parsed.decisive_reasons.length > 0) {
    html += '<ul class="reasons">';
    for (const r of parsed.decisive_reasons) {
      html += `<li>${escapeHtml(r)}</li>`;
    }
    html += '</ul>';
  }

  html += '</div>';
  return html;
}

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderMarkdown(str) {
  if (!str) return '';
  const escaped = escapeHtml(str);
  const lines = escaped.split('\n');
  let html = '';
  let inList = false;
  let listType = '';

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    if (/^---+$/.test(line.trim())) {
      if (inList) { html += `</${listType}>`; inList = false; }
      html += '<hr>';
      continue;
    }

    const hMatch = line.match(/^(#{1,4})\s+(.+)/);
    if (hMatch) {
      if (inList) { html += `</${listType}>`; inList = false; }
      const level = hMatch[1].length;
      html += `<h${level}>${inlineMd(hMatch[2])}</h${level}>`;
      continue;
    }

    const ulMatch = line.match(/^(\s*)[-*]\s+(.+)/);
    if (ulMatch) {
      if (!inList || listType !== 'ul') {
        if (inList) html += `</${listType}>`;
        html += '<ul>';
        inList = true;
        listType = 'ul';
      }
      html += `<li>${inlineMd(ulMatch[2])}</li>`;
      continue;
    }

    const olMatch = line.match(/^(\s*)\d+\.\s+(.+)/);
    if (olMatch) {
      if (!inList || listType !== 'ol') {
        if (inList) html += `</${listType}>`;
        html += '<ol>';
        inList = true;
        listType = 'ol';
      }
      html += `<li>${inlineMd(olMatch[2])}</li>`;
      continue;
    }

    if (inList && line.trim() === '') {
      html += `</${listType}>`;
      inList = false;
      continue;
    }
    if (inList) {
      html += `</${listType}>`;
      inList = false;
    }

    if (line.trim() === '') continue;

    html += `<p>${inlineMd(line)}</p>`;
  }

  if (inList) html += `</${listType}>`;
  return html;
}

function inlineMd(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>');
}

// ── Init ──
renderStats();
renderElo();
buildMatrix();

if (window.innerWidth > 900) {
  document.getElementById('right-panel').classList.add('active');
}
</script>
</body>
</html>
"""
