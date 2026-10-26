"""The live table consumes committed records, not synthetic timer snapshots."""
import csv
import json
import sqlite3

import pytest

from membrane_control.controller import AppController
from membrane_control.models import Recipe, Step
from membrane_control.storage import RunStore
import membrane_control.storage as storage_module


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def app(tmp_path):
    clock = Clock()
    controller = AppController(tmp_path, clock)
    controller.tick()
    yield controller, clock
    controller.close()


def begin(controller, *, duration=120, interval=2):
    controller.load_recipe(Recipe(name="Recorded observations", sample_interval_s=interval,
                                 desired_flow_ml_min=125,
                                 steps=[Step("Filter sample", duration, pump_percent=15)]))
    controller.start_run()
    controller.tick()
    controller.tick()
    assert controller.run_id is not None
    return controller.run_id


def rows(controller):
    return controller.store.connection.execute(
        "SELECT run_id,time_utc,payload_json FROM samples ORDER BY id").fetchall()


def test_store_returns_the_exact_committed_timestamp_and_detached_payload(tmp_path, monkeypatch):
    store = RunStore(tmp_path)
    try:
        run_id = store.start(Recipe(), {}, {})
        timestamps = iter(["2026-10-26T12:34:56.789+00:00"])
        monkeypatch.setattr(storage_module, "utc_now", lambda: next(timestamps))
        snapshot = {"elapsed_s": 3, "step_name": "Filter", "valves": [True] + [False] * 6,
                    "mass_g": None, "flow_ml_min": None, "pressure_psi": None,
                    "desired_flow_ml_min": 125, "pump_percent": 15, "simulation": False}
        record = store.sample(run_id, snapshot)
        saved_run, timestamp, payload = store.connection.execute(
            "SELECT run_id,time_utc,payload_json FROM samples").fetchone()
        assert record == {"run_id": saved_run, "time_utc": timestamp, **json.loads(payload)}
        assert timestamp == "2026-10-26T12:34:56.789+00:00"
        assert record["mass_g"] is None and record["flow_ml_min"] is None
        assert record["step_name"] == "Filter"
        snapshot["valves"][0] = False
        assert record["valves"][0] is True
        record["valves"][1] = True
        assert json.loads(payload)["valves"][1] is False
    finally:
        store.close()


def test_idle_refreshes_do_not_create_recorded_readings(app):
    controller, clock = app
    for _ in range(50):
        clock.advance(0.1)
        controller.tick()
    assert controller.snapshot["controller_connected"]
    assert controller.recorded_samples_after(0) == []
    assert rows(controller) == []


def test_interval_events_match_database_and_keep_measurements_separate(app):
    controller, clock = app
    run_id = begin(controller, interval=2)
    initial = controller.recorded_samples_after(0)
    assert len(initial) == 1
    assert initial[0]["run_id"] == run_id
    assert initial[0]["step_name"] == "Filter sample"
    assert initial[0]["desired_flow_ml_min"] == 125
    assert initial[0]["flow_ml_min"] != 125
    for _ in range(3):
        clock.advance(0.5)
        controller.tick()
    assert len(controller.recorded_samples_after(0)) == 1
    clock.advance(0.51)
    controller.tick()
    events = controller.recorded_samples_after(0)
    assert len(events) == 2
    for event, (saved_run, timestamp, payload) in zip(events, rows(controller), strict=True):
        expected = {"run_id": saved_run, "time_utc": timestamp, **json.loads(payload)}
        assert {key: value for key, value in event.items() if key != "_sample_sequence"} == expected
    assert [event["_sample_sequence"] for event in events] == [1, 2]
    assert controller.recorded_samples_after(1) == events[1:]
    assert controller.recorded_samples_after(2) == []


def test_final_stop_sample_is_an_event_even_before_next_recording_interval(app):
    controller, clock = app
    run_id = begin(controller, interval=60)
    before = controller.recorded_samples_after(0)
    clock.advance(0.5)
    controller.tick()
    controller.stop_run()
    controller.tick()
    after = controller.recorded_samples_after(0)
    assert len(after) == len(before) + 1
    assert controller.run_id is None
    assert after[-1]["run_id"] == run_id
    assert after[-1]["elapsed_s"] == pytest.approx(0.5)
    assert after[-1]["state"] == "idle"
    saved_run, timestamp, payload = rows(controller)[-1]
    assert after[-1] == {"_sample_sequence": after[-1]["_sample_sequence"],
                         "run_id": saved_run, "time_utc": timestamp, **json.loads(payload)}


def test_natural_completion_and_new_run_keep_global_sequence(app):
    controller, clock = app
    first_run = begin(controller, duration=1, interval=30)
    clock.advance(0.5)
    controller.tick()
    clock.advance(0.51)
    controller.tick()
    assert controller.run_id is None
    first = controller.recorded_samples_after(0)
    assert len(first) == 2
    assert controller.list_runs()[0]["status"] == "completed"
    second_run = begin(controller, interval=30)
    assert second_run != first_run
    new = controller.recorded_samples_after(first[-1]["_sample_sequence"])
    assert len(new) == 1
    assert new[0]["run_id"] == second_run
    assert new[0]["_sample_sequence"] == first[-1]["_sample_sequence"] + 1
    assert controller.recorded_samples_after(0)[:len(first)] == first


def test_recorded_events_are_deeply_detached_and_need_no_database_query(app):
    controller, _ = app
    begin(controller)
    original = controller.recorded_samples_after(0)[0]
    result = controller.recorded_samples_after(0)
    result[0]["valves"][0] = not original["valves"][0]
    result[0]["mass_g"] = -999
    result.clear()
    # A SELECT forbidden here would fail an implementation that polls SQLite.
    controller.store.connection.set_authorizer(
        lambda action, *_: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_SELECT else sqlite3.SQLITE_OK)
    try:
        assert controller.recorded_samples_after(0) == [original]
    finally:
        controller.store.connection.set_authorizer(None)


def test_record_buffer_is_bounded_but_database_retains_every_sample(app):
    controller, _ = app
    begin(controller)
    for index in range(1104):
        controller.snapshot["elapsed_s"] = index + 1
        controller._record_sample()
    events = controller.recorded_samples_after(0)
    assert len(events) == 1000
    assert events[0]["_sample_sequence"] == 106
    assert events[-1]["_sample_sequence"] == 1105
    assert len(rows(controller)) == 1105
    assert controller.recorded_samples_after(1104) == events[-1:]


def test_failed_database_insert_cannot_emit_a_sample_or_consume_sequence(app):
    controller, _ = app
    begin(controller)
    before = controller.recorded_samples_after(0)
    controller.store.connection.execute("""
      CREATE TRIGGER refuse_sample BEFORE INSERT ON samples
      BEGIN SELECT RAISE(FAIL, 'Test recording failure'); END;
    """)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="Test recording failure"):
            controller._record_sample()
        assert controller.recorded_samples_after(0) == before
        assert len(rows(controller)) == len(before)
    finally:
        controller.store.connection.execute("DROP TRIGGER refuse_sample")
    controller._record_sample()
    newest = controller.recorded_samples_after(before[-1]["_sample_sequence"])
    assert len(newest) == 1
    assert newest[0]["_sample_sequence"] == before[-1]["_sample_sequence"] + 1


def test_failed_interval_write_stops_controller_without_showing_unsaved_row(app):
    controller, clock = app
    begin(controller, interval=1)
    before = controller.recorded_samples_after(0)
    controller.store.connection.execute("""
      CREATE TRIGGER refuse_sample BEFORE INSERT ON samples
      BEGIN SELECT RAISE(FAIL, 'Test disk unavailable'); END;
    """)
    try:
        clock.advance(1.1)
        controller.tick()
        assert controller.driver is None
        assert controller.snapshot["state"] == "fault"
        assert "Test disk unavailable" in controller.local_fault
        assert controller.recorded_samples_after(0) == before
        assert len(rows(controller)) == len(before)
    finally:
        controller.store.connection.execute("DROP TRIGGER refuse_sample")


def test_step_name_exports_and_old_records_remain_compatible(tmp_path):
    store = RunStore(tmp_path)
    try:
        run_id = store.start(Recipe(), {}, {})
        store.sample(run_id, {"step_name": "Backwash", "mass_g": None, "valves": [False] * 7})
        with store.connection:
            store.connection.execute(
                "INSERT INTO samples(run_id,time_utc,payload_json) VALUES(?,?,?)",
                (run_id, "2026-10-26T10:00:00Z", json.dumps({"mass_g": 5})))
        output = tmp_path / "readings.csv"
        store.export(output, run_id)
        with output.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            assert reader.fieldnames[-1] == "step_name"  # Existing column order is preserved.
            exported = list(reader)
        assert exported[0]["step_name"] == "Backwash"
        assert exported[0]["mass_g"] == ""
        assert exported[1]["step_name"] == ""
        assert exported[1]["mass_g"] == "5"
    finally:
        store.close()
