"""Readers for the raw run directories described in docs/DATA.md."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import zstandard


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def read_zst_json(path: Path):
    with path.open("rb") as f, zstandard.ZstdDecompressor().stream_reader(f) as r:
        return json.load(io.TextIOWrapper(r, encoding="utf-8"))


@dataclass
class Run:
    """One or more run directories, concatenated. Every frame carries `run_id`."""

    paths: list[Path]
    starts: list[dict]
    probes: pd.DataFrame
    windows: pd.DataFrame
    outcomes: pd.DataFrame
    states: pd.DataFrame
    sends: pd.DataFrame
    ends: list[dict] = field(default_factory=list)
    #: observed slot events (run_id, slot, kind, recv_unix_ns) from slot_events.json.zst
    slot_events: pd.DataFrame = field(default_factory=pd.DataFrame)


def _flatten_outcomes(rows: list[dict]) -> pd.DataFrame:
    """One row per (run_id, probe_id): the *last* record wins, so an outcome restored by `itb reconcile` supersedes
    the unresolved one written at collection time. `outcome_records` keeps the number of records seen."""
    flat = []
    for r in rows:
        o = dict(r.get("outcome", r))
        o["run_id"] = r.get("run_id", o.get("run_id"))
        flat.append(o)
    df = pd.DataFrame(flat)
    if df.empty or "probe_id" not in df:
        return df
    counts = df.groupby(["run_id", "probe_id"], dropna=False).size().rename("outcome_records")
    df = df.drop_duplicates(subset=["run_id", "probe_id"], keep="last")
    return df.merge(counts, left_on=["run_id", "probe_id"], right_index=True, how="left")


def _flatten_sends(rows: list[dict]) -> pd.DataFrame:
    flat = []
    for r in rows:
        if "record" in r:
            d = dict(r["record"])
            d["dry_run"] = False
        else:
            d = {k: v for k, v in r.items()}
        d["run_id"] = r.get("run_id")
        flat.append(d)
    return pd.DataFrame(flat)


def _flatten_states(rows: list[dict], run_id: str) -> pd.DataFrame:
    flat = []
    for r in rows:
        s = r.get("state") or {}
        flat.append(
            {
                "run_id": run_id,
                "at_unix_ns": r["at_unix_ns"],
                "identity": r["identity"],
                "present": bool(s),
                "client_id": s.get("client_id"),
                "version": s.get("version"),
                "tpu_quic": s.get("tpu_quic"),
                "ingress": s.get("ingress"),
            }
        )
    return pd.DataFrame(flat)


def load_run(path: Path) -> Run:
    path = Path(path)
    start = read_json(path / "run_start.json") if (path / "run_start.json").exists() else {}
    run_id = start.get("run_id", path.name)
    probes = pd.DataFrame(read_jsonl(path / "probes.jsonl"))
    windows = pd.DataFrame(read_jsonl(path / "windows.jsonl"))
    outcomes = _flatten_outcomes(read_jsonl(path / "outcomes.jsonl"))
    sends = _flatten_sends(read_jsonl(path / "sends.jsonl"))
    states = _flatten_states(read_jsonl(path / "target_states.jsonl"), run_id)
    for df in (probes, windows, outcomes, sends):
        if len(df) and "run_id" not in df:
            df["run_id"] = run_id
        elif len(df):
            df["run_id"] = df["run_id"].fillna(run_id)
    end = read_json(path / "run_end.json") if (path / "run_end.json").exists() else {}
    ev_path = path / "slot_events.json.zst"
    events = pd.DataFrame(read_zst_json(ev_path)) if ev_path.exists() else pd.DataFrame()
    if len(events):
        events["run_id"] = run_id
    return Run([path], [start], probes, windows, outcomes, states, sends, [end] if end else [], events)


def load_runs(paths: list[Path]) -> Run:
    runs = [load_run(p) for p in paths]
    if not runs:
        raise ValueError("no run directories given")
    cat = lambda frames: pd.concat([f for f in frames if len(f)], ignore_index=True) if any(len(f) for f in frames) else pd.DataFrame()
    return Run(
        paths=[p for r in runs for p in r.paths],
        starts=[s for r in runs for s in r.starts],
        probes=cat([r.probes for r in runs]),
        windows=cat([r.windows for r in runs]),
        outcomes=cat([r.outcomes for r in runs]),
        states=cat([r.states for r in runs]),
        sends=cat([r.sends for r in runs]),
        ends=[e for r in runs for e in r.ends],
        slot_events=cat([r.slot_events for r in runs]),
    )


def load_designs(paths: list[Path]) -> dict[str, dict[tuple[str, int, int], dict]]:
    """Frozen designs keyed by SHA-256 of the file, each as {(target, stage, seq): plan}."""
    import hashlib

    out = {}
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        raw = p.read_bytes()
        plans = {}
        for line in raw.decode("utf-8").splitlines():
            if line.strip():
                pl = json.loads(line)
                plans[(pl["target_identity"], int(pl["stage"]), int(pl["seq"]))] = pl
        out[hashlib.sha256(raw).hexdigest()] = plans
    return out


def run_dirs(root: Path) -> list[Path]:
    """Every directory under `root` that contains a run_start.json, sorted by name (= by start time)."""
    return sorted(p.parent for p in Path(root).glob("*/run_start.json"))
