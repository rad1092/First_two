from __future__ import annotations

import csv
import random
from collections import Counter
from pathlib import Path
from typing import Any


SUPPORTED_CHART_TYPES = {"histogram", "boxplot", "missing", "bar", "scatter", "line"}


SAMPLE_CAP = 20000
TOP_K = 10


def _safe_stem(path: Path) -> str:
    return path.stem.replace(" ", "_")


def _ensure_matplotlib():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except Exception as exc:
        raise RuntimeError("matplotlib is required for chart generation") from exc


def _reservoir_float(values: list[float], value: float, seen: int, cap: int) -> None:
    if cap <= 0:
        return
    if len(values) < cap:
        values.append(value)
        return
    idx = random.randint(0, seen - 1)
    if idx < cap:
        values[idx] = value


def _reservoir_pair(xs: list[float], ys: list[float], x: float, y: float, seen: int, cap: int) -> None:
    if cap <= 0:
        return
    if len(xs) < cap:
        xs.append(x)
        ys.append(y)
        return
    idx = random.randint(0, seen - 1)
    if idx < cap:
        xs[idx] = x
        ys[idx] = y


def _collect_profiles(csv_path: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return [], {}
        columns = [str(c) for c in reader.fieldnames]

        profiles: dict[str, dict[str, Any]] = {
            c: {
                "seen": 0,
                "numeric_seen": 0,
                "is_numeric": True,
                "missing": 0,
                "values": [],
                "counter": Counter(),
            }
            for c in columns
        }

        for row in reader:
            for c in columns:
                raw = (row.get(c) or "").strip()
                if not raw:
                    profiles[c]["missing"] += 1
                    continue
                profiles[c]["seen"] += 1

                if profiles[c]["is_numeric"]:
                    try:
                        num = float(raw)
                        profiles[c]["numeric_seen"] += 1
                        _reservoir_float(
                            profiles[c]["values"], num, profiles[c]["numeric_seen"], SAMPLE_CAP
                        )
                    except ValueError:
                        profiles[c]["is_numeric"] = False
                        profiles[c]["values"] = []

                profiles[c]["counter"][raw] += 1

    for c in columns:
        if profiles[c]["numeric_seen"] == 0:
            profiles[c]["is_numeric"] = False

    return columns, profiles


def create_file_charts(
    csv_path: Path,
    out_dir: Path,
    max_numeric: int = 3,
    max_categorical: int = 2,
    selected_chart_types: list[str] | None = None,
) -> list[str]:
    plt = _ensure_matplotlib()

    out_dir.mkdir(parents=True, exist_ok=True)
    columns, profiles = _collect_profiles(csv_path)
    if not columns:
        return []

    numeric_cols = [c for c in columns if profiles[c]["is_numeric"]][:max_numeric]
    categorical_cols = [c for c in columns if not profiles[c]["is_numeric"]][:max_categorical]

    artifacts: list[str] = []
    stem = _safe_stem(csv_path)
    selected = {c.strip().lower() for c in (selected_chart_types or []) if c}
    if not selected:
        selected = set(SUPPORTED_CHART_TYPES)

    for col in numeric_cols:
        values: list[float] = profiles[col]["values"]
        missing = profiles[col]["missing"]
        if not values:
            continue

        if "histogram" in selected:
            fig = plt.figure(figsize=(7, 4))
            plt.hist(values, bins=20)
            plt.title(f"{stem} - {col} histogram(sample)")
            plt.xlabel(col)
            plt.ylabel("count")
            plt.tight_layout()
            out = out_dir / f"{stem}_{col}_hist.png"
            fig.savefig(out)
            plt.close(fig)
            artifacts.append(str(out))

        if "boxplot" in selected:
            fig = plt.figure(figsize=(5, 4))
            plt.boxplot(values, vert=True)
            plt.title(f"{stem} - {col} boxplot(sample)")
            plt.ylabel(col)
            plt.tight_layout()
            out = out_dir / f"{stem}_{col}_box.png"
            fig.savefig(out)
            plt.close(fig)
            artifacts.append(str(out))

        total = profiles[col]["seen"] + missing
        if total > 0 and "missing" in selected:
            fig = plt.figure(figsize=(5, 3))
            plt.bar(["non_missing", "missing"], [profiles[col]["seen"], missing])
            plt.title(f"{stem} - {col} missing overview")
            plt.tight_layout()
            out = out_dir / f"{stem}_{col}_missing.png"
            fig.savefig(out)
            plt.close(fig)
            artifacts.append(str(out))

    for col in categorical_cols:
        items = profiles[col]["counter"].most_common(TOP_K)
        if not items:
            continue

        labels = [x[0] for x in items]
        counts = [x[1] for x in items]
        if "bar" in selected:
            fig = plt.figure(figsize=(8, 4))
            plt.bar(range(len(labels)), counts)
            plt.xticks(range(len(labels)), labels, rotation=30, ha="right")
            plt.title(f"{stem} - {col} top values")
            plt.tight_layout()
            out = out_dir / f"{stem}_{col}_top.png"
            fig.savefig(out)
            plt.close(fig)
            artifacts.append(str(out))

    if len(numeric_cols) >= 2 and ("scatter" in selected or "line" in selected):
        x_col, y_col = numeric_cols[0], numeric_cols[1]
        xs: list[float] = []
        ys: list[float] = []
        seen = 0
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is not None:
                for row in reader:
                    x_raw = (row.get(x_col) or "").strip()
                    y_raw = (row.get(y_col) or "").strip()
                    if not x_raw or not y_raw:
                        continue
                    try:
                        x, y = float(x_raw), float(y_raw)
                    except ValueError:
                        continue
                    seen += 1
                    _reservoir_pair(xs, ys, x, y, seen, SAMPLE_CAP)

        if xs and ys and "scatter" in selected:
            fig = plt.figure(figsize=(6, 5))
            plt.scatter(xs, ys, alpha=0.6, s=12)
            plt.title(f"{stem} - {x_col} vs {y_col} scatter(sample)")
            plt.xlabel(x_col)
            plt.ylabel(y_col)
            plt.tight_layout()
            out = out_dir / f"{stem}_{x_col}_{y_col}_scatter.png"
            fig.savefig(out)
            plt.close(fig)
            artifacts.append(str(out))

        if xs and ys and "line" in selected:
            pairs = sorted(zip(xs, ys), key=lambda pair: pair[0])
            fig = plt.figure(figsize=(6, 4))
            plt.plot([p[0] for p in pairs], [p[1] for p in pairs], linewidth=1.3)
            plt.title(f"{stem} - {x_col} vs {y_col} line(sample)")
            plt.xlabel(x_col)
            plt.ylabel(y_col)
            plt.tight_layout()
            out = out_dir / f"{stem}_{x_col}_{y_col}_line.png"
            fig.savefig(out)
            plt.close(fig)
            artifacts.append(str(out))

    return artifacts


def create_multi_charts(
    csv_paths: list[Path],
    out_dir: Path,
    selected_chart_types: list[str] | None = None,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for p in csv_paths:
        results[str(p)] = create_file_charts(p, out_dir, selected_chart_types=selected_chart_types)
    return results
