from bitnet_tools.multi_csv import analyze_multiple_csv


def test_reason_candidates_score_sort_and_reason_text(tmp_path):
    p = tmp_path / 'reason_case.csv'
    p.write_text(
        '\n'.join(
            [
                'dt,cat,amount,desc',
                '2024-01-01,A,100,10kg',
                '2024-01-02,A,110,12kg',
                '2024-01-03,A,120,1lb',
                '2024-01-04,A,,3kg',
                '2024-01-05,B,105,2lb',
                '2024-01-06,A,,5kg',
                '2024-01-07,A,1000,2lb',
                '2024-01-08,A,1200,6kg',
                '2024-01-09,A,1300,7kg',
                '2024-01-10,A,1400,8kg',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    result = analyze_multiple_csv([p], '이상치 이유를 보여줘')
    reasons = result['reason_candidates']

    assert 1 <= len(reasons) <= 3
    assert reasons == sorted(reasons, key=lambda x: x['score'], reverse=True)

    for reason in reasons:
        assert reason['score'] > 0
        assert reason['rule']
        assert reason['reason']

    reason_text = ' '.join(r['reason'] for r in reasons)
    assert any(token in reason_text for token in ['결측', '편중', '단위', '급변'])
