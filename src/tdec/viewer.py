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
    from scipy.stats import binomtest

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
            "p_value": float(bt.pvalue),
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

    n_median = int(float(np.median(judges_per_debate))) if judges_per_debate else 0
    n_total = total_decided

    if n_total > 0:
        se = math.sqrt(0.5 * 0.5 / n_total)
        mde = round(100 * 2.8 * se, 1)
        judges_for_5pct = max(1, math.ceil(((2.8 * 0.5) / (0.05)) ** 2 / len(debates))) if debates else 0
    else:
        mde = 0
        judges_for_5pct = 0

    power_info = {
        "median_judges_per_debate": n_median,
        "total_observations": n_total,
        "total_debates": len(debates),
        "min_detectable_effect_pct": mde,
        "judges_for_5pct_mde": judges_for_5pct,
    }

    # ── Section 5: ANOVA (model x topic) ──
    from scipy.stats import f as f_dist

    anova = None
    topic_ids = sorted({d["topic"]["id"] for d in debates.values()})
    if len(topic_ids) > 1 and len(debater_ids) > 1:
        scores_by_cell: dict[tuple[str, str], list[float]] = {}
        for j in judgements:
            debate = debates.get(j["debate_id"])
            if not debate:
                continue
            parsed = j.get("parsed") or {}
            pro_score = parsed.get("pro_score")
            con_score = parsed.get("con_score")
            if pro_score is None or con_score is None:
                continue
            pro_id = debate["pro_model"]["id"]
            con_id = debate["con_model"]["id"]
            if pro_id == con_id:
                continue
            tid = debate["topic"]["id"]
            margin = pro_score - con_score
            scores_by_cell.setdefault((pro_id, tid), []).append(margin)

        all_margins = []
        for vals in scores_by_cell.values():
            all_margins.extend(vals)

        if len(all_margins) >= 4:
            grand_mean = float(np.mean(all_margins))
            n_obs = len(all_margins)

            model_means = {}
            for mid in debater_ids:
                vals = [v for (m, t), vs in scores_by_cell.items() if m == mid for v in vs]
                if vals:
                    model_means[mid] = float(np.mean(vals))

            topic_means = {}
            for tid in topic_ids:
                vals = [v for (m, t), vs in scores_by_cell.items() if t == tid for v in vs]
                if vals:
                    topic_means[tid] = float(np.mean(vals))

            ss_model = sum(
                len([v for (m, t), vs in scores_by_cell.items() if m == mid for v in vs])
                * (model_means.get(mid, grand_mean) - grand_mean) ** 2
                for mid in debater_ids if mid in model_means
            )
            ss_topic = sum(
                len([v for (m, t), vs in scores_by_cell.items() if t == tid for v in vs])
                * (topic_means.get(tid, grand_mean) - grand_mean) ** 2
                for tid in topic_ids if tid in topic_means
            )

            ss_total = float(np.sum((np.array(all_margins) - grand_mean) ** 2))
            ss_residual = max(ss_total - ss_model - ss_topic, 0.001)

            df_model = max(len(model_means) - 1, 1)
            df_topic = max(len(topic_means) - 1, 1)
            df_residual = max(n_obs - df_model - df_topic - 1, 1)

            ms_model = ss_model / df_model
            ms_topic = ss_topic / df_topic
            ms_residual = ss_residual / df_residual

            f_model = ms_model / ms_residual
            f_topic = ms_topic / ms_residual
            p_model = float(f_dist.sf(f_model, df_model, df_residual))
            p_topic = float(f_dist.sf(f_topic, df_topic, df_residual))

            pct_model = round(100 * ss_model / ss_total, 1) if ss_total > 0 else 0
            pct_topic = round(100 * ss_topic / ss_total, 1) if ss_total > 0 else 0
            pct_residual = round(100 * ss_residual / ss_total, 1) if ss_total > 0 else 0

            anova = {
                "response": "Score margin (pro_score - con_score)",
                "rows": [
                    {
                        "source": "Model (pro)",
                        "ss": round(ss_model, 1),
                        "df": df_model,
                        "ms": round(ms_model, 1),
                        "f": round(f_model, 2),
                        "p_value": p_model,
                        "pct_variance": pct_model,
                        "significant": bool(p_model < 0.05),
                    },
                    {
                        "source": "Topic",
                        "ss": round(ss_topic, 1),
                        "df": df_topic,
                        "ms": round(ms_topic, 1),
                        "f": round(f_topic, 2),
                        "p_value": p_topic,
                        "pct_variance": pct_topic,
                        "significant": bool(p_topic < 0.05),
                    },
                    {
                        "source": "Residual",
                        "ss": round(ss_residual, 1),
                        "df": df_residual,
                        "ms": round(ms_residual, 1),
                        "f": None,
                        "p_value": None,
                        "pct_variance": pct_residual,
                        "significant": None,
                    },
                ],
            }

    return {
        "side_bias": side_bias,
        "model_strength": model_strength,
        "rubric_profiles": rubric_profiles,
        "rubric_categories": categories,
        "power": power_info,
        "anova": anova,
    }


def _compute_cross_run_analysis(runs: list[dict], run_dirs: list[Path]) -> dict | None:
    import numpy as np
    from scipy.stats import f as f_dist

    if len(runs) < 2:
        return None

    all_condition_keys = set()
    for r in runs:
        all_condition_keys.update(r["summary"].get("conditions", {}).keys())

    all_conditions = {}
    for k in all_condition_keys:
        vals = set()
        for r in runs:
            vals.add(r["summary"].get("conditions", {}).get(k, "false" if k == "label_swap" else ""))
        all_conditions[k] = vals

    varying = {k: sorted(v) for k, v in all_conditions.items() if len(v) > 1}
    if not varying:
        return {"varying_conditions": {}, "anova": None, "note": "No varying conditions across runs."}

    observations = []
    for r, rd in zip(runs, run_dirs):
        conds = r["summary"].get("conditions", {})
        debates = {}
        for f in sorted((rd / "debates").glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            debates[d["id"]] = d
        for f in sorted((rd / "judgements").glob("*.json")):
            j = json.loads(f.read_text(encoding="utf-8"))
            parsed = j.get("parsed") or {}
            pro_score = parsed.get("pro_score")
            con_score = parsed.get("con_score")
            if pro_score is None or con_score is None:
                continue
            debate = debates.get(j["debate_id"])
            if not debate:
                continue
            pro_id = debate["pro_model"]["id"]
            con_id = debate["con_model"]["id"]
            if pro_id == con_id:
                continue
            margin = pro_score - con_score
            if conds.get("motion_polarity") == "negative":
                margin = -margin
            obs = {
                "margin": margin,
                "pro_model": pro_id,
                "run": r["run_name"],
            }
            for k in all_condition_keys:
                obs[k] = conds.get(k, "false" if k == "label_swap" else "")
            obs.update(conds)
            observations.append(obs)

    if len(observations) < 4:
        return {"varying_conditions": {k: list(v) for k, v in varying.items()}, "anova": None}

    margins = np.array([o["margin"] for o in observations])
    grand_mean = float(margins.mean())
    ss_total = float(np.sum((margins - grand_mean) ** 2))

    anova_rows = []
    for factor_name, levels in varying.items():
        ss = 0.0
        for level in levels:
            group = [o["margin"] for o in observations if o.get(factor_name) == level]
            if group:
                group_mean = np.mean(group)
                ss += len(group) * (group_mean - grand_mean) ** 2
        df = len(levels) - 1
        if df > 0 and ss_total > 0:
            anova_rows.append({
                "source": factor_name,
                "ss": round(float(ss), 1),
                "df": df,
                "pct_variance": round(100 * float(ss) / ss_total, 1),
                "_ss": float(ss),
            })

    ss_explained = sum(r["_ss"] for r in anova_rows)
    ss_residual = max(ss_total - ss_explained, 0.001)
    df_residual = max(len(observations) - sum(r["df"] for r in anova_rows) - 1, 1)
    ms_residual = ss_residual / df_residual

    for row in anova_rows:
        ms = row["_ss"] / row["df"]
        f_val = ms / ms_residual
        p_val = float(f_dist.sf(f_val, row["df"], df_residual))
        row["ms"] = round(ms, 1)
        row["f"] = round(f_val, 2)
        row["p_value"] = p_val
        row["significant"] = bool(p_val < 0.05)
        del row["_ss"]

    anova_rows.append({
        "source": "Residual",
        "ss": round(ss_residual, 1),
        "df": df_residual,
        "ms": round(ms_residual, 1),
        "f": None,
        "p_value": None,
        "pct_variance": round(100 * ss_residual / ss_total, 1) if ss_total > 0 else 0,
        "significant": None,
    })

    judge_ids = sorted({
        j.get("judge_model_id", "")
        for r, rd in zip(runs, run_dirs)
        for f in (rd / "judgements").glob("*.json")
        for j in [json.loads(f.read_text(encoding="utf-8"))]
        if j.get("judge_model_id")
    })

    breakdowns = {}
    for factor_name, levels in varying.items():
        rows_bd = []
        for level in levels:
            pro = 0
            con = 0
            per_judge: dict[str, dict[str, int]] = {jid: {"pro": 0, "con": 0} for jid in judge_ids}
            for r, rd in zip(runs, run_dirs):
                conds = r["summary"].get("conditions", {})
                cond_val = conds.get(factor_name, "false" if factor_name == "label_swap" else "")
                if cond_val != level:
                    continue
                is_negative = conds.get("motion_polarity") == "negative"
                for f in (rd / "judgements").glob("*.json"):
                    j = json.loads(f.read_text(encoding="utf-8"))
                    winner = (j.get("parsed") or {}).get("winner")
                    if winner not in ("pro", "con"):
                        continue
                    if is_negative:
                        winner = "con" if winner == "pro" else "pro"
                    if winner == "pro":
                        pro += 1
                    else:
                        con += 1
                    jid = j["judge_model_id"]
                    if jid in per_judge:
                        per_judge[jid]["pro" if winner == "pro" else "con"] += 1

            total = pro + con
            rows_bd.append({
                "level": level,
                "pro": pro,
                "con": con,
                "total": total,
                "pro_pct": round(100 * pro / total, 1) if total else 0,
                "per_judge": per_judge,
            })
        breakdowns[factor_name] = rows_bd

    return {
        "varying_conditions": {k: list(v) for k, v in varying.items()},
        "run_count": len(runs),
        "run_names": [r["run_name"] for r in runs],
        "judge_ids": judge_ids,
        "breakdowns": breakdowns,
        "anova": {
            "response": "Score margin (pro_score - con_score) across all runs",
            "n_observations": len(observations),
            "rows": anova_rows,
        },
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


def _load_run_data(run_dir: Path) -> dict:
    return {
        "run_name": run_dir.name,
        "summary": json.loads((run_dir / "summary.json").read_text(encoding="utf-8")),
        "topic_motions": _extract_topic_motions(run_dir),
        "word_counts": _compute_word_counts(run_dir),
        "judge_stats": _compute_judge_stats(run_dir),
        "motion_stats": _compute_motion_stats(run_dir),
        "analysis_stats": _compute_analysis_stats(run_dir),
    }


def serve(
    run_dir_or_dirs: Path | list[Path],
    port: int | None = None,
    *,
    open_browser: bool = True,
) -> None:
    import uvicorn

    if port is None:
        port = _find_free_port()

    if isinstance(run_dir_or_dirs, list):
        run_dirs = run_dir_or_dirs
    else:
        run_dirs = [run_dir_or_dirs]

    runs = [_load_run_data(rd) for rd in run_dirs]
    active_run = runs[0]
    cross_run = _compute_cross_run_analysis(runs, run_dirs)
    all_debates_dirs = {rd.name: rd / "debates" for rd in run_dirs}
    all_judgements_dirs = {rd.name: rd / "judgements" for rd in run_dirs}

    css_text = _STATIC_DIR.joinpath("viewer.css").read_text(encoding="utf-8")
    env = _jinja_env()
    template = env.get_template("viewer.html")

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return template.render(
            run_name=active_run["run_name"],
            summary=json.dumps(active_run["summary"]),
            all_debates="null",
            all_judgements="null",
            topic_motions=json.dumps(active_run["topic_motions"]),
            word_counts=json.dumps(active_run["word_counts"]),
            judge_stats=json.dumps(active_run["judge_stats"]),
            motion_stats=json.dumps(active_run["motion_stats"]),
            analysis_stats=json.dumps(active_run["analysis_stats"]),
            runs=json.dumps([{
                "run_name": r["run_name"],
                "conditions": r["summary"].get("conditions", {}),
            } for r in runs]),
            cross_run=json.dumps(cross_run),
            inline_css=None,
        )

    @app.get("/static/viewer.css")
    async def static_css():
        return Response(content=css_text, media_type="text/css")

    @app.get("/api/run/{run_name}")
    async def api_run(run_name: str):
        for r in runs:
            if r["run_name"] == run_name:
                return JSONResponse({
                    "summary": r["summary"],
                    "topic_motions": r["topic_motions"],
                    "word_counts": r["word_counts"],
                    "judge_stats": r["judge_stats"],
                    "motion_stats": r["motion_stats"],
                    "analysis_stats": r["analysis_stats"],
                })
        return JSONResponse({"error": "not found"}, status_code=404)

    @app.get("/api/debates/{run_name}/{debate_id}")
    async def api_debate(run_name: str, debate_id: str):
        debates_dir = all_debates_dirs.get(run_name)
        if not debates_dir:
            return JSONResponse({"error": "run not found"}, status_code=404)
        path = debates_dir / f"{debate_id}.json"
        if not path.exists():
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(json.loads(path.read_text(encoding="utf-8")))

    @app.get("/api/judgements/{run_name}/{debate_id}")
    async def api_judgements(run_name: str, debate_id: str):
        judgements_dir = all_judgements_dirs.get(run_name)
        if not judgements_dir:
            return JSONResponse({"error": "run not found"}, status_code=404)
        files = sorted(judgements_dir.glob(f"{debate_id}__*.json"))
        results = [json.loads(f.read_text(encoding="utf-8")) for f in files]
        return JSONResponse(results)

    url = f"http://127.0.0.1:{port}"
    names = ", ".join(rd.name for rd in run_dirs)
    print(f"Serving {names} at {url}")
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
        runs=json.dumps([{"run_name": run_dir.name, "conditions": summary.get("conditions", {})}]),
        cross_run=json.dumps(None),
        inline_css=css,
    )
    output.write_text(html, encoding="utf-8")
