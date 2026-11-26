import math
import warnings

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


RANDOM_STATE = 42
MAX_MODEL_ROWS = 3000
MAX_CATEGORY_COUNT = 20


def json_number(value):
    if pd.isna(value) or not np.isfinite(value):
        return None
    return float(value)


def build_features(frame):
    numeric = frame.select_dtypes(include=[np.number]).columns.tolist()
    categorical = [
        column
        for column in frame.columns
        if column not in numeric and frame[column].notna().any()
    ]
    numeric = [column for column in numeric if frame[column].notna().any()]
    if not numeric and not categorical:
        return None, [], [], []

    transformers = []
    if numeric:
        transformers.append(
            ("numeric", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric)
        )
    if categorical:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("encode", OneHotEncoder(handle_unknown="infrequent_if_exist", max_categories=MAX_CATEGORY_COUNT, sparse_output=False)),
                    ]
                ),
                categorical,
            )
        )
    transformer = ColumnTransformer(transformers, remainder="drop", sparse_threshold=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        matrix = transformer.fit_transform(frame)
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.size == 0 or not np.isfinite(matrix).all():
        return None, numeric, categorical, []
    feature_names = []
    if numeric:
        feature_names.extend(numeric)
    if categorical:
        feature_names.extend(transformer.named_transformers_["categorical"].named_steps["encode"].get_feature_names_out(categorical).tolist())
    return matrix, numeric, categorical, feature_names


def analyze_dataframe(frame):
    rows, columns = frame.shape
    missing_by_column = {str(column): int(value) for column, value in frame.isna().sum().items() if value}
    duplicate_rows = int(frame.duplicated().sum())
    numeric_columns = frame.select_dtypes(include=[np.number]).columns.tolist()
    categorical_columns = [column for column in frame.columns if column not in numeric_columns]
    profile = []
    for column in frame.columns:
        series = frame[column]
        item = {
            "name": str(column),
            "type": "numeric" if column in numeric_columns else "categorical",
            "missing": int(series.isna().sum()),
            "unique": int(series.nunique(dropna=True)),
        }
        if column in numeric_columns:
            values = series.describe()
            item["summary"] = {
                key: json_number(values.get(key))
                for key in ("mean", "std", "min", "25%", "50%", "75%", "max")
            }
        else:
            top = series.dropna().astype(str).value_counts().head(5)
            item["top_values"] = [{"value": str(value)[:120], "count": int(count)} for value, count in top.items()]
        profile.append(item)

    correlations = []
    heatmap = []
    if len(numeric_columns) >= 2:
        corr = frame[numeric_columns].corr(min_periods=2).replace([np.inf, -np.inf], np.nan)
        for row_idx, row_name in enumerate(corr.index):
            heatmap.append([json_number(value) for value in corr.iloc[row_idx].tolist()])
            for col_idx in range(row_idx + 1, len(corr.columns)):
                value = corr.iloc[row_idx, col_idx]
                if pd.notna(value) and abs(value) >= 0.7:
                    correlations.append({"first": str(row_name), "second": str(corr.columns[col_idx]), "value": round(float(value), 3)})
        correlations.sort(key=lambda item: abs(item["value"]), reverse=True)

    model_frame = frame.copy()
    sampled = rows > MAX_MODEL_ROWS
    if sampled:
        model_frame = frame.sample(n=MAX_MODEL_ROWS, random_state=RANDOM_STATE).sort_index()
    matrix, model_numeric, model_categorical, feature_names = build_features(model_frame)

    clusters = {"available": False, "reason": "At least two records and one usable feature are required.", "count": 0, "sizes": [], "points": []}
    anomalies = {"available": False, "reason": "At least ten records and one usable feature are required.", "count": 0, "percentage": 0, "points": []}
    pca = {"available": False, "reason": "A usable feature matrix is required.", "points": []}

    if matrix is not None and matrix.shape[1] > 0:
        point_indices = model_frame.index.tolist()
        distinct_profiles = int(np.unique(matrix, axis=0).shape[0])
        if rows >= 2:
            k = min(5, max(2, int(round(math.sqrt(len(matrix) / 2)))), distinct_profiles)
            k = min(k, len(matrix))
            if distinct_profiles >= 2 and k >= 2:
                labels = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit_predict(matrix)
                sizes = np.bincount(labels, minlength=k)
                cluster_centers = []
                for cluster_id in range(k):
                    center = matrix[labels == cluster_id].mean(axis=0)
                    prominent = np.argsort(np.abs(center))[::-1][:3]
                    cluster_centers.append(
                        {
                            "id": int(cluster_id),
                            "size": int(sizes[cluster_id]),
                            "share": round(float(sizes[cluster_id] / len(labels) * 100), 1),
                            "features": [
                                {"name": str(feature_names[index])[:80], "relative_value": round(float(center[index]), 2)}
                                for index in prominent
                                if abs(center[index]) >= 0.35
                            ],
                        }
                    )
                clusters = {
                    "available": True,
                    "count": k,
                    "sizes": cluster_centers,
                    "points": [
                        {"x": int(point_indices[i]), "y": int(labels[i]), "cluster": int(labels[i])}
                        for i in range(len(labels))
                    ],
                    "sampled": sampled,
                }
            elif distinct_profiles < 2:
                clusters["reason"] = "The usable feature values do not vary enough to form distinct groups."
        if rows >= 10:
            if distinct_profiles >= 2:
                model = IsolationForest(n_estimators=100, contamination="auto", random_state=RANDOM_STATE, n_jobs=1)
                labels = model.fit_predict(matrix)
                scores = model.decision_function(matrix)
                outlier_positions = np.flatnonzero(labels == -1)
                anomalies = {
                    "available": True,
                    "count": int(len(outlier_positions)),
                    "percentage": round(float(len(outlier_positions) / len(labels) * 100), 1),
                    "points": [
                        {"row": int(point_indices[i]) + 1, "score": round(float(scores[i]), 4)}
                        for i in outlier_positions[:100]
                    ],
                    "sampled": sampled,
                }
            else:
                anomalies["reason"] = "The usable feature values do not vary enough to detect unusual records."
        if len(matrix) >= 2:
            if matrix.shape[1] >= 2:
                pca_model = PCA(n_components=2, random_state=RANDOM_STATE)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=RuntimeWarning)
                    coordinates = pca_model.fit_transform(matrix)
                variance = np.nan_to_num(pca_model.explained_variance_ratio_, nan=0.0, posinf=0.0, neginf=0.0)
            else:
                coordinates = np.column_stack((matrix[:, 0], np.zeros(len(matrix))))
                variance = np.array([1.0, 0.0])
            pca = {
                "available": True,
                "variance": [round(float(value), 4) for value in variance],
                "points": [
                    {"x": round(float(coordinates[i, 0]), 4), "y": round(float(coordinates[i, 1]), 4)}
                    for i in range(len(coordinates))
                ],
                "sampled": sampled,
            }

    insights = []
    if missing_by_column:
        most_missing = max(missing_by_column, key=missing_by_column.get)
        insights.append(f"{sum(missing_by_column.values()):,} cells are missing; {most_missing} has the most ({missing_by_column[most_missing]:,}).")
    else:
        insights.append("No missing cells were found in this dataset.")
    if clusters["available"]:
        largest = max(clusters["sizes"], key=lambda item: item["size"])
        insights.append(f"K-Means found {clusters['count']} groups; the largest contains {largest['size']:,} records ({largest['share']}%).")
    else:
        insights.append(clusters["reason"])
    if anomalies["available"]:
        insights.append(f"Isolation Forest flagged {anomalies['count']:,} unusual records ({anomalies['percentage']}% of analyzed records).")
    if correlations:
        strongest = correlations[0]
        direction = "positive" if strongest["value"] > 0 else "negative"
        insights.append(f"Strongest numeric relationship: {strongest['first']} and {strongest['second']} ({direction}, r = {strongest['value']}).")
    elif len(numeric_columns) >= 2:
        insights.append("No numeric feature pair met the strong-correlation threshold (|r| >= 0.70).")
    if sampled:
        insights.append(f"Models and visualizations use a deterministic sample of {MAX_MODEL_ROWS:,} rows; descriptive statistics use the full dataset.")

    recommendations = []
    if missing_by_column:
        most_missing = max(missing_by_column, key=missing_by_column.get)
        recommendations.append(
            f"Review missing values in {most_missing} and choose an imputation or exclusion strategy that fits your workflow."
        )
    if duplicate_rows:
        recommendations.append("Inspect duplicate rows and decide whether they represent repeated events or accidental copies.")
    if clusters["available"]:
        recommendations.append("Compare the discovered group profiles with domain knowledge before using group labels in decisions.")
    if correlations:
        strongest = correlations[0]
        recommendations.append(
            f"Check whether {strongest['first']} and {strongest['second']} measure overlapping information; their observed correlation is {strongest['value']}."
        )
    if anomalies["available"] and anomalies["count"]:
        row_numbers = ", ".join(str(item["row"]) for item in anomalies["points"][:5])
        recommendations.append(
            f"Review flagged CSV row references ({row_numbers}) against the original file and relevant context."
        )
    elif anomalies["available"]:
        recommendations.append("No rows were flagged, but consider domain-specific rules because this model only detects isolation-based patterns.")
    if not numeric_columns:
        recommendations.append("If numeric relationships or PCA would be useful, check whether any numeric values were imported as text.")
    if not recommendations:
        recommendations.append("Review the data preview and column profile, then consider which question you want your next analysis to answer.")

    return {
        "overview": {
            "rows": int(rows),
            "columns": int(columns),
            "numeric_columns": len(numeric_columns),
            "categorical_columns": len(categorical_columns),
            "missing_cells": int(frame.isna().sum().sum()),
            "duplicate_rows": duplicate_rows,
        },
        "missing_by_column": missing_by_column,
        "columns": profile,
        "correlations": correlations[:20],
        "heatmap": {"labels": [str(name) for name in numeric_columns], "values": heatmap},
        "clusters": clusters,
        "anomalies": anomalies,
        "pca": pca,
        "insights": insights,
        "recommendations": recommendations,
        "preview": csv_preview(frame),
    }


def csv_preview(frame):
    return {
        "columns": [str(column) for column in frame.columns],
        "rows": [
            [
                None if pd.isna(value) else str(value)[:160]
                for value in row
            ]
            for row in frame.head(8).itertuples(index=False, name=None)
        ],
    }
