import uuid
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _demo_headers():
    res = client.post("/api/auth/demo-login")
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_live_docs_public_and_access_control_scheduling():
    headers = _demo_headers()
    try:
        # 1) Default seeded state is publicly available
        pub = client.get("/api/live-docs/public")
        assert pub.status_code == 200
        body = pub.json()
        assert body["available"] is True
        assert len(body["sections"]) >= 26
        assert len(body["team"]) >= 4
        assert body["live_stats"]["counts"]["bd_drugs"] >= 100
        assert len(body["live_stats"]["api_routes"]) >= 40

        # 2) Toggle OFF -> 403
        off = client.put("/api/live-docs/admin/settings", json={"visibility_mode": "force_off"}, headers=headers)
        assert off.status_code == 200
        blocked = client.get("/api/live-docs/public")
        assert blocked.status_code == 403

        # 3) Schedule mode with default June 10-14 window (outside Nov 2026) -> 403
        sched = client.put(
            "/api/live-docs/admin/settings",
            json={
                "visibility_mode": "schedule",
                "publish_start_at": "2026-06-10T00:00:00+06:00",
                "publish_end_at": "2026-06-14T23:59:59+06:00",
            },
            headers=headers,
        )
        assert sched.status_code == 200
        assert client.get("/api/live-docs/public").status_code == 403

        # 4) Duration-based publishing (24h from now) -> 200
        dur = client.put(
            "/api/live-docs/admin/settings",
            json={"duration_hours": 24, "apply_duration_now": True},
            headers=headers,
        )
        assert dur.status_code == 200
        assert client.get("/api/live-docs/public").status_code == 200
    finally:
        # Restore default force_on state
        client.put(
            "/api/live-docs/admin/settings",
            json={
                "visibility_mode": "force_on",
                "publish_start_at": "2026-06-10T00:00:00+06:00",
                "publish_end_at": "2026-06-14T23:59:59+06:00",
            },
            headers=headers,
        )


def test_live_docs_admin_rbac_and_exports():
    # Regular user must be blocked from admin endpoints
    reg_email = f"docs_user_{uuid.uuid4().hex[:8]}@test.bd"
    reg = client.post(
        "/api/auth/register",
        json={"full_name": "Regular User", "email": reg_email, "password": "Password123!"},
    )
    assert reg.status_code == 201
    user_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    assert client.get("/api/live-docs/admin/state", headers=user_headers).status_code == 403

    # Super admin succeeds
    admin_headers = _demo_headers()
    state = client.get("/api/live-docs/admin/state", headers=admin_headers)
    assert state.status_code == 200
    assert len(state.json()["sections"]) >= 26

    # Markdown & PDF exports
    md = client.get("/api/live-docs/export/markdown")
    assert md.status_code == 200
    assert "MediTrackAI" in md.text

    pdf = client.get("/api/live-docs/export/pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
