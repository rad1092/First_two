from __future__ import annotations

import json
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .analysis import build_analysis_payload
from .doctor import collect_environment


def run_ollama(model: str, prompt: str) -> str:
    proc = subprocess.run(
        ["ollama", "run", model, prompt],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ollama run failed")
    return proc.stdout.strip()


class DesktopApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("BitNet CSV Analyzer (Windows)")
        self.root.geometry("1100x760")

        self.csv_path: Path | None = None
        self.latest_prompt = ""

        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)

        header = ttk.Label(
            frame,
            text="BitNet CSV Analyzer - 터미널 없이 바로 실행",
            font=("Segoe UI", 14, "bold"),
        )
        header.pack(anchor="w")

        sub = ttk.Label(
            frame,
            text="CSV 선택 → 분석 → BitNet 실행 순서로 사용하세요.",
        )
        sub.pack(anchor="w", pady=(0, 10))

        top_row = ttk.Frame(frame)
        top_row.pack(fill="x", pady=(0, 8))
        ttk.Button(top_row, text="CSV 파일 열기", command=self._open_csv).pack(side="left")

        self.csv_label = ttk.Label(top_row, text="선택된 파일 없음")
        self.csv_label.pack(side="left", padx=12)

        question_row = ttk.LabelFrame(frame, text="질문")
        question_row.pack(fill="x", pady=(0, 8))

        chip_row = ttk.Frame(question_row)
        chip_row.pack(anchor="w", padx=8, pady=6)
        presets = [
            "핵심 인사이트 3개와 근거를 알려줘",
            "이상치 의심 포인트와 추가 확인 항목을 알려줘",
            "실행 가능한 다음 액션 5개를 우선순위로 제안해줘",
        ]
        for txt in presets:
            ttk.Button(chip_row, text=txt.split()[0], command=lambda t=txt: self._set_question(t)).pack(
                side="left", padx=(0, 6)
            )

        self.question = tk.Text(question_row, height=3, wrap="word")
        self.question.pack(fill="x", padx=8, pady=(0, 8))
        self.question.insert("1.0", presets[0])

        model_row = ttk.Frame(frame)
        model_row.pack(fill="x", pady=(0, 8))

        ttk.Label(model_row, text="BitNet 모델 태그").pack(side="left")
        self.model = ttk.Entry(model_row)
        self.model.insert(0, "bitnet:latest")
        self.model.pack(side="left", fill="x", expand=True, padx=8)

        ttk.Button(model_row, text="환경진단", command=self._doctor_async).pack(side="left", padx=(8, 4))
        ttk.Button(model_row, text="1) 분석", command=self._analyze_async).pack(side="left", padx=(0, 4))
        ttk.Button(model_row, text="2) BitNet 실행", command=self._run_model_async).pack(side="left")

        self.status = ttk.Label(frame, text="대기 중")
        self.status.pack(anchor="w", pady=(0, 8))

        output = ttk.Panedwindow(frame, orient="vertical")
        output.pack(fill="both", expand=True)

        self.summary = self._make_text_panel(output, "데이터 요약")
        self.prompt = self._make_text_panel(output, "생성 프롬프트")
        self.answer = self._make_text_panel(output, "BitNet 응답")

    def _make_text_panel(self, parent: ttk.Panedwindow, title: str) -> tk.Text:
        panel = ttk.LabelFrame(parent, text=title)
        text = tk.Text(panel, wrap="word", height=10)
        scrollbar = ttk.Scrollbar(panel, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        parent.add(panel, weight=1)
        return text

    def _on_ui(self, func, *args) -> None:
        self.root.after(0, lambda: func(*args))

    def _set_question(self, text: str) -> None:
        self.question.delete("1.0", "end")
        self.question.insert("1.0", text)

    def _open_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="CSV 파일 선택",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        self.csv_path = Path(path)
        self.csv_label.configure(text=str(self.csv_path))

    def _get_question(self) -> str:
        question = self.question.get("1.0", "end").strip()
        return question or "이 데이터의 핵심 인사이트를 알려줘"

    def _analyze_async(self) -> None:
        threading.Thread(target=self._analyze, daemon=True).start()

    def _analyze(self) -> None:
        self._on_ui(self._set_status, "분석 중...")
        try:
            question = self._get_question()
            if self.csv_path:
                payload = build_analysis_payload(self.csv_path, question)
            else:
                self._on_ui(
                    messagebox.showinfo,
                    "파일 미선택",
                    "CSV를 선택하지 않아 본문 텍스트 입력을 안내합니다. 텍스트 박스에 CSV를 붙여넣으세요.",
                )
                return

            self.latest_prompt = payload["prompt"]
            self._on_ui(self._set_text, self.summary, json.dumps(payload["summary"], ensure_ascii=False, indent=2))
            self._on_ui(self._set_text, self.prompt, self.latest_prompt)
            self._on_ui(self._set_text, self.answer, "")
            self._on_ui(self._set_status, "분석 완료")
        except Exception as exc:
            self._on_ui(self._set_status, f"오류: {exc}")


    def _doctor_async(self) -> None:
        threading.Thread(target=self._doctor, daemon=True).start()

    def _doctor(self) -> None:
        self._on_ui(self._set_status, "환경 진단 중...")
        report = collect_environment(model=self.model.get().strip() or None)
        self._on_ui(self._set_text, self.answer, json.dumps(report, ensure_ascii=False, indent=2))
        if report.get("ollama_installed") and report.get("ollama_running"):
            self._on_ui(self._set_status, "환경 진단 완료 (정상)")
        else:
            self._on_ui(self._set_status, "환경 진단 완료 (확인 필요)")

    def _run_model_async(self) -> None:
        threading.Thread(target=self._run_model, daemon=True).start()

    def _run_model(self) -> None:
        if not self.latest_prompt:
            self._on_ui(self._set_text, self.answer, "먼저 분석을 실행해 프롬프트를 생성하세요.")
            return

        model = self.model.get().strip()
        if not model:
            self._on_ui(self._set_text, self.answer, "모델 태그를 입력하세요. 예: bitnet:latest")
            return

        self._on_ui(self._set_status, "BitNet 실행 중...")
        try:
            result = run_ollama(model, self.latest_prompt)
            self._on_ui(self._set_text, self.answer, result)
            self._on_ui(self._set_status, "BitNet 실행 완료")
        except Exception as exc:
            self._on_ui(self._set_text, self.answer, f"오류: {exc}")
            self._on_ui(self._set_status, "BitNet 실행 실패")

    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    def _set_status(self, value: str) -> None:
        self.status.configure(text=value)


def launch_desktop() -> None:
    root = tk.Tk()
    DesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    launch_desktop()
