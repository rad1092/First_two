from bitnet_tools.schema_semantics import (
    load_schema_semantics,
    match_alias_to_column,
    normalize_question_entities,
)


def test_schema_semantics_success_mapping():
    concepts = load_schema_semantics()
    match = match_alias_to_column('시군구', ['sigungu_col', 'service_type_col'], concepts)

    assert match.status == 'success'
    assert match.matched_column == 'sigungu_col'


def test_schema_semantics_failed_mapping():
    concepts = load_schema_semantics()
    match = match_alias_to_column('없는용어', ['sigungu_col', 'service_type_col'], concepts)

    assert match.status == 'failed'
    assert match.matched_column is None


def test_schema_semantics_ambiguous_mapping():
    concepts = load_schema_semantics()
    match = match_alias_to_column('세차유형', ['service_type_col', 'service_type'], concepts)

    assert match.status == 'ambiguous'
    assert sorted(match.candidates or []) == ['service_type', 'service_type_col']


def test_normalize_question_entities_replaces_with_column_name():
    concepts = load_schema_semantics()
    result = normalize_question_entities('시군구 별 세차유형 비율을 보여줘', ['sigungu_col', 'service_type_col'], concepts)

    assert result['normalized_question'] == 'sigungu_col 별 service_type_col 비율을 보여줘'
    assert len(result['mappings']) == 2
