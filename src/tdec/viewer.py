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


def _compute_motion_stats(run_dir: Path) -> list[dict]:
    judgements = []
    for f in sorted((run_dir / "judgements").glob("*.json")):
        judgements.append(json.loads(f.read_text(encoding="utf-8")))

    debates = {}
    for f in sorted((run_dir / "debates").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        debates[d["id"]] = d

    topic_ids = []
    for d in debates.values():
        tid = d["topic"]["id"]
        if tid not in topic_ids:
            topic_ids.append(tid)

    judge_ids = sorted({j["judge_model_id"] for j in judgements})

    rows = []
    for tid in topic_ids:
        topic_debates = {did: d for did, d in debates.items() if d["topic"]["id"] == tid}
        topic_judgements = [j for j in judgements if j["debate_id"] in topic_debates]

        pro = sum(1 for j in topic_judgements if (j.get("parsed") or {}).get("winner") == "pro")
        con = sum(1 for j in topic_judgements if (j.get("parsed") or {}).get("winner") == "con")
        tie = sum(1 for j in topic_judgements if (j.get("parsed") or {}).get("winner") == "tie")

        per_judge = {}
        for jid in judge_ids:
            jj = [j for j in topic_judgements if j["judge_model_id"] == jid]
            jp = sum(1 for j in jj if (j.get("parsed") or {}).get("winner") == "pro")
            jc = sum(1 for j in jj if (j.get("parsed") or {}).get("winner") == "con")
            per_judge[jid] = {"pro": jp, "con": jc, "total": len(jj)}

        motion_text = ""
        for d in topic_debates.values():
            motion_text = d["topic"].get("motion", tid)
            break

        total = pro + con + tie
        result = "carried" if pro > con else "defeated" if con > pro else "tied"
        rows.append({
            "topic_id": tid,
            "motion": motion_text,
            "result": result,
            "pro": pro,
            "con": con,
            "tie": tie,
            "total": total,
            "pro_pct": round(100 * pro / total, 1) if total else 0,
            "per_judge": per_judge,
        })

    return {"judge_ids": judge_ids, "motions": rows}


def _compute_analysis_stats(run_dir: Path) -> dict:
    import math

    import numpy as np
    from scipy.stats import binomtest, chi2_contingency

    judgements = []
    for f in sorted((run_dir / "judgements").glob("*.json")):
        judgements.append(json.loads(f.read_text(encoding="utf-8")))

    debates = {}
    for f in sorted((run_dir / "debates").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        debates[d["id"]] = d

    # ── Section 1: Side bias ──
    pro_wins = sum(1 for j in judgements if (j.get("parsed") or {}).get("winner") == "pro")
    con_wins = sum(1 for j in judgements if (j.get("parsed") or {}).get("winner") == "con")
    total_decided = pro_wins + con_wins

    if total_decided > 0:
        bt = binomtest(pro_wins, total_decided, 0.5)
        ci = bt.proportion_ci(method="wilson")
        side_bias = {
            "pro_wins": pro_wins,
            "con_wins": con_wins,
            "total": total_decided,
            "pro_pct": round(100 * pro_wins / total_decided, 1),
            "p_value": max(round(float(bt.pvalue), 4), 0.0001),
            "ci_low": round(100 * ci.low, 1),
            "ci_high": round(100 * ci.high, 1),
            "significant": bool(bt.pvalue < 0.05),
        }
    else:
        side_bias = None

    # ── Section 2: Model win rates with CIs ──
    debater_ids = sorted({
        d["pro_model"]["id"] for d in debates.values()
    } | {
        d["con_model"]["id"] for d in debates.values()
    })

    model_strength = []
    for mid in debater_ids:
        wins = 0
        total = 0
        for j in judgements:
            debate = debates.get(j["debate_id"])
            if not debate:
                continue
            pro_id = debate["pro_model"]["id"]
            con_id = debate["con_model"]["id"]
            if pro_id == con_id:
                continue
            winner = (j.get("parsed") or {}).get("winner")
            if winner not in ("pro", "con"):
                continue
            if mid == pro_id:
                total += 1
                if winner == "pro":
                    wins += 1
            elif mid == con_id:
                total += 1
                if winner == "con":
                    wins += 1

        if total > 0:
            bt = binomtest(wins, total)
            ci = bt.proportion_ci(method="wilson")
            model_strength.append({
                "model_id": mid,
                "wins": wins,
                "total": total,
                "win_pct": round(100 * wins / total, 1),
                "ci_low": round(100 * ci.low, 1),
                "ci_high": round(100 * ci.high, 1),
            })

    model_strength.sort(key=lambda m: m["win_pct"], reverse=True)

    # ── Section 3: Rubric profiles ──
    categories = [
        "breadth", "responsiveness", "evidence_quality",
        "moral_reasoning", "institutional_reasoning", "strategic_clarity",
    ]
    rubric_scores: dict[str, dict[str, list]] = {mid: {c: [] for c in categories} for mid in debater_ids}

    for j in judgements:
        debate = debates.get(j["debate_id"])
        if not debate:
            continue
        parsed = j.get("parsed") or {}
        rubric = parsed.get("rubric") or {}
        pro_id = debate["pro_model"]["id"]
        con_id = debate["con_model"]["id"]
        for cat in categories:
            scores = rubric.get(cat)
            if not isinstance(scores, dict):
                continue
            if scores.get("pro") is not None and pro_id in rubric_scores:
                rubric_scores[pro_id][cat].append(scores["pro"])
            if scores.get("con") is not None and con_id in rubric_scores:
                rubric_scores[con_id][cat].append(scores["con"])

    rubric_profiles = []
    for mid in debater_ids:
        profile = {"model_id": mid, "scores": {}}
        for cat in categories:
            vals = rubric_scores[mid][cat]
            profile["scores"][cat] = round(float(np.mean(vals)), 2) if vals else None
        rubric_profiles.append(profile)

    # ── Section 4: Power ──
    judges_per_debate = []
    for did in debates:
        n = sum(1 for j in judgements if j["debate_id"] == did)
        if n > 0:
            judges_per_debate.append(n)

    avg_judges = round(float(np.mean(judges_per_debate)), 1) if judges_per_debate else 0
    n_median = int(float(np.median(judges_per_debate))) if judges_per_debate else 0

    if total_decided > 0 and n_median > 0:
        p_hat = pro_wins / total_decided
        se = math.sqrt(p_hat * (1 - p_hat) / n_median)
        mde = round(100 * 1.96 * se * 2, 1) if se > 0 else 0
    else:
        mde = 0

    power_info = {
        "avg_judges_per_debate": avg_judges,
        "median_judges_per_debate": n_median,
        "min_detectable_effect_pct": mde,
    }

    # ── Section 5: Topic variability ──
    topic_variability = None
    topic_ids = sorted({d["topic"]["id"] for d in debates.values()})
    if len(topic_ids) > 1:
        topic_pro_pcts = []
        topic_labels = []
        for tid in topic_ids:
            tp = sum(
                1 for j in judgements
                if debates.get(j["debate_id"], {}).get("topic", {}).get("id") == tid
                and (j.get("parsed") or {}).get("winner") == "pro"
            )
            tc = sum(
                1 for j in judgements
                if debates.get(j["debate_id"], {}).get("topic", {}).get("id") == tid
                and (j.get("parsed") or {}).get("winner") == "con"
            )
            tt = tp + tc
            if tt > 0:
                topic_pro_pcts.append(100 * tp / tt)
                motion = ""
                for d in debates.values():
                    if d["topic"]["id"] == tid:
                        motion = d["topic"].get("motion", tid)
                        break
                topic_labels.append({"topic_id": tid, "motion": motion, "pro_pct": round(100 * tp / tt, 1)})

        if topic_pro_pcts:
            arr = np.array(topic_pro_pcts)
            most_pro = max(topic_labels, key=lambda t: t["pro_pct"])
            most_con = min(topic_labels, key=lambda t: t["pro_pct"])

            chi2_result = None
            try:
                table = []
                for tid in topic_ids:
                    tp = sum(
                        1 for j in judgements
                        if debates.get(j["debate_id"], {}).get("topic", {}).get("id") == tid
                        and (j.get("parsed") or {}).get("winner") == "pro"
                    )
                    tc = sum(
                        1 for j in judgements
                        if debates.get(j["debate_id"], {}).get("topic", {}).get("id") == tid
                        and (j.get("parsed") or {}).get("winner") == "con"
                    )
                    if tp + tc > 0:
                        table.append([tp, tc])
                if len(table) >= 2:
                    res = chi2_contingency(table)
                    chi2_result = {
                        "statistic": round(float(res.statistic), 2),
                        "p_value": round(float(res.pvalue), 4),
                        "significant": bool(float(res.pvalue) < 0.05),
                    }
            except Exception:
                pass

            topic_variability = {
                "range_low": round(float(arr.min()), 1),
                "range_high": round(float(arr.max()), 1),
                "std": round(float(arr.std()), 1),
                "most_pro": most_pro,
                "most_con": most_con,
                "chi2": chi2_result,
            }

    return {
        "side_bias": side_bias,
        "model_strength": model_strength,
        "rubric_profiles": rubric_profiles,
        "rubric_categories": categories,
        "power": power_info,
        "topic_variability": topic_variability,
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
    motion_stats = _compute_motion_stats(run_dir)
    analysis_stats = _compute_analysis_stats(run_dir)
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
            motion_stats=json.dumps(motion_stats),
            analysis_stats=json.dumps(analysis_stats),
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
    motion_stats = _compute_motion_stats(run_dir)
    analysis_stats = _compute_analysis_stats(run_dir)
    html = template.render(
        run_name=run_dir.name,
        summary=json.dumps(summary),
        all_debates=json.dumps(debates),
        all_judgements=json.dumps(judgements),
        topic_motions=json.dumps(topic_motions),
        word_counts=json.dumps(word_counts),
        judge_stats=json.dumps(judge_stats),
        motion_stats=json.dumps(motion_stats),
        analysis_stats=json.dumps(analysis_stats),
        inline_css=css,
    )
    output.write_text(html, encoding="utf-8")
