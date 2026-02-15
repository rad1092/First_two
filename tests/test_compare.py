import json
from bitnet_tools import cli
from bitnet_tools.compare import compare_csv_texts
from tests.test_web import _post_json, _run_server


def test_compare_same_data_has_near_zero_drift():
    csv_text = 'city,sales\nseoul,100\nbusan,200\n'
    result = compare_csv_texts(csv_text, csv_text, before_source='before.csv', after_source='after.csv')

    assert result['column_metrics']['city']['psi'] == 0
    assert result['column_metrics']['sales']['js_divergence'] == 0
    assert result['lineage_path'].endswith('.json')


def test_compare_changed_data_has_positive_drift():
    before = 'city,sales\nseoul,100\nbusan,200\n'
    after = 'city,sales\nseoul,100\nseoul,100\n'

    result = compare_csv_texts(before, after, before_source='before.csv', after_source='after.csv')

    assert result['column_metrics']['city']['psi'] > 0
    assert result['column_metrics']['city']['chi_square'] > 0


def test_cli_compare_command(tmp_path):
    before = tmp_path / 'before.csv'
    after = tmp_path / 'after.csv'
    out = tmp_path / 'compare.json'

    before.write_text('city,sales\nseoul,100\nbusan,200\n', encoding='utf-8')
    after.write_text('city,sales\nseoul,100\nseoul,100\n', encoding='utf-8')

    code = cli.main(['compare', '--before', str(before), '--after', str(after), '--out', str(out)])

    assert code == 0
    body = json.loads(out.read_text(encoding='utf-8'))
    assert body['column_metrics']['city']['psi'] > 0


def test_compare_api_returns_result_payload():
    server, thread = _run_server()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        code, body = _post_json(base + '/api/compare', {
            'before': {'name': 'before.csv', 'normalized_csv_text': 'city,sales\nseoul,100\nbusan,200\n'},
            'after': {'name': 'after.csv', 'normalized_csv_text': 'city,sales\nseoul,100\nseoul,100\n'},
        })
        assert code == 200
        assert body['column_metrics']['city']['psi'] > 0
        assert body['before']['source_name'] == 'before.csv'
    finally:
        server.shutdown()
        thread.join(timeout=1)
