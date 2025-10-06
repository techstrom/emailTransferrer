from email_transferrer.state import StateStore


def test_state_store_roundtrip(tmp_path):
    state_path = tmp_path / "state.json"
    store = StateStore(state_path)

    assert store.get_processed_uids("source") == set()

    store.record_processed_uids("source", ["1", "2"])
    assert store.get_processed_uids("source") == {"1", "2"}

    store.record_processed_uids("source", ["2", "3"])
    assert store.get_processed_uids("source") == {"1", "2", "3"}

    store.clear_source("source")
    assert store.get_processed_uids("source") == set()

