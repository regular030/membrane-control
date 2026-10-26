"""Local transactional run records; no server or database installation required."""
from __future__ import annotations
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class RunStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.directory / "runs.sqlite3")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
          CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY, started_utc TEXT NOT NULL, ended_utc TEXT,
            name TEXT NOT NULL, status TEXT NOT NULL, recipe_json TEXT NOT NULL,
            settings_json TEXT NOT NULL, device_json TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id),
            time_utc TEXT NOT NULL, payload_json TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS samples_run ON samples(run_id);
          CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, run_id INTEGER, time_utc TEXT NOT NULL, message TEXT NOT NULL);
        """)
        # A previous process terminated without a controlled end. Never resume it.
        self.connection.execute("UPDATE runs SET status='interrupted', ended_utc=? WHERE ended_utc IS NULL", (utc_now(),))
        self.connection.commit()

    def start(self, recipe, settings, device):
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO runs(started_utc,name,status,recipe_json,settings_json,device_json) VALUES(?,?,?,?,?,?)",
                (utc_now(), recipe.name, "running", json.dumps(recipe.to_dict(), allow_nan=False),
                 json.dumps(settings, allow_nan=False), json.dumps(device, allow_nan=False)))
        return cursor.lastrowid

    def sample(self, run_id, snapshot):
        fields = {k: snapshot.get(k) for k in (
            "elapsed_s", "simulation", "state", "step_index", "cycle", "pressure_psi",
            "flow_ml_min", "desired_flow_ml_min", "balance_flow_ml_min", "flux_lmh", "mass_g", "pump_percent", "pump_feedback_v",
            "valves", "fault", "controller_status", "balance_status", "step_name")}
        payload = json.dumps(fields, allow_nan=False)
        timestamp = utc_now()
        with self.connection:
            self.connection.execute("INSERT INTO samples(run_id,time_utc,payload_json) VALUES(?,?,?)",
                                    (run_id, timestamp, payload))
        # Return only committed data, detached from the caller's mutable snapshot.
        return {"run_id": run_id, "time_utc": timestamp, **json.loads(payload)}

    def finish(self, run_id, status):
        with self.connection:
            self.connection.execute("UPDATE runs SET status=?,ended_utc=? WHERE id=? AND ended_utc IS NULL", (status, utc_now(), run_id))

    def event(self, message, run_id=None):
        with self.connection:
            self.connection.execute("INSERT INTO events(run_id,time_utc,message) VALUES(?,?,?)", (run_id, utc_now(), message))

    def list_runs(self):
        self.connection.row_factory = sqlite3.Row
        result = [dict(row) for row in self.connection.execute(
            "SELECT id,started_utc,ended_utc,name,status FROM runs ORDER BY id DESC LIMIT 200")]
        self.connection.row_factory = None
        return result

    def export(self, path, run_id=None):
        if run_id is None:
            row = self.connection.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                raise ValueError("No recorded runs to export")
            run_id = row[0]
        row = self.connection.execute("SELECT recipe_json,settings_json,device_json FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError("Run not found")
        path = Path(path)
        fields = ["time_utc", "elapsed_s", "simulation", "state", "step_index", "cycle", "pressure_psi",
                  "flow_ml_min", "desired_flow_ml_min", "balance_flow_ml_min", "flux_lmh", "mass_g", "pump_percent", "pump_feedback_v", "valves", "fault",
                  "controller_status", "balance_status", "step_name"]
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for timestamp, payload in self.connection.execute("SELECT time_utc,payload_json FROM samples WHERE run_id=? ORDER BY id", (run_id,)):
                data = json.loads(payload)
                data["time_utc"] = timestamp
                data["valves"] = "".join("1" if v else "0" for v in data.get("valves", []))
                writer.writerow(data)
        path.with_suffix(".metadata.json").write_text(json.dumps({"run_id": run_id, "recipe": json.loads(row[0]),
            "settings": json.loads(row[1]), "device": json.loads(row[2])}, indent=2), encoding="utf-8")

    def close(self):
        self.connection.close()
