def _reloaded_storage(tmp_path, monkeypatch):
    from src import storage as storage_module

    monkeypatch.setattr(storage_module, "HISTORICAL_DIR", str(tmp_path))
    monkeypatch.setattr(storage_module, "SNAPSHOTS_DIR", str(tmp_path / "snapshots"))
    return storage_module


def test_save_and_load_run_snapshot(tmp_path, monkeypatch):
    storage = _reloaded_storage(tmp_path, monkeypatch)
    storage.save_run_snapshot("2026-01-05", {"clicks": 10})
    assert storage.load_run_snapshot("2026-01-05") == {"clicks": 10}
    assert storage.load_run_snapshot("2026-01-06") is None


def test_load_previous_run_snapshot_returns_most_recent_before_date(tmp_path, monkeypatch):
    storage = _reloaded_storage(tmp_path, monkeypatch)
    storage.save_run_snapshot("2026-01-05", {"week": 1})
    storage.save_run_snapshot("2026-01-12", {"week": 2})
    assert storage.load_previous_run_snapshot("2026-01-12") == {"week": 1}
    assert storage.load_previous_run_snapshot("2026-01-05") is None


def test_rank_history_round_trip(tmp_path, monkeypatch):
    storage = _reloaded_storage(tmp_path, monkeypatch)
    assert storage.load_rank_history() == {}
    storage.save_rank_history({"2026-01-05": {"jupiter homes for sale": 5.5}})
    assert storage.load_rank_history() == {"2026-01-05": {"jupiter homes for sale": 5.5}}


def test_sitemap_baseline_round_trip(tmp_path, monkeypatch):
    storage = _reloaded_storage(tmp_path, monkeypatch)
    assert storage.load_sitemap_baseline() == []
    storage.save_sitemap_baseline(["/b", "/a"])
    assert storage.load_sitemap_baseline() == ["/a", "/b"]
