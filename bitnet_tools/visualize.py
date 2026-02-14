from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def _is_numeric_column(rows: list[dict[str, str]], col: str) -> bool:
    seen = 0
    for row in rows:
        raw = (row.get(col) or "").strip()
        if not raw:
            continue
        seen += 1
        try:
            float(raw)
        except ValueError:
            return False
    return seen > 0


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


def create_file_charts(
    csv_path: Path,
    out_dir: Path,
    max_numeric: int = 3,
    max_categorical: int = 2,
) -> list[str]:
    plt = _ensure_matplotlib()

    out_dir.mkdir(parents=True, exist_ok=True)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []
        columns = [str(c) for c in reader.fieldnames]
        rows = list(reader)

    numeric_cols = [c for c in columns if _is_numeric_column(rows, c)][:max_numeric]
    categorical_cols = [c for c in columns if c not in numeric_cols][:max_categorical]

    artifacts: list[str] = []
    stem = _safe_stem(csv_path)

    # template 1: numeric histogram + boxplot
    for col in numeric_cols:
        values = []
        missing = 0
        for row in rows:
            raw = (row.get(col) or "").strip()
            if raw:
                values.append(float(raw))
            else:
                missing += 1
        if not values:
            continue

        fig = plt.figure(figsize=(7, 4))
        plt.hist(values, bins=20)
        plt.title(f"{stem} - {col} histogram")
        plt.xlabel(col)
        plt.ylabel("count")
        plt.tight_layout()
        out = out_dir / f"{stem}_{col}_hist.png"
        fig.savefig(out)
        plt.close(fig)
        artifacts.append(str(out))

        fig = plt.figure(figsize=(5, 4))
        plt.boxplot(values, vert=True)
        plt.title(f"{stem} - {col} boxplot")
        plt.ylabel(col)
        plt.tight_layout()
        out = out_dir / f"{stem}_{col}_box.png"
        fig.savefig(out)
        plt.close(fig)
        artifacts.append(str(out))

        # template 2: numeric missing ratio mini chart
        total = len(values) + missing
        if total > 0:
            fig = plt.figure(figsize=(5, 3))
            plt.bar(["non_missing", "missing"], [len(values), missing])
            plt.title(f"{stem} - {col} missing overview")
            plt.tight_layout()
            out = out_dir / f"{stem}_{col}_missing.png"
            fig.savefig(out)
            plt.close(fig)
            artifacts.append(str(out))

    # template 3: categorical top-value bar
    for col in categorical_cols:
        counter: dict[str, int] = {}
        for row in rows:
            raw = (row.get(col) or "").strip()
            if not raw:
                continue
            counter[raw] = counter.get(raw, 0) + 1
        items = sorted(counter.items(), key=lambda x: x[1], reverse=True)[:10]
        if not items:
            continue

        labels = [x[0] for x in items]
        counts = [x[1] for x in items]
        fig = plt.figure(figsize=(8, 4))
        plt.bar(range(len(labels)), counts)
        plt.xticks(range(len(labels)), labels, rotation=30, ha="right")
        plt.title(f"{stem} - {col} top values")
        plt.tight_layout()
        out = out_dir / f"{stem}_{col}_top.png"
        fig.savefig(out)
        plt.close(fig)
        artifacts.append(str(out))

    # template 4: scatter for first 2 numeric columns
    if len(numeric_cols) >= 2:
        x_col, y_col = numeric_cols[0], numeric_cols[1]
        xs: list[float] = []
        ys: list[float] = []
        for row in rows:
            x_raw = (row.get(x_col) or "").strip()
            y_raw = (row.get(y_col) or "").strip()
            if not x_raw or not y_raw:
                continue
            xs.append(float(x_raw))
            ys.append(float(y_raw))
        if xs and ys:
            fig = plt.figure(figsize=(6, 5))
            plt.scatter(xs, ys, alpha=0.6, s=12)
            plt.title(f"{stem} - {x_col} vs {y_col}")
            plt.xlabel(x_col)
            plt.ylabel(y_col)
            plt.tight_layout()
            out = out_dir / f"{stem}_{x_col}_{y_col}_scatter.png"
            fig.savefig(out)
            plt.close(fig)
            artifacts.append(str(out))

    return artifacts


def create_multi_charts(
    csv_paths: list[Path],
    out_dir: Path,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for p in csv_paths:
        results[str(p)] = create_file_charts(p, out_dir)
    return results
