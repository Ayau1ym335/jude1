"""Seeded failures for the pytest-based CI stages (XC-FND-03).

Each test is skipped unless JUDE_CI_SEED names its stage (or "all"). Then it fails, which
must turn that stage red and block the merge. The tests also keep every stage's marker
selection non-empty, so a stage without content yet still collects and runs.

Seed a run:  JUDE_CI_SEED=unit bash scripts/ci/stage.sh unit   (exit code must be non-zero)
"""

import os

import pytest

SEED = os.environ.get("JUDE_CI_SEED", "")


def seeded(stage: str) -> bool:
    return SEED in (stage, "all")


def _fail(stage: str) -> None:
    pytest.fail(f"seeded failure for CI stage '{stage}' (JUDE_CI_SEED={SEED})")


@pytest.mark.skipif(not seeded("unit"), reason="JUDE_CI_SEED does not name 'unit'")
def test_seeded_unit_failure() -> None:
    _fail("unit")


@pytest.mark.determinism
@pytest.mark.skipif(not seeded("determinism"), reason="JUDE_CI_SEED does not name 'determinism'")
def test_seeded_determinism_failure() -> None:
    _fail("determinism")


@pytest.mark.contract
@pytest.mark.skipif(not seeded("contract"), reason="JUDE_CI_SEED does not name 'contract'")
def test_seeded_contract_failure() -> None:
    _fail("contract")


@pytest.mark.integration
@pytest.mark.skipif(not seeded("integration"), reason="JUDE_CI_SEED does not name 'integration'")
def test_seeded_integration_failure() -> None:
    _fail("integration")


@pytest.mark.oracle
@pytest.mark.skipif(not seeded("oracle"), reason="JUDE_CI_SEED does not name 'oracle'")
def test_seeded_oracle_failure() -> None:
    _fail("oracle")


@pytest.mark.security
@pytest.mark.skipif(not seeded("security"), reason="JUDE_CI_SEED does not name 'security'")
def test_seeded_security_failure() -> None:
    _fail("security")


@pytest.mark.e2e
@pytest.mark.skipif(not seeded("e2e"), reason="JUDE_CI_SEED does not name 'e2e'")
def test_seeded_e2e_failure() -> None:
    _fail("e2e")


@pytest.mark.performance
@pytest.mark.skipif(not seeded("performance"), reason="JUDE_CI_SEED does not name 'performance'")
def test_seeded_performance_failure() -> None:
    _fail("performance")
