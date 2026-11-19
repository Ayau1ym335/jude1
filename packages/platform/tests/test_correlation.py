"""IT-correlation (contract part): the ID survives API -> job payload -> worker (XC-FND-11)."""

from jude_platform import correlation


def test_accept_keeps_valid_and_replaces_invalid() -> None:
    assert correlation.accept("abc-12345678") == "abc-12345678"
    for bad in (
        None,
        "",
        "short",
        "x" * 65,
        "has space 123",
        "Иванова-1234567",
        "../../etc/passwd",
    ):
        new = correlation.accept(bad)
        assert new != bad and len(new) == 32


def test_bound_is_scoped() -> None:
    assert correlation.current() is None
    with correlation.bound("abcdef012345"):
        assert correlation.current() == "abcdef012345"
    assert correlation.current() is None


def test_payload_round_trip() -> None:
    with correlation.bound("req-0123456789"):
        payload = correlation.inject({"type": "regenerate.v1"})
    assert payload == {"type": "regenerate.v1", "correlation_id": "req-0123456789"}
    assert correlation.extract(payload) == "req-0123456789"


def test_extract_without_or_with_malformed_id_gives_fresh_id() -> None:
    assert len(correlation.extract({})) == 32
    assert len(correlation.extract({"correlation_id": 42})) == 32
