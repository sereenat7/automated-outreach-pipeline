import sys
import threading
import uuid
from copy import deepcopy
from pathlib import Path

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline_runner import run_pipeline, send_to_contacts, validate_config

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)

jobs: dict[str, dict] = {}


def _append_log(job_id: str, message: str, level: str = "info") -> None:
    jobs[job_id]["logs"].append({"message": message, "level": level})


def _run_job(job_id: str, domain: str, limit: int, dry_run: bool) -> None:
    try:
        result = run_pipeline(
            domain,
            limit=limit,
            dry_run=dry_run,
            send=False,
            on_log=lambda msg, level: _append_log(job_id, msg, level),
        )
        jobs[job_id]["result"] = result
        jobs[job_id]["status"] = "done" if result.get("ok") else "error"
        if not result.get("ok"):
            jobs[job_id]["error"] = result.get("error", "Pipeline failed.")
    except Exception as exc:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(exc)
        _append_log(job_id, str(exc), "error")


def _send_job(job_id: str, contacts: list[dict]) -> None:
    try:
        result = send_to_contacts(
            contacts,
            on_log=lambda msg, level: _append_log(job_id, msg, level),
        )
        jobs[job_id]["send_result"] = result
        jobs[job_id]["status"] = "sent" if result.get("ok") else "error"
        if not result.get("ok"):
            jobs[job_id]["error"] = result.get("error", "Send failed.")
    except Exception as exc:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(exc)
        _append_log(job_id, str(exc), "error")


@app.get("/")
def index():
    missing = validate_config()
    return render_template("index.html", config_ok=len(missing) == 0, missing=missing)


@app.post("/api/run")
def api_run():
    data = request.get_json(silent=True) or {}
    domain = (data.get("domain") or "").strip()
    limit = int(data.get("limit") or 10)
    dry_run = bool(data.get("dry_run", True))

    if not domain:
        return jsonify({"ok": False, "error": "Domain is required."}), 400

    missing = validate_config()
    if missing:
        return jsonify({"ok": False, "error": f"Missing: {', '.join(missing)}"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "running",
        "logs": [],
        "result": None,
        "send_result": None,
        "error": None,
    }

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, domain, limit, dry_run),
        daemon=True,
    )
    thread.start()
    return jsonify({"ok": True, "job_id": job_id})


@app.get("/api/status/<job_id>")
def api_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job not found."}), 404
    return jsonify({"ok": True, **deepcopy(job)})


@app.post("/api/send/<job_id>")
def api_send(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job not found."}), 404

    result = job.get("result") or {}
    contacts = result.get("contacts") or []
    if not contacts:
        return jsonify({"ok": False, "error": "No contacts to send."}), 400

    if result.get("dry_run"):
        return jsonify({"ok": False, "error": "This was a dry run. Re-run without dry-run to send."}), 400

    job["status"] = "sending"
    thread = threading.Thread(
        target=_send_job,
        args=(job_id, contacts),
        daemon=True,
    )
    thread.start()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
