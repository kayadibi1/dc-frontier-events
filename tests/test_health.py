from aggregator.health import classify, update_health


def test_classify():
    assert classify(5, None) == "ok"
    assert classify(0, None) == "empty"
    assert classify(3, "HTTP 403") == "error"   # error wins even with a count


def test_ok_source_records_success_today():
    health, regressions = update_health({}, [("itif", 5, None)], "2026-06-02")
    assert health["itif"]["status"] == "ok"
    assert health["itif"]["count"] == 5
    assert health["itif"]["last_success"] == "2026-06-02"
    assert health["itif"]["fail_streak"] == 0
    assert regressions == []


def test_regression_when_previously_ok_now_failing():
    prior = {"cdt": {"status": "ok", "count": 12, "last_success": "2026-06-01", "fail_streak": 0}}
    health, regressions = update_health(prior, [("cdt", 0, "HTTP 403")], "2026-06-02")
    assert "cdt" in regressions
    assert health["cdt"]["status"] == "error"
    assert health["cdt"]["fail_streak"] == 1
    assert health["cdt"]["last_success"] == "2026-06-01"   # carried forward


def test_still_failing_is_not_a_new_regression():
    prior = {"x": {"status": "empty", "count": 0, "last_success": None, "fail_streak": 2}}
    health, regressions = update_health(prior, [("x", 0, None)], "2026-06-02")
    assert regressions == []                # already failing, not newly broken
    assert health["x"]["fail_streak"] == 3


def test_brand_new_failing_source_is_not_a_regression():
    health, regressions = update_health({}, [("new", 0, "HTTP 500")], "2026-06-02")
    assert regressions == []
    assert health["new"]["fail_streak"] == 1
