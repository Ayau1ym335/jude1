"""X-06 §6.3-6.4: the worker seeds the numba cache and loads every kernel before it is ready."""

from pathlib import Path

from jude_worker import kernel_warmup


def test_seed_cache_copies_once(tmp_path: Path) -> None:
    src = tmp_path / "prefilled"
    (src / "sub").mkdir(parents=True)
    (src / "sub" / "f.nbi").write_bytes(b"x")
    env = {"JUDE_NUMBA_PREFILLED_CACHE": str(src), "NUMBA_CACHE_DIR": str(tmp_path / "cache")}
    assert kernel_warmup.seed_cache(env) is True
    assert (tmp_path / "cache" / "sub" / "f.nbi").read_bytes() == b"x"
    assert kernel_warmup.seed_cache(env) is False  # already there: left alone


def test_seed_cache_without_configuration_is_a_no_op(tmp_path: Path) -> None:
    assert kernel_warmup.seed_cache({}) is False
    assert (
        kernel_warmup.seed_cache(
            {
                "JUDE_NUMBA_PREFILLED_CACHE": str(tmp_path / "missing"),
                "NUMBA_CACHE_DIR": str(tmp_path / "c"),
            }
        )
        is False
    )


def test_warm_up_loads_predicates() -> None:
    assert kernel_warmup.warm_up() >= 0.0
