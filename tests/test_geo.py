from bitnet_tools.geo import (
    DISTANCE_THRESHOLD_EXCEEDED,
    MISSING_OR_NON_NUMERIC,
    OUT_OF_RANGE,
    flag_geo_suspects,
    haversine_km,
    validate_lat_lon,
)


def test_validate_lat_lon_range_checks():
    assert validate_lat_lon(37.5, 127.0) is True
    assert validate_lat_lon(-90, -180) is True
    assert validate_lat_lon(90, 180) is True
    assert validate_lat_lon(91, 127) is False
    assert validate_lat_lon(37, -181) is False


def test_haversine_km_returns_expected_scale():
    d = haversine_km(37.5665, 126.9780, 35.1796, 129.0756)
    assert 320 <= d <= 340


def test_flag_geo_suspects_distinguishes_missing_range_and_distance():
    rows = [
        {'id': '1', 'lat': '37.5665', 'lon': '126.9780'},
        {'id': '2', 'lat': '35.1796', 'lon': '129.0756'},
        {'id': '3', 'lat': '91', 'lon': '127'},
        {'id': '4', 'lat': '', 'lon': '127.1'},
    ]

    result = flag_geo_suspects(rows, lat_col='lat', lon_col='lon', threshold_km=25)

    assert result[0]['is_suspect'] is False
    assert result[0]['suspect_reason'] == ''
    assert result[0]['distance_km'] is None

    assert result[1]['is_suspect'] is True
    assert result[1]['suspect_reason'] == DISTANCE_THRESHOLD_EXCEEDED
    assert result[1]['distance_km'] is not None
    assert result[1]['distance_km'] >= 25

    assert result[2]['is_suspect'] is True
    assert result[2]['suspect_reason'] == OUT_OF_RANGE
    assert result[2]['distance_km'] is None

    assert result[3]['is_suspect'] is True
    assert result[3]['suspect_reason'] == MISSING_OR_NON_NUMERIC
    assert result[3]['distance_km'] is None


def test_flag_geo_suspects_threshold_boundary_is_inclusive():
    rows = [
        {'lat': 0.0, 'lon': 0.0},
        {'lat': 0.0, 'lon': 1.0},
    ]
    # 대략 111km
    result = flag_geo_suspects(rows, lat_col='lat', lon_col='lon', threshold_km=111)
    assert result[1]['is_suspect'] is True
    assert result[1]['suspect_reason'] == DISTANCE_THRESHOLD_EXCEEDED
