"""Critical-path tests: auth, role enforcement, assignment rules. Run against the configured Postgres DB
using unique emails per run (no cleanup needed)."""
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PW = "Password123"


def signup(name="User"):
    email = f"{name.lower()}-{uuid.uuid4().hex[:8]}@test.com"
    r = client.post("/api/auth/signup", json={"name": name, "email": email, "password": PW})
    assert r.status_code == 201, r.text
    return {"email": email, "id": r.json()["user"]["id"], "h": {"Authorization": f"Bearer {r.json()['access_token']}"}}


@pytest.fixture()
def team():
    owner, member, outsider = signup("Owner"), signup("Member"), signup("Outsider")
    pid = client.post("/api/projects", json={"name": "P"}, headers=owner["h"]).json()["id"]
    r = client.post(f"/api/projects/{pid}/members", json={"email": member["email"]}, headers=owner["h"])
    assert r.status_code == 201
    return owner, member, outsider, pid


def test_password_rules_and_email():
    r = client.post("/api/auth/signup", json={"name": "x", "email": "bad", "password": "short"})
    assert r.status_code == 422
    r = client.post("/api/auth/signup", json={"name": "x", "email": "a@b.com", "password": "alllettersss"})
    assert r.status_code == 422


def test_unauthenticated_is_401():
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/projects", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_refresh_rotation_and_reuse():
    email = f"r-{uuid.uuid4().hex[:6]}@test.com"
    c = TestClient(app)
    c.post("/api/auth/signup", json={"name": "R", "email": email, "password": PW})
    old = c.cookies.get("refresh_token", path="/api/auth")
    assert c.post("/api/auth/refresh").status_code == 200
    c2 = TestClient(app)
    c2.cookies.set("refresh_token", old, path="/api/auth")
    assert c2.post("/api/auth/refresh").status_code == 401  # rotated token cannot be replayed


def test_non_member_cannot_access_project(team):
    owner, member, outsider, pid = team
    assert client.get(f"/api/projects/{pid}", headers=outsider["h"]).status_code == 404
    assert client.get(f"/api/projects/{pid}/tasks", headers=outsider["h"]).status_code == 404
    assert client.post(f"/api/projects/{pid}/tasks", json={"title": "x"}, headers=outsider["h"]).status_code == 404


def test_member_cannot_invite_or_delete(team):
    owner, member, outsider, pid = team
    assert client.post(f"/api/projects/{pid}/members", json={"email": outsider["email"]}, headers=member["h"]).status_code == 403
    assert client.delete(f"/api/projects/{pid}", headers=member["h"]).status_code == 403


def test_task_validation(team):
    owner, member, outsider, pid = team
    url = f"/api/projects/{pid}/tasks"
    assert client.post(url, json={"title": "   "}, headers=owner["h"]).status_code == 422
    past = (date.today() - timedelta(days=1)).isoformat()
    assert client.post(url, json={"title": "t", "due_date": past}, headers=owner["h"]).status_code == 422
    r = client.post(url, json={"title": "t", "assignee_id": outsider["id"]}, headers=owner["h"])
    assert r.status_code == 422


def test_done_permission_and_completed_date(team):
    owner, member, outsider, pid = team
    t = client.post(f"/api/projects/{pid}/tasks", json={"title": "t", "assignee_id": owner["id"]}, headers=owner["h"]).json()
    mv = f"/api/projects/{pid}/tasks/{t['id']}/move"
    r = client.post(mv, json={"status": "done"}, headers=member["h"])
    assert r.status_code == 403
    r = client.post(mv, json={"status": "done"}, headers=owner["h"])
    assert r.status_code == 200 and r.json()["completed_at"]
    r = client.post(mv, json={"status": "todo"}, headers=owner["h"])
    assert r.json()["completed_at"] is None


def test_remove_member_keeps_tasks_and_unassigns(team):
    owner, member, outsider, pid = team
    t = client.post(f"/api/projects/{pid}/tasks", json={"title": "mine", "assignee_id": member["id"]}, headers=member["h"]).json()
    assert client.delete(f"/api/projects/{pid}/members/{member['id']}", headers=owner["h"]).status_code == 200
    r = client.get(f"/api/projects/{pid}/tasks/{t['id']}", headers=owner["h"]).json()
    assert r["assignee"] is None and r["creator"]["id"] == member["id"]
    assert client.get(f"/api/projects/{pid}", headers=member["h"]).status_code == 404
    # removed user can no longer be assigned
    assert client.patch(f"/api/projects/{pid}/tasks/{t['id']}", json={"assignee_id": member["id"]}, headers=owner["h"]).status_code == 422


def test_pagination_sorting_filter(team):
    owner, member, outsider, pid = team
    for i, pr in enumerate(["low", "high", "medium", "high", "low"]):
        client.post(f"/api/projects/{pid}/tasks", json={"title": f"task {i}", "priority": pr}, headers=owner["h"])
    r = client.get(f"/api/projects/{pid}/tasks?page=1&page_size=2&sort_by=priority&order=desc", headers=owner["h"]).json()
    assert r["total"] == 5 and r["pages"] == 3 and len(r["items"]) == 2
    assert all(t["priority"] == "high" for t in r["items"])
    r = client.get(f"/api/projects/{pid}/tasks?priority=low&search=task", headers=owner["h"]).json()
    assert r["total"] == 2


def test_assigned_to_me_and_delete_cascade(team):
    owner, member, outsider, pid = team
    client.post(f"/api/projects/{pid}/tasks", json={"title": "for member", "assignee_id": member["id"]}, headers=owner["h"])
    mine = client.get("/api/me/assigned", headers=member["h"]).json()
    assert any(t["title"] == "for member" for t in mine)
    assert client.delete(f"/api/projects/{pid}", headers=owner["h"]).status_code == 204
    assert client.get("/api/me/assigned", headers=member["h"]).json() == []
