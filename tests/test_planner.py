from bitnet_tools.planner import AnalysisPlan, build_plan, execute_plan, parse_question_to_intent


def _schema():
    return {
        "columns": ["region", "sales", "period"],
        "dtypes": {"region": "string", "sales": "float", "period": "string"},
        "region_values": ["서울", "부산"],
    }


def test_parse_question_to_intent_extracts_controls():
    intent = parse_question_to_intent("서울 지역 top 3, sample 2, sales 임계값 100 전/후 비교", _schema())

    assert intent.top_n == 3
    assert intent.sample_n == 2
    assert intent.threshold == 100
    assert intent.threshold_column == "sales"
    assert intent.region == "서울"
    assert intent.compare_periods is True
    assert intent.intent_schema == {
        "topN": 3,
        "sampleN": 2,
        "threshold": {"value": 100, "column": "sales"},
        "filter": {"region": "서울", "region_column": "region"},
        "compare": True,
        "include_code": False,
    }


def test_parse_question_to_intent_extracts_include_code_flag():
    intent = parse_question_to_intent("서울 매출 top 5 코드 포함", _schema())

    assert intent.intent_schema["include_code"] is True


def test_build_plan_routes_template_queries_first():
    intent = parse_question_to_intent("상위 5 샘플 2", _schema())
    plan = build_plan(intent, _schema())

    assert [n["op"] for n in plan.nodes] == ["filter", "groupby", "agg", "rank", "sample", "export"]
    assert any(node["op"] == "rank" and node["enabled"] for node in plan.nodes)
    assert plan.intent.routing_source == "template:top_only"


def test_build_plan_routes_only_unmatched_queries_to_fallback():
    intent = parse_question_to_intent("기본 분석만 해줘", _schema())
    plan = build_plan(intent, _schema())

    assert plan.intent.routing_source == "fallback"
    assert any("fallback" in warning for warning in plan.warnings)


def test_execute_plan_fallback_on_invalid_node():
    plan = AnalysisPlan(
        intent=parse_question_to_intent("기본", _schema()),
        nodes=[{"op": "unknown", "enabled": True}],
    )
    data = [{"region": "서울", "sales": "120", "period": "after"}]

    result = execute_plan(plan, data)

    assert result["meta"]["fallback"] is True
    assert "unsupported op" in result["meta"]["error"]


def test_user_examples_are_kept_as_regression_cases():
    cases = [
        (
            "서울 지역 top 3, sample 2, sales 임계값 100 전/후 비교",
            {
                "top_n": 3,
                "sample_n": 2,
                "threshold": 100,
                "region": "서울",
                "compare_periods": True,
            },
        ),
        (
            "상위 5 샘플 2",
            {
                "top_n": 5,
                "sample_n": 2,
                "threshold": None,
                "region": None,
                "compare_periods": False,
            },
        ),
        (
            "기본 분석만 해줘",
            {
                "top_n": None,
                "sample_n": None,
                "threshold": None,
                "region": None,
                "compare_periods": False,
            },
        ),
    ]

    for question, expected in cases:
        intent = parse_question_to_intent(question, _schema())

        assert intent.top_n == expected["top_n"]
        assert intent.sample_n == expected["sample_n"]
        assert intent.threshold == expected["threshold"]
        assert intent.region == expected["region"]
        assert intent.compare_periods == expected["compare_periods"]
