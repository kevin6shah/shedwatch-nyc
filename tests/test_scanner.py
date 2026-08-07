from app.scanner import distance_m, normalize_name


def test_camera_filename_normalization():
    assert normalize_name("2 Ave @ E 14 St") == normalize_name("2_Ave_@_E_14_St.jpg".removesuffix(".jpg"))
    assert normalize_name("8 Ave @ 14 St") == normalize_name("8_Ave_@_14_St")


def test_known_eighth_avenue_camera_is_inside_union_square_radius():
    distance = distance_m(40.734717, -73.990696, 40.7397525513578, -74.0025212013102)
    assert distance < 1609


def test_far_camera_is_outside_radius():
    distance = distance_m(40.734717, -73.990696, 40.785302, -73.969353)
    assert distance > 1609
