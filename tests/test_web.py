import time
from pathlib import Path

import bitnet_tools.web as web


def test_submit_and_get_chart_job_done(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "CHART_JOB_DIR", tmp_path / "jobs")

    def fake_create_multi_charts(csv_paths, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        outputs = {}
        for p in csv_paths:
            chart = out_dir / f"{Path(p).stem}.png"
            chart.write_text("ok", encoding="utf-8")
            outputs[str(p)] = [str(chart)]
        return outputs

    monkeypatch.setattr(web, "create_multi_charts", fake_create_multi_charts)

    job_id = web.submit_chart_job([{"name": "a.csv", "csv_text": "x\n1\n"}])
    result = web.get_chart_job(job_id)
    for _ in range(20):
        if result["status"] != "running":
            break
        time.sleep(0.01)
        result = web.get_chart_job(job_id)

    assert result["status"] == "done"
    assert result["chart_count"] == 1
    assert result["output_dir"].endswith("_charts")


def test_get_chart_job_not_found():
    result = web.get_chart_job("missing")
    assert result["status"] == "not_found"
