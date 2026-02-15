from bitnet_tools.viz_recommender import recommend_chart_types


def test_recommend_trend_question_consistency():
    q = '월별 매출 추이를 보여줘'
    first = recommend_chart_types(q)
    second = recommend_chart_types(q)
    assert first == second
    assert first['intent'] == 'trend'
    assert 'line' in first['recommended_chart_types']


def test_recommend_relationship_question_consistency():
    q = '광고비와 매출의 상관 관계를 알고 싶어'
    result = recommend_chart_types(q)
    assert result['intent'] == 'relationship'
    assert result['recommended_chart_types'][:2] == ['scatter', 'histogram']


def test_recommend_quality_question_consistency():
    q = '결측치와 이상치가 있는지 확인해줘'
    result = recommend_chart_types(q)
    assert result['intent'] == 'quality'
    assert result['recommended_chart_types'] == ['missing', 'boxplot']


def test_recommend_default_for_unknown_question():
    result = recommend_chart_types('데이터를 한번 살펴봐')
    assert result['intent'] == 'overview'
    assert result['recommended_chart_types'] == ['histogram', 'bar', 'scatter']
