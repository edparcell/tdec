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
                "pro_position": topic.get("pro_position"),
                "con_position": topic.get("con_position"),
            }
    return result


def _jinja_env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=False,
    )


# ── Server mode ──


def serve(run_dir: Path, port: int | None = None) -> None:
    import uvicorn

    if port is None:
        port = _find_free_port()

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    debates_dir = run_dir / "debates"
    judgements_dir = run_dir / "judgements"
    css_text = _STATIC_DIR.joinpath("viewer.css").read_text(encoding="utf-8")
    topic_motions = _extract_topic_motions(run_dir)
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
    html = template.render(
        run_name=run_dir.name,
        summary=json.dumps(summary),
        all_debates=json.dumps(debates),
        all_judgements=json.dumps(judgements),
        topic_motions=json.dumps(topic_motions),
        inline_css=css,
    )
    output.write_text(html, encoding="utf-8")
