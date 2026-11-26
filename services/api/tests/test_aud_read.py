"""UT-FN-AUD-02: the read-event mapping (no database)."""

from jude_api.platform import aud
from jude_api.platform.aud_read import READ_EVENTS, ReadKind


def test_every_object_type_of_fn_aud_02_has_its_catalogued_event() -> None:
    fs_events = {"blob.read", "export.downloaded", "report.downloaded", "audit.exported",
                 "prescription.read"}  # fmt: skip
    assert set(READ_EVENTS) == set(ReadKind)
    assert {e.event_type for e in READ_EVENTS.values()} == fs_events
    catalogue = aud.event_types()
    assert all(not catalogue[e]["reserved"] for e in fs_events)
    assert len({e.object_type for e in READ_EVENTS.values()}) == len(READ_EVENTS)
