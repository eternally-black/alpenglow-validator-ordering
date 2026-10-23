"""From raw probe records to the per-window, per-pair observations the pre-registration analyses (docs/PREREGISTRATION.md §1–2).

For every pair of a window:
- `x` / `y` = the contrast's first / second label in the contrast table (C1: A vs B, C2: A' vs B, C3: A vs A');
- `x_first` (y_w) = 1 if x lands before y, ordering by (slot, index) over the whole window, with members that did not
  land in the targeted window placed after every member that did; NaN if neither landed;
- `first_sent_first` (z_w) = the same observation recoded by send order.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .load import Run

FIRST_ALPENGLOW_SLOT = 459_653_008

#: (pair_kind) -> (x label, y label), PLAN §2.3
CONTRASTS: dict[str, tuple[str, str]] = {
    "c1": ("A", "B"),
    "c2": ("A'", "B"),
    "c3": ("A", "A'"),
    "c2_uncontended": ("A'", "B"),
    "race": ("hi", "lo"),
    "equal_key": ("A", "A#2"),
}

LANDED = "landed_target"


def probe_table(run: Run) -> pd.DataFrame:
    """Probes joined with their outcome (one row per probe)."""
    p = run.probes.copy()
    if p.empty:
        return p
    o = run.outcomes
    keep = ["probe_id", "run_id", "status", "slot", "index_in_block", "block_tx_count", "leader", "fee", "err", "cost_units", "transport_error"]
    if not o.empty:
        o = o[[c for c in keep if c in o.columns]]
        p = p.merge(o, on=["run_id", "probe_id"], how="left")
    else:
        for c in keep[2:]:
            p[c] = np.nan
    p["status"] = p["status"].fillna("unresolved")
    p["landed"] = p["status"].eq(LANDED)
    return p


def _gossip_mode(states: pd.DataFrame, identity: str, t_ns: float, horizon_ns: float = 90e9) -> str:
    """stable / transition_ambiguous / unknown from the snapshots nearest before and after `t_ns`."""
    if states.empty or t_ns is None or (isinstance(t_ns, float) and math.isnan(t_ns)):
        return "unknown"
    s = states[states["identity"] == identity]
    before = s[(s["at_unix_ns"] <= t_ns) & (s["at_unix_ns"] >= t_ns - horizon_ns)].sort_values("at_unix_ns").tail(1)
    after = s[(s["at_unix_ns"] > t_ns) & (s["at_unix_ns"] <= t_ns + horizon_ns)].sort_values("at_unix_ns").head(1)
    snaps = pd.concat([before, after])
    if snaps.empty:
        return "unknown"
    if not snaps["present"].all():
        return "transition_ambiguous"
    key = snaps[["client_id", "tpu_quic", "ingress"]].astype(str).agg("|".join, axis=1)
    if key.nunique() > 1:
        return "transition_ambiguous"
    # Only a snapshot on one side (run start/end): accept as stable but say so.
    return "stable" if len(snaps) == 2 else "stable_one_sided"


def window_table(run: Run) -> pd.DataFrame:
    """One row per attempted window with eligibility flags (PREREGISTRATION §2)."""
    w = run.windows.copy()
    if w.empty:
        return w
    p = probe_table(run)
    planned = p.groupby(["run_id", "target_identity", "seq"]).size().rename("planned")
    w = w.merge(planned, left_on=["run_id", "target_identity", "seq"], right_index=True, how="left")
    sent_ok = w["sent_ok"] if "sent_ok" in w else pd.Series(np.nan, index=w.index)
    not_sent = w["not_sent"] if "not_sent" in w else pd.Series(0, index=w.index)
    skipped = w["skipped"] if "skipped" in w else pd.Series(np.nan, index=w.index)
    w["all_sent"] = skipped.isna() & sent_ok.fillna(-1).eq(w["planned"]) & not_sent.fillna(0).eq(0)
    t_col = "estimated_window_start_unix_ns"
    w["mode"] = [
        _gossip_mode(run.states, r["target_identity"], r[t_col] if t_col in w and pd.notna(r.get(t_col)) else None)
        for _, r in w.iterrows()
    ]
    if run.states.empty:
        w["mode"] = "stable_one_sided"
    if "produced_slots" in w:
        w["target_produced"] = w["produced_slots"].apply(lambda v: bool(v) if isinstance(v, list) else True)
    else:
        w["target_produced"] = True
    w["post_alpenglow"] = w["window_first_slot"] >= FIRST_ALPENGLOW_SLOT
    w["evaluable"] = w["all_sent"] & w["mode"].isin(["stable", "stable_one_sided"]) & w["target_produced"] & w["post_alpenglow"]
    return w


def _rank_key(row) -> tuple:
    if row["landed"]:
        return (0, int(row["slot"]), int(row["index_in_block"]))
    return (1, 0, 0)


def pair_table(run: Run, kinds: tuple[str, ...] = ("c1", "c2", "c3", "c2_uncontended")) -> pd.DataFrame:
    """One row per (window, pair) for the given pair kinds, with y_w / z_w and the landing funnel."""
    p = probe_table(run)
    if p.empty:
        return pd.DataFrame()
    w = window_table(run).set_index(["run_id", "target_identity", "seq"])
    rows = []
    for (run_id, pair_id), g in p[p["pair_kind"].isin(kinds)].groupby(["run_id", "pair_id"]):
        kind = g["pair_kind"].iloc[0]
        x_label, y_label = CONTRASTS[kind]
        gx, gy = g[g["label"] == x_label], g[g["label"] == y_label]
        if len(gx) != 1 or len(gy) != 1:
            continue
        rx, ry = gx.iloc[0], gy.iloc[0]
        x_sent_first = int(rx["send_position_in_pair"]) == 0
        landed_x, landed_y = bool(rx["landed"]), bool(ry["landed"])
        if not landed_x and not landed_y:
            x_first = np.nan
        else:
            x_first = float(_rank_key(rx) < _rank_key(ry))
        first_sent_first = np.nan if np.isnan(x_first) else float(x_first == float(x_sent_first))
        key = (run_id, rx["target_identity"], int(rx["seq"]))
        wrow = w.loc[key] if key in w.index else None
        rows.append(
            {
                "run_id": run_id,
                "target_identity": rx["target_identity"],
                "seq": int(rx["seq"]),
                "kit": rx["kit"],
                "regime": rx["regime"],
                "pair_id": pair_id,
                "pair_kind": kind,
                "x_label": x_label,
                "y_label": y_label,
                "x_sent_first": x_sent_first,
                "landed_x": landed_x,
                "landed_y": landed_y,
                "both_landed": landed_x and landed_y,
                "same_slot": landed_x and landed_y and rx["slot"] == ry["slot"],
                "x_first": x_first,
                "first_sent_first": first_sent_first,
                "race_dt_ms": rx.get("race_dt_ms"),
                "client_id": None if wrow is None else wrow.get("client_id"),
                "ingress": None if wrow is None else wrow.get("ingress"),
                "mode": None if wrow is None else wrow.get("mode"),
                "evaluable": False if wrow is None else bool(wrow.get("evaluable")),
            }
        )
    return pd.DataFrame(rows)


def funnel(run: Run) -> pd.DataFrame:
    """Per target: planned → sent → any landing → status breakdown (probe level) and window eligibility."""
    p = probe_table(run)
    w = window_table(run)
    if p.empty:
        return pd.DataFrame()
    status = p.pivot_table(index="target_identity", columns="status", values="probe_id", aggfunc="count", fill_value=0)
    win = w.groupby("target_identity").agg(
        windows_attempted=("seq", "size"),
        windows_all_sent=("all_sent", "sum"),
        windows_evaluable=("evaluable", "sum"),
    )
    probes = p.groupby("target_identity").agg(probes_planned=("probe_id", "size"), probes_landed=("landed", "sum"))
    return win.join(probes).join(status).reset_index()
