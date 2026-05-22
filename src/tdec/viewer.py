"""FastAPI viewer server and standalone HTML export for TDEC run results."""

from __future__ import annotations

import json
import socket
import webbrowser
from pathlib import Path

import jinja2
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

_PKG_DIR = Path(__file__).parent
_TEMPLATES_DIR = _PKG_DIR / "templates"
_STATIC_DIR = _PKG_DIR / "static"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _load_all_debates(run_dir: Path) -> dict:
    result = {}
    for f in sorted((run_dir / "debates").glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        result[data["id"]] = data
    return result


def _load_all_judgements(run_dir: Path) -> dict:
    result: dict[str, list] = {}
    for f in sorted((run_dir / "judgements").glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        result.setdefault(data["debate_id"], []).append(data)
    return result


def _extract_topic_motions(run_dir: Path) -> dict:
    result = {}
    for f in (run_dir / "debates").glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        topic = data.get("topic", {})
        tid = topic.get("id")
        if tid and tid not in result:
            result[tid] = {
                "motion": topic.get("motion", tid),
                "context": topic.get("context"),
            }
    return result


def _compute_judge_stats(run_dir: Path) -> dict:
    judgements = []
    for f in sorted((run_dir / "judgements").glob("*.json")):
        judgements.append(json.loads(f.read_text(encoding="utf-8")))

    debates = {}
    for f in sorted((run_dir / "debates").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        debates[d["id"]] = d

    judge_ids = sorted({j["judge_model_id"] for j in judgements})
    debater_ids = sorted({d["pro_model"]["id"] for d in debates.values()}
                         | {d["con_model"]["id"] for d in debates.values()})

    per_judge: dict[str, dict] = {}
    for jid in judge_ids:
        per_judge[jid] = {"total": 0, "pro": 0, "con": 0, "tie": 0, "parse_error": 0}

    judge_debater: dict[str, dict[str, dict]] = {}
    for jid in judge_ids:
        judge_debater[jid] = {}
        for did in debater_ids:
            judge_debater[jid][did] = {"voted_for": 0, "total": 0}

    judge_pairs: dict[str, list] = {}
    for debate_id in debates:
        debate_judges = [j for j in judgements if j["debate_id"] == debate_id]
        for j in debate_judges:
            jid = j["judge_model_id"]
            winner = (j.get("parsed") or {}).get("winner", "parse_error")
            per_judge[jid]["total"] += 1
            per_judge[jid][winner] = per_judge[jid].get(winner, 0) + 1

            debate = debates[debate_id]
            pro_id = debate["pro_model"]["id"]
            con_id = debate["con_model"]["id"]
            if pro_id != con_id:
                judge_debater[jid][pro_id]["total"] += 1
                judge_debater[jid][con_id]["total"] += 1
                if winner == "pro":
                    judge_debater[jid][pro_id]["voted_for"] += 1
                elif winner == "con":
                    judge_debater[jid][con_id]["voted_for"] += 1

        for i, ja in enumerate(debate_judges):
            for jb in debate_judges[i + 1:]:
                key = "|".join(sorted([ja["judge_model_id"], jb["judge_model_id"]]))
                judge_pairs.setdefault(key, [])
                wa = (ja.get("parsed") or {}).get("winner")
                wb = (jb.get("parsed") or {}).get("winner")
                if wa and wb and wa != "parse_error" and wb != "parse_error":
                    judge_pairs[key].append(1 if wa == wb else 0)

    agreement = {}
    for key, votes in judge_pairs.items():
        if votes:
            agreement[key] = {
                "agreed": sum(votes),
                "total": len(votes),
                "pct": round(100 * sum(votes) / len(votes), 1),
            }

    return {
        "judge_ids": judge_ids,
        "debater_ids": debater_ids,
        "per_judge": per_judge,
        "judge_debater": judge_debater,
        "agreement": agreement,
    }


def _compute_word_counts(run_dir: Path) -> dict:
    debate_words = 0
    judgement_words = 0
    for f in (run_dir / "debates").glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        for turn in data.get("turns", []):
            debate_words += len(turn.get("content", "").split())
    for f in (run_dir / "judgements").glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        judgement_words += len(data.get("raw_text", "").split())
    return {"debate_words": debate_words, "judgement_words": judgement_words}


def _jinja_env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=False,
    )


# ── Server mode ──


def serve(run_dir: Path, port: int | None = None, *, open_browser: bool = True) -> None:
    import uvicorn

    if port is None:
        port = _find_free_port()

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    debates_dir = run_dir / "debates"
    judgements_dir = run_dir / "judgements"
    css_text = _STATIC_DIR.joinpath("viewer.css").read_text(encoding="utf-8")
    topic_motions = _extract_topic_motions(run_dir)
    word_counts = _compute_word_counts(run_dir)
    judge_stats = _compute_judge_stats(run_dir)
    env = _jinja_env()
    template = env.get_template("viewer.html")

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return template.render(
            run_name=run_dir.name,
            summary=json.dumps(summary),
            all_debates="null",
            all_judgements="null",
            topic_motions=json.dumps(topic_motions),
            word_counts=json.dumps(word_counts),
            judge_stats=json.dumps(judge_stats),
            inline_css=None,
        )

    @app.get("/static/viewer.css")
    async def static_css():
        return Response(content=css_text, media_type="text/css")

    @app.get("/api/summary")
    async def api_summary():
        return JSONResponse(summary)

    @app.get("/api/debates/{debate_id}")
    async def api_debate(debate_id: str):
        path = debates_dir / f"{debate_id}.json"
        if not path.exists():
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(json.loads(path.read_text(encoding="utf-8")))

    @app.get("/api/judgements/{debate_id}")
    async def api_judgements(debate_id: str):
        files = sorted(judgements_dir.glob(f"{debate_id}__*.json"))
        results = [json.loads(f.read_text(encoding="utf-8")) for f in files]
        return JSONResponse(results)

    url = f"http://127.0.0.1:{port}"
    print(f"Serving {run_dir.name} at {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


# ── Export mode ──


def export_html(run_dir: Path, output: Path) -> None:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    debates = _load_all_debates(run_dir)
    judgements = _load_all_judgements(run_dir)
    css = _STATIC_DIR.joinpath("viewer.css").read_text(encoding="utf-8")

    env = _jinja_env()
    template = env.get_template("viewer.html")
    topic_motions = _extract_topic_motions(run_dir)
    word_counts = _compute_word_counts(run_dir)
    judge_stats = _compute_judge_stats(run_dir)
    html = template.render(
        run_name=run_dir.name,
        summary=json.dumps(summary),
        all_debates=json.dumps(debates),
        all_judgements=json.dumps(judgements),
        topic_motions=json.dumps(topic_motions),
        word_counts=json.dumps(word_counts),
        judge_stats=json.dumps(judge_stats),
        inline_css=css,
    )
    output.write_text(html, encoding="utf-8")
