# PatternIQ

PatternIQ is a local-first CSV exploration app. It profiles data quality, discovers exploratory groups with K-Means, flags unusual rows with Isolation Forest, maps numeric correlations, projects features with PCA, and creates downloadable PDF summaries.

> **Interpret results carefully.** Clusters are exploratory, anomaly flags are not proof of errors or fraud, correlations are not causation, and no accuracy scores are invented for unlabeled data.

## Features

- **CSV upload and preview:** UTF-8 CSV files up to 16 MB, 100,000 rows, 100 columns, and 1,000,000 cells.
- **Data quality:** row and column counts, duplicate and missing values, inferred numeric/categorical types, column statistics, common categorical values, and an eight-row preview.
- **Pattern discovery:** reproducible K-Means grouping with standardized numeric features and safely one-hot encoded categories.
- **Anomaly detection:** reproducible Isolation Forest, candidate count and rate, decision scores, and CSV row references.
- **Relationships and PCA:** strong numeric correlations (absolute correlation at least 0.70), a correlation heatmap, and a two-dimensional PCA view.
- **Next-step recommendations:** rule-based suggestions tied to detected missing values, duplicates, groups, correlations, and anomaly candidates.
- **Dashboard and scan history:** review saved analysis summaries and delete old scans.
- **PDF reports:** export dataset statistics, key findings, cluster profiles and chart, relationships, and method notes.
- **Responsive interface:** mobile-friendly navigation and data views.

## Technology

- Python 3.10+
- Flask, Pandas, NumPy
- Scikit-learn
- SQLite
- ReportLab
- HTML, CSS, JavaScript, and Chart.js

No paid API, hosted AI service, or external model is used. Chart.js, its matrix plugin, and web fonts are loaded from public CDNs in the browser. The app and data analysis run locally.

## Run in VS Code

1. Open the `PatternIQ` folder in VS Code.
2. Open **Terminal → New Terminal**.
3. Create and activate a virtual environment:

   **Windows PowerShell**

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   **macOS / Linux**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. Install dependencies:

   ```shell
   python -m pip install -r requirements.txt
   ```

5. Start the local server:

   ```shell
   python app.py
   ```

6. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) and upload a CSV.

In VS Code, select the `.venv` interpreter with **Python: Select Interpreter** if prompted. For production use, place the app behind an appropriately configured production WSGI server; the built-in server is for local development.

### Configuration

- `PATTERNIQ_SECRET_KEY`: optional Flask session signing key. If unset, a random process-local key is generated.
- `PATTERNIQ_DATABASE`: optional SQLite file path. Defaults to `instance/patterniq.sqlite3`.
- `PORT`: optional local HTTP port. Defaults to `5000`.

The server binds to `127.0.0.1` by default. Keep it local unless you add authentication and deploy behind a secure production server.

## Usage

1. Choose **Upload dataset** and select or drop a `.csv` file.
2. Review the data preview, column profile, quality indicators, and generated findings.
3. Navigate to **Pattern analysis** or **Anomaly detection** for focused views of the latest scan.
4. Use **Reports** to download PDFs, or **Scan history** to open or delete saved summaries.

Uploaded file bytes are read into memory for analysis and not written to a public/static directory or retained as an uploaded file. Only a compact preview and analysis summary are saved in the local SQLite database. Delete a scan from history to remove its saved summary.

Modeling and visualizations use a deterministic sample of up to 3,000 rows for larger datasets. Descriptive statistics are computed over the full dataset. Model failures and unsupported CSV inputs are reported rather than replaced with fake results.

## Tests

With dependencies installed and the virtual environment active:

```shell
python -m unittest -v
```

## Screenshots

Screenshots can be added here after launching the app, for example:

```text
screenshots/
  dashboard.png
  analysis.png
  upload.png
```

## Project structure

```text
PatternIQ/
├── app.py
├── analysis.py
├── reports.py
├── test_app.py
├── requirements.txt
├── templates/
│   ├── about.html
│   ├── analysis.html
│   ├── base.html
│   ├── dashboard.html
│   ├── feature.html
│   ├── history.html
│   ├── home.html
│   ├── reports.html
│   └── upload.html
└── static/
    ├── css/app.css
    └── js/app.js
```

## Deployment

PatternIQ needs a Python/Flask host; GitHub Pages cannot execute Flask, SQLite, or scikit-learn.
For a free hosted deployment, connect this GitHub repository to a Python-compatible platform such as Render,
set the start command to `gunicorn app:app --bind 0.0.0.0:$PORT`, and set `PYTHON_VERSION` to `3.14` or a
supported Python version. Add persistent storage for `PATTERNIQ_DATABASE` if scan history must survive restarts.

## Future improvements

- Add optional user authentication and per-user workspaces before any network-accessible deployment.
- Allow analysts to export a processed dataset with explicit consent.
- Add configurable sampling and model parameters with a clear audit trail.
- Add richer categorical association measures and time-series-specific analysis.
- Offer accessibility and localization refinements based on user feedback.

## License

Choose and add an open-source license before publishing this project.
