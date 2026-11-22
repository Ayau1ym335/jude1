"""T8: property-based inputs with a fixed hypothesis profile (FN-OPS-06, GTS T8).

    from jude_fixtures import t8
    t8.register()                      # once, e.g. in a conftest; then
    @t8.fixed                          # or settings(parent=settings.get_profile("jude-fixed"))
    @given(t8.face_selection(n_faces=320), t8.signed_value(lo, hi))

No strategy has a default range: magnitudes and offsets are always passed in by the test (no
clinical or production value is defaulted, DEC-029).
"""

from collections.abc import Callable
from typing import Any

from hypothesis import settings
from hypothesis import strategies as st

PROFILE = "jude-fixed"


def register() -> None:
    settings.register_profile(
        PROFILE, derandomize=True, database=None, max_examples=200, deadline=None, print_blob=True
    )


def fixed[F: Callable[..., Any]](fn: F) -> F:
    register()
    decorated: F = settings(settings.get_profile(PROFILE))(fn)
    return decorated


def face_selection(
    n_faces: int, min_size: int = 1, max_size: int | None = None
) -> st.SearchStrategy[list[int]]:
    """Sorted, unique face indices of a fixture mesh (a zone or a selection)."""
    top = n_faces if max_size is None else min(max_size, n_faces)
    return st.lists(
        st.integers(min_value=0, max_value=n_faces - 1),
        min_size=min_size,
        max_size=top,
        unique=True,
    ).map(sorted)


def signed_value(lo: float, hi: float) -> st.SearchStrategy[float]:
    """A finite value in [lo, hi] chosen by the test, including both ends and zero if inside."""
    if not lo < hi:
        raise ValueError("lo must be < hi")
    edges = [lo, hi] + ([0.0] if lo < 0.0 < hi else [])
    return st.one_of(st.sampled_from(edges), st.floats(min_value=lo, max_value=hi, allow_nan=False))
