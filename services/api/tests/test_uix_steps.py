"""UT-FN-UIX-03: gate and job status presentation (TSK-UIX-03-B; NFR-05, FR-014, FR-032).

Completion criterion: each gate code has a resource string and a target step.
"""

from collections import Counter
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from jude_api.domain.uix import TARGETS, WORKFLOW, gate_steps, step_label_key, target_step
from jude_api.domain.uix import steps as steps_module
from jude_api.main import API_PREFIX, create_app
from jude_api.platform.errors import ApiError, Gate, catalogue, error_body, messages_ru
from jude_api.platform.schemas import ErrorResponse, StepTarget


def test_completion_criterion_every_code_has_a_resource_string_and_a_target_step() -> None:
    assert set(gate_steps()) == set(catalogue())  # no code without a step, no stale entry
    for code, entry in catalogue().items():
        assert messages_ru()[entry["message_key"]].strip(), code
        assert target_step(code) in TARGETS, code
        assert messages_ru()[step_label_key(target_step(code))].strip(), code


def test_every_target_has_a_russian_label_and_no_label_is_orphaned() -> None:
    labels = {k for k in messages_ru() if k.startswith("step.")}
    assert labels == {f"step.{t}" for t in TARGETS}


def test_every_workflow_step_resolves_at_least_one_code() -> None:
    used = Counter(gate_steps().values())
    assert all(used[s] > 0 for s in WORKFLOW), used


def test_schema_literal_matches_the_targets() -> None:
    assert StepTarget.__args__ == TARGETS  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("code", "step"),
    [
        ("PRESCRIPTION_MISSING", "S2"),  # raised at approval, resolved by attaching the document
        ("FRAME_NOT_CONFIRMED", "S6"),  # raised by measurement and design, resolved in anatomy
        ("GATE_BLOCKED", "S4"),
        ("LANDMARKS_INCOMPLETE", "S6"),
        ("SELF_INTERSECTION_CREATED", "S8"),  # kernel codes in gates[] resolve too
        ("CHECKLIST_INCOMPLETE", "S10"),
        ("SESSION_EXPIRED", "SIGN_IN"),
        ("CONFIG_NOT_SET", "ADMIN"),
        ("VERSION_CONFLICT", "CURRENT"),
    ],
)
def test_representative_steps(code: str, step: str) -> None:
    assert target_step(code) == step


def test_error_body_enriches_every_gate() -> None:
    body = error_body(
        "VALIDITY_FAILED",
        [Gate(code="SELF_INTERSECTION_CREATED", detail="op 3"), Gate(code="FRAME_NOT_CONFIRMED")],
    )
    assert body["step"] == "S9"
    assert [(g["code"], g["step"]) for g in body["gates"]] == [
        ("SELF_INTERSECTION_CREATED", "S8"),
        ("FRAME_NOT_CONFIRMED", "S6"),
    ]
    assert body["gates"][1]["message_ru"] == messages_ru()["error.frame_not_confirmed"]
    ErrorResponse.model_validate(body)  # the contract model accepts it (extra="forbid")


def test_every_refusal_body_validates_against_the_contract() -> None:
    app = create_app(db_check=lambda: None, readiness_checks={})

    @app.get(f"{API_PREFIX}/_gate/{{code}}")
    def refuse(code: str) -> None:
        raise ApiError(code, gates=[Gate(code=c) for c in sorted(catalogue())[:3]])

    client = TestClient(app, raise_server_exceptions=False)
    for code in sorted(c for c, e in catalogue().items() if e["kind"] == "refusal"):
        body = client.get(f"{API_PREFIX}/_gate/{code}").json()
        assert ErrorResponse.model_validate(body).step == target_step(code)
        assert all(g["step"] == target_step(g["code"]) for g in body["gates"])


def test_unknown_code_and_target_are_programming_errors() -> None:
    with pytest.raises(KeyError):
        target_step("NO_SUCH_CODE")
    with pytest.raises(KeyError):
        step_label_key("S13")


def test_a_table_with_an_unknown_target_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "gate_steps.json").write_text(
        json.dumps({"schema": "gate-steps/1", "codes": {"INTERNAL": "S0"}}), encoding="utf-8"
    )
    monkeypatch.setattr(steps_module, "HERE", tmp_path)
    steps_module.gate_steps.cache_clear()
    try:
        with pytest.raises(ValueError, match="unknown target step"):
            steps_module.gate_steps()
        (tmp_path / "gate_steps.json").write_text('{"schema": "x/1", "codes": {}}', "utf-8")
        with pytest.raises(ValueError, match="schema"):
            steps_module.gate_steps()
    finally:
        steps_module.gate_steps.cache_clear()
