"""Phase 15: AI assistant — grounding tools, permissions/scope, streaming, transcript integrity, history.

Claude is replaced by a scripted client with the same streaming surface as the SDK, so these tests exercise the real
loop, tools, persistence and request shape without network access or an API key.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services.assistant.service import FALLBACK_BETA, SYSTEM_PROMPT, AssistantClient, RateLimiter
from app.services.assistant.tools import TOOL_DEFINITIONS
from tests.org_helpers import Workspace, auth
from tests.test_agent_api import enrol_member
from tests.test_productivity_api import workday


class Block:
    def __init__(self, **data: Any) -> None:
        self.__dict__.update(data)
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)


def text(value: str) -> Block:
    return Block(type="text", text=value)


def thinking() -> Block:
    return Block(type="thinking", thinking="", signature="sig-abc")


def tool(name: str, args: dict[str, Any], id_: str = "toolu_1") -> Block:
    return Block(type="tool_use", id=id_, name=name, input=args)


def reply(*blocks: Block, stop: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(content=list(blocks), stop_reason=stop)


class FakeStream:
    def __init__(self, message: SimpleNamespace) -> None:
        self.message = message

    async def __aenter__(self) -> FakeStream:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    def __aiter__(self) -> Any:
        async def events() -> Any:
            for block in self.message.content:
                if block.type == "text":
                    yield SimpleNamespace(type="text", text=block.text)

        return events()

    async def get_final_message(self) -> SimpleNamespace:
        return self.message


class FakeClaude:
    def __init__(self, *script: SimpleNamespace) -> None:
        self.script = list(script)
        self.requests: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs: Any) -> FakeStream:
        self.requests.append(copy.deepcopy(kwargs))
        return FakeStream(self.script.pop(0))


@pytest.fixture
def claude(client: TestClient) -> Iterator[Any]:
    state = client.app.state  # type: ignore[attr-defined]
    previous = getattr(state, "assistant_client", None)

    def use(*script: SimpleNamespace) -> FakeClaude:
        fake = FakeClaude(*script)
        state.assistant_client = AssistantClient(client=fake, model="claude-opus-5-5")
        state.assistant_limiter = RateLimiter()
        return fake

    yield use
    if previous is not None:
        state.assistant_client = previous


def ask(
    client: TestClient, token: str, message: str, conversation_id: str | None = None
) -> tuple[int, list[dict[str, Any]]]:
    body: dict[str, Any] = {"message": message}
    if conversation_id:
        body["conversation_id"] = conversation_id
    response = client.post("/api/assistant/ask", json=body, headers=auth(token))
    if response.status_code != 200:
        return response.status_code, [response.json()]
    events = [
        json.loads(chunk[len("data: ") :])
        for chunk in response.text.split("\n\n")
        if chunk.startswith("data: ")
    ]
    return 200, events


def test_off_without_a_key_and_only_for_report_viewers(ws: Workspace, client: TestClient) -> None:
    state = client.app.state  # type: ignore[attr-defined]
    state.assistant_client = AssistantClient(client=None, model="claude-opus-5-5")
    status = ws.get("/assistant/status").json()
    assert status["configured"] is False and status["model"] is None
    assert "Which tasks are overdue?" in status["suggestions"]
    code, (error,) = ask(client, ws.admin.token, "What happened today?")
    assert code == 503 and error["error"]["code"] == "assistant_not_configured"
    employee = ws.member("Eve Employee")
    assert ws.get("/assistant/status", token=employee.token).status_code == 403
    assert ws.get("/assistant/conversations", token=employee.token).status_code == 403


def test_answers_from_tools_streams_cards_and_replays_history_unchanged(
    ws: Workspace, client: TestClient, claude: Any
) -> None:
    fake = claude(
        reply(
            thinking(), text("Let me check who is online. "), tool("get_live_presence", {}), stop="tool_use"
        ),
        reply(text("**0** people are active right now. [Open Live Tracking](/live)")),
        reply(thinking(), text("Nothing else has changed.")),
    )
    code, events = ask(client, ws.admin.token, "How many employees are currently active?")
    assert code == 200
    kinds = [e["type"] for e in events]
    assert kinds[0] == "start" and kinds[-1] == "done" and "error" not in kinds
    assert [e["status"] for e in events if e["type"] == "tool"] == ["running", "done"]
    (card,) = [e["card"] for e in events if e["type"] == "card"]
    assert card["kind"] == "metrics" and [m["label"] for m in card["metrics"]] == [
        "Online",
        "Active",
        "Idle",
        "Offline",
    ]
    assert card["link"]["href"] == "/live" and card["source"]
    streamed = "".join(e["delta"] for e in events if e["type"] == "text")
    assert streamed.endswith("[Open Live Tracking](/live)")
    done = events[-1]["turn"]
    assert done["tools"] == [
        {"name": "get_live_presence", "label": "Checking who is online", "status": "done"}
    ]

    first, second = fake.requests[0], fake.requests[1]
    assert (
        first["model"] == "claude-opus-5-5"
        and first["system"] == SYSTEM_PROMPT
        and first["tools"] == TOOL_DEFINITIONS
    )
    assert first["thinking"] == {"type": "adaptive"} and first["output_config"] == {"effort": "medium"}
    assert first["betas"] == [FALLBACK_BETA] and first["fallbacks"] == "default"
    assert first["cache_control"] == {"type": "ephemeral"}
    assert all(t["eager_input_streaming"] is True for t in first["tools"])
    question = first["messages"][-1]["content"]
    assert (
        question[0]["text"].startswith("[Context: it is ")
        and question[1]["text"] == "How many employees are currently active?"
    )
    # The assistant's turn (thinking included) goes back exactly as returned, then the tool result.
    assert second["messages"][1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig-abc"}
    tool_result = second["messages"][2]["content"][0]
    assert (
        tool_result["type"] == "tool_result" and json.loads(tool_result["content"])["counts"]["online"] == 0
    )

    conversation_id = events[0]["conversation_id"]
    code, _ = ask(client, ws.admin.token, "Anything else?", conversation_id)
    assert code == 200
    third = fake.requests[2]["messages"]
    assert (
        third[: len(second["messages"]) + 1][:-1] == second["messages"]
    )  # append-only: earlier turns untouched
    assert third[3]["role"] == "assistant" and third[3]["content"][0]["text"].startswith("**0** people")

    saved = ws.get(f"/assistant/conversations/{conversation_id}").json()
    assert [t["role"] for t in saved["turns"]] == ["user", "assistant", "user", "assistant"]
    assert saved["turns"][1]["cards"][0]["kind"] == "metrics" and saved["title"].startswith(
        "How many employees"
    )
    (summary,) = [c for c in ws.get("/assistant/conversations").json() if c["id"] == conversation_id]
    assert summary["questions"] == 2


def test_tools_run_as_the_person_asking(ws: Workspace, client: TestClient, claude: Any) -> None:
    manager = ws.member("Mona Manager", role="MANAGER")
    _, agent = enrol_member(ws, "Rafi Report", manager_employee_id=manager.employee_id)
    _, outsider_agent = enrol_member(ws, "Oona Outside")
    workday(agent)
    workday(outsider_agent)
    claude(
        reply(
            tool("get_attendance_summary", {"period": "last_7_days"}, "toolu_a"),
            tool(
                "get_employee_summary", {"employee_name": "Oona Outside", "period": "last_7_days"}, "toolu_b"
            ),
            stop="tool_use",
        ),
        reply(text("Rafi worked one day.")),
    )
    code, events = ask(client, manager.token, "Show this week's attendance summary.")
    assert code == 200
    statuses = {e["name"]: e for e in events if e["type"] == "tool" and e["status"] != "running"}
    assert statuses["get_attendance_summary"]["status"] == "done"
    assert (
        statuses["get_employee_summary"]["status"] == "error"
        and "No one called" in statuses["get_employee_summary"]["message"]
    )
    (card,) = [e["card"] for e in events if e["type"] == "card"]
    people = {r["employee"] for r in card["rows"]}
    assert "Rafi Report" in people and "Oona Outside" not in people  # the manager's scope, not everyone's
    rafi = next(r for r in card["rows"] if r["employee"] == "Rafi Report")
    assert rafi["days_worked"] == 1 and rafi["hours"] == "5h 00m" and rafi["typical_start"] == "09:00"
    assert "not an absence" in card["note"]


def test_overdue_tasks_carry_deep_links_and_unknown_names_are_errors(
    ws: Workspace, client: TestClient, claude: Any
) -> None:
    project = ws.post("/projects", {"name": "Assist", "key": "AS", "member_ids": []}).json()
    task = ws.post("/tasks", {"project_id": project["id"], "title": "Late", "due_date": "2026-01-02"}).json()
    claude(
        reply(
            tool("list_overdue_tasks", {"project": "assist"}, "toolu_1"),
            tool("get_project_time", {"project": "Nope", "period": "this_month"}, "toolu_2"),
            tool(
                "get_team_activity",
                {"period": "custom", "start": "2026-01-01", "end": "2026-06-01"},
                "toolu_3",
            ),
            stop="tool_use",
        ),
        reply(text("One task is overdue.")),
    )
    code, events = ask(client, ws.admin.token, "Which tasks are overdue?")
    assert code == 200
    (card,) = [e["card"] for e in events if e["type"] == "card"]
    (row,) = card["rows"]
    assert row["reference"] == "AS-1" and row["href"] == f"/projects/{project['id']}?task={task['id']}"
    errors = {e["name"]: e["message"] for e in events if e["type"] == "tool" and e["status"] == "error"}
    assert "No project matching" in errors["get_project_time"]
    assert "at most 31 days" in errors["get_team_activity"]


def test_refusals_errors_rate_limit_and_clearing(ws: Workspace, client: TestClient, claude: Any) -> None:
    fake = claude(reply(text("I can't"), stop="refusal"))
    code, events = ask(client, ws.admin.token, "Is Rafi lazy?")
    assert code == 200 and events[-2] == {
        "type": "error",
        "message": "The assistant can't help with that request.",
    }
    conversation_id = events[0]["conversation_id"]
    conversations = client.app.state.mongo.db["assistant_conversations"]  # type: ignore[attr-defined]
    stored = client.portal.call(conversations.find_one, {"title": "Is Rafi lazy?"})  # type: ignore[union-attr]
    assert (
        stored["transcript"] == [] and len(stored["turns"]) == 2
    )  # a refused turn is never replayed to the model
    assert len(fake.requests) == 1

    state = client.app.state  # type: ignore[attr-defined]
    limiter = RateLimiter()
    for _ in range(60):
        limiter.allow(ws.admin.user_id, 60)
    state.assistant_limiter = limiter
    code, (error,) = ask(client, ws.admin.token, "Again?")
    assert code == 429 and error["error"]["code"] == "rate_limited"

    other = ws.member("Nia Neighbour", role="MANAGER")
    assert ws.get(f"/assistant/conversations/{conversation_id}", token=other.token).status_code == 404
    assert (
        ws.client.delete(
            f"/api/assistant/conversations/{conversation_id}", headers=auth(ws.admin.token)
        ).status_code
        == 204
    )
    assert ws.get(f"/assistant/conversations/{conversation_id}").status_code == 404
    assert ws.client.delete("/api/assistant/conversations", headers=auth(ws.admin.token)).status_code == 204
    assert ws.get("/assistant/conversations").json() == []
