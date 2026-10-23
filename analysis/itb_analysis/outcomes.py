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


def _gossip_mode(states: pd.DataFrame, identity: str, t_ns, used: dict | None = None, horizon_ns: float = 90e9) -> str:
    """stable / transition_ambiguous / unknown (PREREGISTRATION §2(b)).

    Requires one snapshot at or before `t_ns` and one after it, both within the horizon, agreeing with each other on
    clientId, tpuQuic and ingress kind, and agreeing with the endpoint the window actually used (`used`). Missing
    evidence is "unknown", never "stable".
    """
    if states.empty or t_ns is None or (isinstance(t_ns, float) and math.isnan(t_ns)):
        return "unknown"
    s = states[states["identity"] == identity]
    before = s[(s["at_unix_ns"] <= t_ns) & (s["at_unix_ns"] >= t_ns - horizon_ns)].sort_values("at_unix_ns").tail(1)
    after = s[(s["at_unix_ns"] > t_ns) & (s["at_unix_ns"] <= t_ns + horizon_ns)].sort_values("at_unix_ns").head(1)
    if before.empty or after.empty:
        return "unknown"
    snaps = pd.concat([before, after])
    if not snaps["present"].all():
        return "transition_ambiguous"
    key = snaps[["client_id", "tpu_quic", "ingress"]].astype(str).agg("|".join, axis=1)
    if key.nunique() > 1:
        return "transition_ambiguous"
    if used is not None and all(used.get(k) is not None for k in ("client_id", "tpu_quic", "ingress")):
        if "|".join(str(used[k]) for k in ("client_id", "tpu_quic", "ingress")) != key.iloc[0]:
            return "transition_ambiguous"
    return "stable"


def window_table(run: Run) -> pd.DataFrame:
    """One row per attempted window with eligibility flags and the reason for any exclusion (PREREGISTRATION §2)."""
    w = run.windows.copy()
    if w.empty:
        return w
    p = run.probes
    logged = p.groupby(["run_id", "target_identity", "seq"]).size().rename("probes_logged") if len(p) else pd.Series(dtype=int, name="probes_logged")
    w = w.merge(logged, left_on=["run_id", "target_identity", "seq"], right_index=True, how="left")
    w["probes_logged"] = w["probes_logged"].fillna(0).astype(int)
    col = lambda name, default: w[name] if name in w else pd.Series(default, index=w.index)
    planned = col("planned_probes", np.nan)
    skipped = col("skipped", np.nan)
    sent_ok = col("sent_ok", np.nan)
    not_sent = col("not_sent", np.nan)
    transport = col("transport_errors", 0)
    # Every planned member logged and written without error; missing fields mean "not established".
    w["all_sent"] = (
        skipped.isna()
        & planned.notna()
        & w["probes_logged"].eq(planned)
        & sent_ok.eq(planned)
        & not_sent.fillna(-1).eq(0)
        & transport.fillna(-1).eq(0)
    )
    t_col = "estimated_window_start_unix_ns"
    modes = []
    for _, r in w.iterrows():
        used = {k: r.get(k) for k in ("client_id", "tpu_quic", "ingress")}
        modes.append(_gossip_mode(run.states, r["target_identity"], r[t_col] if t_col in w and pd.notna(r.get(t_col)) else None, used))
    w["mode"] = modes

    def produced(v):
        if isinstance(v, list):
            return len(v) > 0
        return None  # missing or errored lookup: unknown

    w["target_produced"] = col("produced_slots", None).apply(produced)
    w["post_alpenglow"] = w["window_first_slot"] >= FIRST_ALPENGLOW_SLOT
    reasons = []
    for _, r in w.iterrows():
        why = []
        if not r["all_sent"]:
            why.append("not_all_sent" if pd.isna(r.get("skipped")) else f"skipped:{r.get('skipped')}")
        if r["mode"] != "stable":
            why.append(f"mode:{r['mode']}")
        if r["target_produced"] is not True:
            why.append("production_unknown" if r["target_produced"] is None else "target_produced_no_block")
        if not r["post_alpenglow"]:
            why.append("pre_alpenglow")
        reasons.append(",".join(why))
    w["exclusion"] = reasons
    w["evaluable"] = w["exclusion"].eq("")
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
        both = landed_x and landed_y
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
                # primary (complete-case): both members landed in the targeted window
                "x_first_cc": x_first if both else np.nan,
                "first_sent_first_cc": first_sent_first if both else np.nan,
                # sensitivity: a member that did not land counts as after every member that did
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
    status.columns = [f"probes_{c}" for c in status.columns]
    win = w.groupby("target_identity").agg(
        windows_attempted=("seq", "size"),
        windows_all_sent=("all_sent", "sum"),
        windows_evaluable=("evaluable", "sum"),
    )
    # Every exclusion reason counted separately (a window can have several).
    reasons = w.assign(reason=w["exclusion"].str.split(",")).explode("reason")
    reasons = reasons[reasons["reason"].fillna("") != ""]
    by_reason = (
        reasons.assign(reason=reasons["reason"].str.split(":").str[0])
        .pivot_table(index="target_identity", columns="reason", values="seq", aggfunc="count", fill_value=0)
        if len(reasons)
        else pd.DataFrame(index=win.index)
    )
    by_reason.columns = [f"excluded_{c}" for c in by_reason.columns]
    probes = p.groupby("target_identity").agg(probes_planned=("probe_id", "size"), probes_landed=("landed", "sum"))
    pairs = pair_table(run)
    stages = (
        pairs[pairs["pair_kind"].isin(["c1", "c2", "c3"])]
        .groupby("target_identity")
        .agg(pairs_main=("pair_id", "size"), pairs_both_landed=("both_landed", "sum"), pairs_same_slot=("same_slot", "sum"),
             pairs_evaluable_both=("x_first_cc", lambda s: int(s.notna().sum())))
        if len(pairs)
        else pd.DataFrame(index=win.index)
    )
    return win.join(by_reason).join(probes).join(stages).join(status).fillna(0).reset_index()
