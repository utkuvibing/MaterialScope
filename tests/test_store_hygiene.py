"""PR-14: store hygiene — copy-on-read, per-project locks, autosave journal."""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest

from backend.store import ProjectStore
from core.data_io import ThermalDataset, read_thermal_data


def _state(marker: str = "v1") -> dict:
    return {
        "datasets": {},
        "results": {},
        "history": [{"event": marker}],
        "branding": {"app_name": "MaterialScope"},
        "active_dataset": None,
    }


def _thermal_dataset() -> ThermalDataset:
    return ThermalDataset(
        data=pd.DataFrame({"temperature": np.linspace(30, 300, 50), "signal": np.linspace(0, 1, 50)}),
        metadata={"sample_name": "S", "sample_mass": 5.0},
        data_type="DSC",
        units={"temperature": "degC", "signal": "mW/mg"},
        original_columns={"temperature": "temperature", "signal": "signal"},
        file_path="",
    )


class TestCopyOnRead:
    def test_get_returns_independent_copy(self):
        store = ProjectStore(autosave=False)
        pid = store.put(_state())

        first = store.get(pid)
        first["history"].append({"event": "mutated"})
        first["branding"]["app_name"] = "Corrupted"
        first["datasets"]["x"] = "injected"

        second = store.get(pid)
        assert second["history"] == [{"event": "v1"}]
        assert second["branding"]["app_name"] == "MaterialScope"
        assert second["datasets"] == {}

    def test_set_stores_independent_copy(self):
        store = ProjectStore(autosave=False)
        pid = store.put(_state())

        state = store.get(pid)
        state["active_dataset"] = "ds1"
        assert store.set(pid, state)

        state["active_dataset"] = "tampered-after-set"
        state["results"]["bad"] = {}

        restored = store.get(pid)
        assert restored["active_dataset"] == "ds1"
        assert restored["results"] == {}

    def test_live_dataset_objects_are_copied(self):
        store = ProjectStore(autosave=False)
        state = _state()
        state["datasets"]["d1"] = _thermal_dataset()
        pid = store.put(state)

        fetched = store.get(pid)
        fetched["datasets"]["d1"].data.loc[0, "signal"] = 999.0
        fetched["datasets"]["d1"].metadata["sample_name"] = "tampered"

        clean = store.get(pid)
        assert clean["datasets"]["d1"].data.loc[0, "signal"] != 999.0
        assert clean["datasets"]["d1"].metadata["sample_name"] == "S"


class TestPerProjectLocks:
    def test_distinct_projects_get_distinct_locks(self):
        store = ProjectStore(autosave=False)
        assert store._lock_for("a") is not store._lock_for("b")
        assert store._lock_for("a") is store._lock_for("a")

    def test_missing_project_set_returns_false(self):
        store = ProjectStore(autosave=False)
        assert store.set("nonexistent", _state()) is False
        assert store.get("nonexistent") is None


class TestAutosaveJournal:
    def test_put_and_set_write_journal(self, tmp_path):
        store = ProjectStore(journal_dir=tmp_path)
        pid = store.put(_state())
        journal = tmp_path / f"{pid}.msjournal"
        assert journal.exists()

        state = store.get(pid)
        state["branding"]["app_name"] = "Updated"
        store.set(pid, state)
        # Journal rewritten — a fresh store sees the update, not the original.
        reloaded = ProjectStore(journal_dir=tmp_path)
        restored = reloaded.get(pid)
        assert restored["branding"]["app_name"] == "Updated"

    def test_restart_restores_workspace_losslessly(self, tmp_path):
        store = ProjectStore(journal_dir=tmp_path)
        state = _state()
        state["datasets"]["d1"] = _thermal_dataset()
        state["results"]["r1"] = {"id": "r1", "analysis_type": "DSC"}
        state["comparison_workspace"] = {"rows": [{"a": 1}]}
        pid = store.put(state)

        # Simulate a crash: brand-new store, empty memory, same journal dir.
        fresh = ProjectStore(journal_dir=tmp_path)
        restored = fresh.get(pid)
        assert restored is not None
        assert restored["results"]["r1"]["analysis_type"] == "DSC"
        assert restored["comparison_workspace"] == {"rows": [{"a": 1}]}
        assert isinstance(restored["datasets"]["d1"], ThermalDataset)
        pd.testing.assert_frame_equal(
            restored["datasets"]["d1"].data, state["datasets"]["d1"].data
        )

    def test_set_restores_then_updates_from_journal(self, tmp_path):
        store = ProjectStore(journal_dir=tmp_path)
        pid = store.put(_state())

        fresh = ProjectStore(journal_dir=tmp_path)
        assert fresh.set(pid, _state(marker="v2")) is True
        assert fresh.get(pid)["history"] == [{"event": "v2"}]

    def test_corrupt_journal_is_ignored(self, tmp_path):
        store = ProjectStore(journal_dir=tmp_path)
        pid = store.put(_state())
        (tmp_path / f"{pid}.msjournal").write_bytes(b"not a pickle")

        fresh = ProjectStore(journal_dir=tmp_path)
        assert fresh.get(pid) is None

    def test_autosave_disabled_writes_nothing(self, tmp_path):
        store = ProjectStore(journal_dir=tmp_path, autosave=False)
        pid = store.put(_state())
        assert not (tmp_path / f"{pid}.msjournal").exists()
        assert store.journal_enabled is False

    def test_autosave_true_without_dir_raises(self, monkeypatch):
        monkeypatch.delenv("MATERIALSCOPE_JOURNAL_DIR", raising=False)
        monkeypatch.delenv("MATERIALSCOPE_HOME", raising=False)
        monkeypatch.delenv("THERMOANALYZER_HOME", raising=False)
        with pytest.raises(ValueError, match="journal"):
            ProjectStore(autosave=True)

    def test_journal_roundtrip_through_import_endpoint_shape(self, tmp_path):
        # Journal payloads must survive real ThermalDataset objects produced
        # by the import path, not just hand-built fixtures.
        csv = "Temp/°C,DSC/(mW/mg)\n25,0.1\n50,0.2\n75,0.3\n"
        buf = io.BytesIO(csv.encode("utf-8"))
        buf.name = "dsc.csv"
        ds = read_thermal_data(buf, data_type="DSC")

        store = ProjectStore(journal_dir=tmp_path)
        pid = store.put({"datasets": {"d": ds}, "results": {}, "history": []})

        fresh = ProjectStore(journal_dir=tmp_path)
        restored = fresh.get(pid)
        assert restored["datasets"]["d"].data_type == "DSC"
        pd.testing.assert_frame_equal(restored["datasets"]["d"].data, ds.data)
