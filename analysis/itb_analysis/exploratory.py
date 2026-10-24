"""Stage-2 exploratory aggregates (PREREGISTRATION §7 — exploratory, labelled as such everywhere).

One function per kit, each a plain count table keyed by (client, ingress, …). `scripts/exploratory_stage2.py` prints
them as markdown and `figures.py` draws them, so the published tables and figures cannot disagree.

Only evaluable windows (same eligibility rules as Stage 1) enter the race and equal-key counts; the hold-cliff and
spill-over kits are counted per probe status.
- **Races** (T kit): `hi` (3,000,000 µlamports/CU) vs `lo` (1,000,000 µlamports/CU with a 64 MiB data request), one
  sent Δt ms after the other. P(hi lands first) separately when `hi` was sent first and when `lo` had the head start
  of Δt ms: how long a head start the higher-priority probe can overcome — the effective reordering horizon.
- **Equal key**: two identical template-A probes, Δt apart. P(first-sent lands first): FIFO predicts ≈ 1; the
  Firedancer later-arrival-first tie-break predicts < 0.5.
- **Hold cliff** (H kit): status of probes sent 7 s, 3 s and 0.5 s before the window, per client.
- **Spill-over** (S kit): where pre-window probes land, per ingress kind.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import outcomes
from .load import load_designs, load_runs, run_dirs


@dataclass
class Stage2:
    run_ids: list[str]
    windows: pd.DataFrame
    probes: pd.DataFrame  # with evaluable / client / ingress of the probe's window


def load_stage2(raw: Path, design: Path) -> Stage2:
    def start(d: Path) -> dict:
        return json.loads((d / "run_start.json").read_text())

    dirs = [d for d in run_dirs(raw) if start(d).get("stage") == 2 and start(d).get("mode") == "live"]
    run = load_runs(dirs)
    w = outcomes.window_table(run, load_designs([design]))
    p = outcomes.probe_table(run)
    ev = set(zip(w[w["evaluable"]]["run_id"], w[w["evaluable"]]["target_identity"], w[w["evaluable"]]["seq"]))
    group = {(r["run_id"], r["target_identity"], r["seq"]): (r.get("client_id"), r.get("ingress")) for _, r in w.iterrows()}
    keys = list(zip(p["run_id"], p["target_identity"], p["seq"]))
    p["evaluable"] = [k in ev for k in keys]
    p["client"] = [group.get(k, (None, None))[0] for k in keys]
    p["ingress"] = [group.get(k, (None, None))[1] for k in keys]
    return Stage2([d.name for d in dirs], w, p)


def _rank(r) -> tuple[int, int]:
    return (int(r["slot"]), int(r["index_in_block"]))


def races(p: pd.DataFrame) -> dict[tuple, list[int]]:
    """(client, ingress, Δt ms) -> [hi first & hi sent first, hi sent first, hi first & lo sent first, lo sent first],
    over race pairs in evaluable windows where both members landed."""
    out: dict[tuple, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for _, g in p[(p["pair_kind"] == "race") & p["evaluable"]].groupby(["run_id", "pair_id"]):
        if len(g) != 2 or not g["landed"].all():
            continue
        hi, lo = g[g["label"] == "hi"].iloc[0], g[g["label"] == "lo"].iloc[0]
        key = (hi["client"], hi["ingress"], float(hi["race_dt_ms"]))
        hi_first = _rank(hi) < _rank(lo)
        i = 0 if int(hi["send_position_in_pair"]) == 0 else 2
        out[key][i] += hi_first
        out[key][i + 1] += 1
    return dict(out)


def equal_key(p: pd.DataFrame) -> dict[tuple, list[int]]:
    """(client, ingress, Δt ms) -> [first-sent landed first, pairs], both members landed, evaluable windows."""
    out: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for _, g in p[(p["pair_kind"] == "equal_key") & p["evaluable"]].groupby(["run_id", "pair_id"]):
        if len(g) != 2 or not g["landed"].all():
            continue
        first = g[g["send_position_in_pair"] == 0].iloc[0]
        second = g[g["send_position_in_pair"] == 1].iloc[0]
        key = (first["client"], first["ingress"], float(first["race_dt_ms"]))
        out[key][0] += _rank(first) < _rank(second)
        out[key][1] += 1
    return dict(out)


def hold(p: pd.DataFrame) -> dict[tuple, dict[str, int]]:
    """(client, ingress, offset s) -> probe status -> count, H kit."""
    out: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for _, r in p[p["kit"] == "h"].iterrows():
        out[(r["client"], r["ingress"], round(r["nominal_offset_ms"] / 1000, 1))][r["status"]] += 1
    return dict(out)


def spill(p: pd.DataFrame) -> dict[tuple, dict[str, int]]:
    """(ingress, offset ms) -> probe status -> count, S kit."""
    out: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for _, r in p[p["kit"] == "s"].iterrows():
        out[(r["ingress"], round(r["nominal_offset_ms"]))][r["status"]] += 1
    return dict(out)
