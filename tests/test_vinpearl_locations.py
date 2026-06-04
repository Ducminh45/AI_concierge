from app.core.vinpearl_locations import VINPEARL_LOCATIONS, detect_locations


def test_detects_named_property_with_coordinates():
    locs = detect_locations("Vinpearl Nha Trang có gì vui")
    assert len(locs) == 1
    assert locs[0]["id"] == "nha-trang"
    assert locs[0]["lat"] == 12.2145
    assert locs[0]["lng"] == 109.2962
    assert locs[0]["zoom"] >= 1


def test_detects_alias_without_diacritics():
    assert detect_locations("dat phong o dao Hon Tre")[0]["id"] == "nha-trang"
    assert detect_locations("resort o Nghe An")[0]["id"] == "cua-hoi"


def test_returns_multiple_in_order_of_appearance():
    locs = detect_locations("Cho tôi thông tin Vinpearl Phú Quốc và Hạ Long")
    assert [loc["id"] for loc in locs] == ["phu-quoc", "ha-long"]


def test_no_location_returns_empty():
    assert detect_locations("Khách sạn có wifi miễn phí không?") == []


def test_limit_caps_results():
    text = " ".join(loc["aliases"][0] for loc in VINPEARL_LOCATIONS)
    assert len(detect_locations(text, limit=2)) == 2
