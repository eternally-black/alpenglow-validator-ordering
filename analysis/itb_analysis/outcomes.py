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
MAINNET_GENESIS_HASH = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"


def _alpenglow_floor(start: dict) -> int:
    """First post-Alpenglow slot of the run's cluster: the first Alpenglow block on mainnet-beta (and for runs that
    recorded no genesis, e.g. simulations), the recorded gate activation slot on any other cluster (localnet tests)."""
    if start.get("genesis_hash") in (None, MAINNET_GENESIS_HASH):
        return FIRST_ALPENGLOW_SLOT
    return int((start.get("alpenglow") or {}).get("activated_at_slot", FIRST_ALPENGLOW_SLOT))

#: (pair_kind) -> (x label, y label), PLAN §2.3
CONTRASTS: dict[str, tuple[str, str]] = {
    "c1": ("A", "B"),
    "c2": ("A'", "B"),
    "c3": ("A", "A'"),
    "c2_uncontended": ("A'", "B"),
    "race": ("hi", "lo"),
    "equal_key": ("A", "A#2"),
    # Study 3: cost alone and reward ÷ cost disagree on C4; cost alone ties on C5
    "c4": ("Y", "A"),
    "c5": ("hi", "A"),
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


ATTRIBUTION = ("client_id", "tpu_quic", "ingress")


def _known(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v)) and v != ""


def _gossip_mode(states: pd.DataFrame, identity: str, t_ns, used: dict | None = None, horizon_ns: float = 90e9) -> str:
    """stable / transition_ambiguous / unknown (PREREGISTRATION §2(b)).

    Requires one snapshot at or before `t_ns` and one after it, both within the horizon, each with a complete
    attribution (clientId, tpuQuic, ingress kind), agreeing with each other *and* with the complete attribution of the
    endpoint the window actually used. Missing or incomplete evidence is "unknown", never "stable"; an actual change
    (including a validator that leaves gossip) is "transition_ambiguous".
    """
    if states.empty or t_ns is None or (isinstance(t_ns, float) and math.isnan(t_ns)):
        return "unknown"
    if used is None or not all(_known(used.get(k)) for k in ATTRIBUTION):
        return "unknown"
    s = states[states["identity"] == identity]
    before = s[(s["at_unix_ns"] <= t_ns) & (s["at_unix_ns"] >= t_ns - horizon_ns)].sort_values("at_unix_ns").tail(1)
    after = s[(s["at_unix_ns"] > t_ns) & (s["at_unix_ns"] <= t_ns + horizon_ns)].sort_values("at_unix_ns").head(1)
    if before.empty or after.empty:
        return "unknown"
    snaps = [r for _, r in pd.concat([before, after]).iterrows()]
    if not all(bool(r["present"]) for r in snaps):
        return "transition_ambiguous"
    if not all(_known(r.get(k)) for r in snaps for k in ATTRIBUTION):
        return "unknown"
    keys = {tuple(str(r[k]) for k in ATTRIBUTION) for r in snaps}
    if len(keys) > 1 or keys != {tuple(str(used[k]) for k in ATTRIBUTION)}:
        return "transition_ambiguous"
    return "stable"


def _template_key(t) -> tuple | None:
    if not isinstance(t, dict):
        return None
    return (int(t["cu_limit"]), int(t["cu_price_micro_lamports"]), int(t["loaded_data_limit"]))


def _plan_members(plan: dict) -> set[tuple]:
    return {(q["pair_id"], q["kind"], m["label"], _template_key(m["template"]), pos, int(m["lock_index"]))
            for q in plan["pairs"] for pos, m in enumerate(q["members"])}


def _realised_members(g: pd.DataFrame) -> list[tuple]:
    return [(r["pair_id"], r["pair_kind"], r["label"], _template_key(r["template"]), int(r["send_position_in_pair"]),
             int(r["lock_index"])) for _, r in g.iterrows()]


def _send_evidence(run: Run) -> pd.DataFrame:
    """Per window: probes whose own send record shows the stream finished without error (`sends_ok`)."""
    s, p = run.sends, run.probes
    cols = ["run_id", "target_identity", "seq", "sends_ok", "send_records"]
    if s.empty or p.empty or "finished_unix_ns" not in s:
        return pd.DataFrame(columns=cols)
    s = s.copy()
    ok = s["finished_unix_ns"].notna()
    if "error" in s:
        ok &= s["error"].isna()
    if "never_opened" in s:
        ok &= ~s["never_opened"].fillna(True).astype(bool)
    s["ok"] = ok
    j = s.merge(p[["run_id", "probe_id", "target_identity", "seq"]], on=["run_id", "probe_id"], how="inner")
    return (j.groupby(["run_id", "target_identity", "seq"])
             .agg(sends_ok=("ok", "sum"), send_records=("probe_id", "size")).reset_index())


def window_table(run: Run, designs: dict | None = None) -> pd.DataFrame:
    """One row per attempted window with eligibility flags and the reason for any exclusion (PREREGISTRATION §2).

    With `designs` ({sha256: {(target, stage, seq): plan}}, from `load.load_designs`), every window's realised probes
    must match its frozen plan exactly (pair ids and kinds, labels, templates, send positions, locks), checked against
    the design whose hash the run recorded; without a matching design the window is `design_unavailable`.
    """
    w = run.windows.copy()
    if w.empty:
        return w
    p = run.probes
    keys = ["run_id", "target_identity", "seq"]
    logged = p.groupby(keys).agg(probes_logged=("probe_id", "size"), probe_ids=("probe_id", "nunique")) if len(p) else \
        pd.DataFrame(columns=["probes_logged", "probe_ids"], index=pd.MultiIndex.from_tuples([], names=keys))
    w = w.merge(logged, left_on=keys, right_index=True, how="left")
    w["probes_logged"] = w["probes_logged"].fillna(0).astype(int)
    w["duplicate_records"] = w["probes_logged"] != w["probe_ids"].fillna(0).astype(int)
    w = w.merge(_send_evidence(run), on=keys, how="left")
    col = lambda name, default: w[name] if name in w else pd.Series(default, index=w.index)
    planned = col("planned_probes", np.nan)
    skipped = col("skipped", np.nan)
    not_sent = col("not_sent", np.nan)
    transport = col("transport_errors", 0)
    # Every planned member logged once and its own send record shows a finished stream without error; aggregate
    # counters must agree; missing fields mean "not established".
    w["all_sent"] = (
        skipped.isna()
        & planned.notna()
        & w["probes_logged"].eq(planned)
        & w["sends_ok"].fillna(-1).eq(planned)
        & w["send_records"].fillna(-1).eq(planned)
        & not_sent.fillna(-1).eq(0)
        & transport.fillna(-1).eq(0)
    )
    design_of = {s.get("run_id"): s.get("design_sha256") for s in run.starts}
    probes_of = dict(tuple(p.groupby(keys))) if designs is not None and len(p) else {}
    design_ok = []
    for _, r in w.iterrows():
        if designs is None:
            design_ok.append("")
            continue
        plans = designs.get(design_of.get(r["run_id"]))
        plan = plans.get((r["target_identity"], int(r["stage"]), int(r["seq"]))) if plans else None
        if plan is None:
            design_ok.append("design_unavailable")
            continue
        g = probes_of.get((r["run_id"], r["target_identity"], r["seq"]), p.iloc[0:0])
        real = _realised_members(g)
        same = len(real) == len(set(real)) and set(real) == _plan_members(plan) and planned_ok(r, plan)
        design_ok.append("" if same else "design_mismatch")
    w["design_check"] = design_ok
    t_col = "estimated_window_start_unix_ns"
    states_of = dict(tuple(run.states.groupby("identity"))) if len(run.states) else {}
    modes = []
    for _, r in w.iterrows():
        used = {k: r.get(k) for k in ("client_id", "tpu_quic", "ingress")}
        st = states_of.get(r["target_identity"], run.states.iloc[0:0])
        modes.append(_gossip_mode(st, r["target_identity"], r[t_col] if t_col in w and pd.notna(r.get(t_col)) else None, used))
    w["mode"] = modes

    def produced(v):
        if isinstance(v, list):
            return len(v) > 0
        return None  # missing or errored lookup: unknown

    w["target_produced"] = col("produced_slots", None).apply(produced)
    floor = {s.get("run_id"): _alpenglow_floor(s) for s in run.starts}
    w["post_alpenglow"] = [int(f) >= floor.get(r, FIRST_ALPENGLOW_SLOT) for f, r in zip(w["window_first_slot"], w["run_id"])]
    reasons = []
    for _, r in w.iterrows():
        why = []
        if pd.notna(r.get("skipped")):
            # Never attempted (no probes): its only reason is the skip itself, not the checks that follow from it.
            reasons.append(f"skipped:{r.get('skipped')}")
            continue
        if r["duplicate_records"]:
            why.append("duplicate_records")
        if r["design_check"]:
            why.append(r["design_check"])
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
    # The stopping predicate `itb run` uses (PREREGISTRATION §5): everything but gossip stability, which is known only
    # after the next snapshot.
    w["stop_ok"] = (~w["duplicate_records"]) & w["design_check"].eq("") & w["all_sent"] & w["target_produced"].eq(True)
    return w


def planned_ok(r, plan: dict) -> bool:
    """The window's recorded plan size equals the frozen plan's member count."""
    n = sum(len(q["members"]) for q in plan["pairs"])
    return pd.notna(r.get("planned_probes")) and int(r["planned_probes"]) == n


def _rank_key(row) -> tuple:
    if row["landed"]:
        return (0, int(row["slot"]), int(row["index_in_block"]))
    return (1, 0, 0)


def pair_table(run: Run, kinds: tuple[str, ...] = ("c1", "c2", "c3", "c2_uncontended"),
               designs: dict | None = None, windows: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per (window, pair) for the given pair kinds, with y_w / z_w and the landing funnel. `windows` reuses an
    already computed `window_table(run, designs)`."""
    p = probe_table(run)
    if p.empty:
        return pd.DataFrame()
    w = (window_table(run, designs) if windows is None else windows).set_index(["run_id", "target_identity", "seq"])
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
                # counts towards the stopping rule exactly as in `itb run`
                "stop_informative": False if wrow is None else bool(wrow.get("stop_ok")) and both,
            }
        )
    return pd.DataFrame(rows)


def funnel(run: Run, designs: dict | None = None, windows: pd.DataFrame | None = None,
           pairs: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per target: planned → sent → any landing → status breakdown (probe level) and window eligibility."""
    p = probe_table(run)
    w = window_table(run, designs) if windows is None else windows
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
    pairs = pair_table(run, designs=designs, windows=w) if pairs is None else pairs
    stages = (
        pairs[pairs["pair_kind"].isin(["c1", "c2", "c3"])]
        .groupby("target_identity")
        .agg(pairs_main=("pair_id", "size"), pairs_both_landed=("both_landed", "sum"), pairs_same_slot=("same_slot", "sum"),
             pairs_evaluable_both=("x_first_cc", lambda s: int(s.notna().sum())))
        if len(pairs)
        else pd.DataFrame(index=win.index)
    )
    return win.join(by_reason).join(probes).join(stages).join(status).fillna(0).reset_index()
