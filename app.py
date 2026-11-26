import csv
import json
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd
from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from analysis import analyze_dataframe, csv_preview
from reports import create_pdf_report


ROOT = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("PATTERNIQ_DATABASE", ROOT / "instance" / "patterniq.sqlite3"))
MAX_FILE_BYTES = 16 * 1024 * 1024
ALLOWED_EXTENSION = ".csv"
MAX_ROWS = 100_000
MAX_COLUMNS = 100
MAX_CELLS = 1_000_000
MAX_FIELD_BYTES = 1_000_000


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("PATTERNIQ_SECRET_KEY") or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=MAX_FILE_BYTES,
        DATABASE=str(DATABASE),
    )
    if test_config:
        app.config.update(test_config)
    init_database(app.config["DATABASE"])

    @app.errorhandler(RequestEntityTooLarge)
    def file_too_large(_error):
        flash("That file exceeds the 16 MB upload limit.", "error")
        return redirect(url_for("upload_page")), 413

    @app.route("/")
    def home():
        return render_template("home.html", page="home", recent_scans=recent_scans(app.config["DATABASE"], 3))

    @app.route("/dashboard")
    def dashboard():
        scans = recent_scans(app.config["DATABASE"], 8)
        return render_template("dashboard.html", page="dashboard", scans=scans, total_scans=count_scans(app.config["DATABASE"]))

    @app.route("/upload", methods=["GET", "POST"])
    def upload_page():
        if request.method == "GET":
            return render_template("upload.html", page="upload")
        file = request.files.get("dataset")
        if not file or not file.filename:
            flash("Choose a CSV file to begin.", "error")
            return redirect(url_for("upload_page"))
        safe_name = secure_filename(file.filename)
        if not safe_name or Path(safe_name).suffix.lower() != ALLOWED_EXTENSION:
            flash("Only .csv files are supported.", "error")
            return redirect(url_for("upload_page"))
        try:
            raw = file.stream.read(MAX_FILE_BYTES + 1)
            if not raw:
                raise ValueError("The uploaded file is empty.")
            if len(raw) > MAX_FILE_BYTES:
                raise ValueError("That file exceeds the 16 MB upload limit.")
            header = next(csv.reader(StringIO(raw.decode("utf-8-sig"), newline=""), strict=True), [])
            if not header:
                raise ValueError("The CSV is missing its header row.")
            if len(header) != len(set(header)):
                raise ValueError("Column names must be unique.")
            if any(not name.strip() for name in header):
                raise ValueError("Every column must have a non-empty name.")
            frame = pd.read_csv(
                BytesIO(raw),
                encoding="utf-8-sig",
                nrows=MAX_ROWS + 1,
                on_bad_lines="error",
                low_memory=False,
            )
            if frame.empty:
                raise ValueError("The CSV has headers but no data rows.")
            if len(frame) > MAX_ROWS:
                raise ValueError("This dataset exceeds the 100,000 row limit.")
            if frame.shape[1] > MAX_COLUMNS:
                raise ValueError("This dataset exceeds the 100 column limit.")
            if frame.shape[0] * frame.shape[1] > MAX_CELLS:
                raise ValueError("This dataset exceeds the 1,000,000 cell analysis limit.")
            if any(len(str(column).encode("utf-8")) > 256 for column in frame.columns):
                raise ValueError("A column name exceeds the 256 byte limit.")
            if frame.columns.empty or any(not str(column).strip() for column in frame.columns):
                raise ValueError("Every column must have a non-empty name.")
            for column in frame.columns:
                if frame[column].dtype == object and frame[column].map(
                    lambda value: len(str(value).encode("utf-8")) > MAX_FIELD_BYTES if pd.notna(value) else False
                ).any():
                    raise ValueError("A cell exceeds the 1 MB safety limit.")
            result = analyze_dataframe(frame)
        except (UnicodeDecodeError, csv.Error, pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as error:
            flash(f"Could not analyze this CSV: {error}", "error")
            return redirect(url_for("upload_page"))
        scan_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        store_scan(
            app.config["DATABASE"],
            scan_id,
            safe_name,
            created_at,
            json.dumps(result, allow_nan=False, ensure_ascii=False),
        )
        return redirect(url_for("scan_detail", scan_id=scan_id))

    @app.route("/scans/<scan_id>")
    def scan_detail(scan_id):
        scan = get_scan(app.config["DATABASE"], scan_id)
        if scan is None:
            abort(404)
        result = json.loads(scan["result_json"])
        return render_template("analysis.html", page="analysis", scan=scan, result=result)

    @app.route("/history")
    def history():
        return render_template("history.html", page="history", scans=recent_scans(app.config["DATABASE"], 100))

    @app.route("/patterns")
    def patterns():
        return latest_feature_page(app, "patterns")

    @app.route("/anomalies")
    def anomalies():
        return latest_feature_page(app, "anomalies")

    @app.route("/reports")
    def reports():
        return render_template("reports.html", page="reports", scans=recent_scans(app.config["DATABASE"], 100))

    @app.post("/scans/<scan_id>/delete")
    def delete_scan(scan_id):
        with connect(app.config["DATABASE"]) as db:
            db.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
        flash("Scan deleted.", "success")
        return redirect(url_for("history"))

    @app.route("/scans/<scan_id>/report.pdf")
    def download_report(scan_id):
        scan = get_scan(app.config["DATABASE"], scan_id)
        if scan is None:
            abort(404)
        pdf = create_pdf_report(scan, json.loads(scan["result_json"]))
        return send_file(
            pdf,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"patterniq-report-{scan_id[:8]}.pdf",
        )

    @app.route("/about")
    def about():
        return render_template("about.html", page="about")

    return app


def latest_feature_page(app, feature):
    with connect(app.config["DATABASE"]) as db:
        row = db.execute("SELECT * FROM scans ORDER BY created_at DESC LIMIT 1").fetchone()
    scan = dict(row) if row else None
    result = json.loads(scan["result_json"]) if scan else None
    return render_template("feature.html", page=feature, feature=feature, scan=scan, result=result)


@contextmanager
def connect(database):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database(database):
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    with connect(database) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                created_at TEXT NOT NULL,
                result_json TEXT NOT NULL
            )"""
        )


def store_scan(database, scan_id, filename, created_at, result_json):
    with connect(database) as db:
        db.execute(
            "INSERT INTO scans (id, filename, created_at, result_json) VALUES (?, ?, ?, ?)",
            (scan_id, filename, created_at, result_json),
        )


def get_scan(database, scan_id):
    if not re.fullmatch(r"[a-f0-9]{32}", scan_id):
        return None
    with connect(database) as db:
        return db.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()


def recent_scans(database, limit):
    with connect(database) as db:
        rows = db.execute(
            "SELECT id, filename, created_at, result_json FROM scans ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    items = []
    for row in rows:
        result = json.loads(row["result_json"])
        items.append(
            {
                "id": row["id"],
                "filename": row["filename"],
                "created_at": row["created_at"],
                "rows": result["overview"]["rows"],
                "columns": result["overview"]["columns"],
                "groups": result["clusters"]["count"] if result["clusters"]["available"] else None,
                "anomalies": result["anomalies"]["count"] if result["anomalies"]["available"] else None,
            }
        )
    return items


def count_scans(database):
    with connect(database) as db:
        return db.execute("SELECT COUNT(*) FROM scans").fetchone()[0]


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
