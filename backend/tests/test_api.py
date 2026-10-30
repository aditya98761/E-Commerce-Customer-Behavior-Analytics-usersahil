import io

from tests.synthetic import make_raw


def _csv_bytes():
    buf = io.StringIO()
    make_raw().to_csv(buf, index=False)
    return buf.getvalue().encode()


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_empty_state_before_import(client):
    s = client.get("/api/dashboard/summary").json()
    assert s["has_data"] is False and s["revenue"] == 0


def test_rejects_bad_upload(client):
    r = client.post("/api/import", files={"file": ("x.txt", b"hello")})
    assert r.status_code == 400


def test_run_fails_gracefully_without_data(client):
    r = client.post("/api/runs", json={"run_type": "rfm"})
    assert r.status_code == 202
    run = client.get(f"/api/runs/{r.json()['id']}").json()
    assert run["status"] == "failed" and "Import a dataset" in run["error"]


def test_param_validation(client):
    r = client.post("/api/runs", json={"run_type": "clustering", "params": {"k_min": 6, "k_max": 3}})
    assert r.status_code == 422
    assert client.post("/api/runs", json={"run_type": "nope"}).status_code == 422


def test_full_pipeline(client):
    r = client.post("/api/import", files={"file": ("synthetic_test.csv", _csv_bytes(), "text/csv")})
    assert r.status_code == 202
    imp = client.get("/api/import/latest").json()["run"]
    assert imp["status"] == "completed", imp["error"]
    assert imp["result"]["exact_duplicates_removed"] == 1

    s = client.get("/api/dashboard/summary").json()
    assert s["has_data"] and s["revenue"] > 0 and s["cancelled_orders"] == 1
    assert 0 < s["repeat_purchase_rate"] <= 1
    assert abs(s["avg_order_value"] - s["revenue"] / s["orders"]) < 0.01

    assert client.get("/api/dashboard/trends?granularity=month").json()
    tp = client.get("/api/dashboard/top-products?limit=5").json()
    assert len(tp) == 5 and tp[0]["revenue"] >= tp[-1]["revenue"]
    assert client.get("/api/dashboard/countries").json()[0]["revenue"] > 0

    for body in ({"run_type": "rfm"}, {"run_type": "clustering", "params": {"k_max": 5}},
                 {"run_type": "basket", "params": {"min_support": 0.1, "min_confidence": 0.5, "top_n": 30}},
                 {"run_type": "forecast", "params": {"horizon": 14}}):
        rid = client.post("/api/runs", json=body).json()["id"]
        run = client.get(f"/api/runs/{rid}").json()
        assert run["status"] == "completed", run["error"]

    page = client.get("/api/customers?page=1&page_size=10&segment=Champions").json()
    assert page["rfm_run_id"] and all(c["segment"] == "Champions" for c in page["items"])
    assert client.get("/api/customers?search=12001").json()["total"] == 1
    assert client.get("/api/rfm/summary").json()["run"]["result"]["segments"]
    assert client.get("/api/clusters/latest").json()["run"]["result"]["silhouette"] is not None
    assert client.get("/api/association-rules?min_lift=1").json()["total"] > 0
    f = client.get("/api/forecast/latest").json()
    assert {p["phase"] for p in f["series"]} == {"train", "test", "future"}
    hist = client.get("/api/runs?run_type=forecast").json()
    assert hist["total"] >= 1 and hist["items"][0]["duration_s"] is not None
