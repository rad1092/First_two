from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VizRecommendation:
    intent: str
    chart_types: list[str]
    reason: str


_INTENT_RULES: list[tuple[tuple[str, ...], VizRecommendation]] = [
    (
        ("추이", "트렌드", "변화", "시계열", "trend", "over time"),
        VizRecommendation(
            intent="trend",
            chart_types=["line", "scatter"],
            reason="시간/순서 기반 변화 파악에는 선형 추세와 분포 확인이 유리합니다.",
        ),
    ),
    (
        ("비교", "랭킹", "상위", "하위", "compare", "ranking"),
        VizRecommendation(
            intent="comparison",
            chart_types=["bar", "boxplot"],
            reason="그룹 간 크기 비교에는 막대, 분산 비교에는 박스플롯이 적합합니다.",
        ),
    ),
    (
        ("관계", "상관", "영향", "relationship", "correlation"),
        VizRecommendation(
            intent="relationship",
            chart_types=["scatter", "histogram"],
            reason="변수 간 관계는 산점도로, 단일 변수 분포는 히스토그램으로 확인합니다.",
        ),
    ),
    (
        ("비율", "구성", "점유", "composition", "ratio"),
        VizRecommendation(
            intent="composition",
            chart_types=["bar"],
            reason="구성 비교는 범주형 막대 차트로 읽기 쉽고 왜곡이 적습니다.",
        ),
    ),
    (
        ("결측", "누락", "품질", "이상치", "missing", "quality", "outlier"),
        VizRecommendation(
            intent="quality",
            chart_types=["missing", "boxplot"],
            reason="데이터 품질 확인에는 결측 막대와 이상치 확인용 박스플롯이 효과적입니다.",
        ),
    ),
]

_DEFAULT = VizRecommendation(
    intent="overview",
    chart_types=["histogram", "bar", "scatter"],
    reason="일반 탐색 질문으로 판단되어 분포/범주/관계를 함께 확인하는 구성을 추천합니다.",
)


def recommend_chart_types(question: str) -> dict[str, object]:
    text = (question or "").strip().lower()
    if not text:
        rec = _DEFAULT
    else:
        rec = next((rule for keywords, rule in _INTENT_RULES if any(k in text for k in keywords)), _DEFAULT)

    return {
        "intent": rec.intent,
        "recommended_chart_types": rec.chart_types,
        "reason": rec.reason,
    }
