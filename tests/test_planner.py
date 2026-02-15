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


def test_build_plan_contains_execution_graph_nodes():
    intent = parse_question_to_intent("상위 5 샘플 2", _schema())
    plan = build_plan(intent, _schema())

    assert [n["op"] for n in plan.nodes] == ["filter", "groupby", "agg", "rank", "sample", "export"]
    assert any(node["op"] == "rank" and node["enabled"] for node in plan.nodes)


def test_execute_plan_fallback_on_invalid_node():
    plan = AnalysisPlan(
        intent=parse_question_to_intent("기본", _schema()),
        nodes=[{"op": "unknown", "enabled": True}],
    )
    data = [{"region": "서울", "sales": "120", "period": "after"}]

    result = execute_plan(plan, data)

    assert result["meta"]["fallback"] is True
    assert "unsupported op" in result["meta"]["error"]
