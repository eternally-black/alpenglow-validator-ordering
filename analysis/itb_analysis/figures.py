"""Figures for README and REPORT, drawn from the numbers the report publishes.

    python -m itb_analysis.cli figures [--results data/derived/results.json] [--out figures]

- identification: the three label contrasts and the send-order effect per validator group (results.json);
- arrival: per window, when our probes arrived against whether all three contrasts followed reward/cost (raw runs);
- races, hold: the Stage-2 exploratory kits, from the same counts `scripts/exploratory_stage2.py` prints.

Every figure is written twice, `<name>.svg` (light) and `<name>-dark.svg`, for a `<picture>` that follows the reader's
colour scheme. Each one has a table twin in REPORT.md. The output is deterministic: text becomes paths in the DejaVu
Sans bundled with matplotlib, the SVG id salt is fixed and no date is embedded, so the same data and the same pinned
matplotlib give the same bytes.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("svg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
from matplotlib.transforms import blended_transform_factory  # noqa: E402

from . import exploratory, outcomes, report, stats, study2  # noqa: E402
from .load import load_designs, load_runs  # noqa: E402


@dataclass(frozen=True)
class Theme:
    name: str
    surface: str
    ink: str
    ink2: str
    muted: str
    grid: str
    axis: str
    band: str
    series: tuple[str, str, str]


# Reference data-viz palette (validated light and dark: adjacent CVD ΔE ≥ 8.4, normal-vision ΔE ≥ 19.8).
LIGHT = Theme("light", "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#eeede8",
              ("#2a78d6", "#eb6834", "#1baf7a"))
DARK = Theme("dark", "#1a1a19", "#f0efec", "#c3c2b7", "#898781", "#2c2c2a", "#383835", "#2a2a28",
             ("#3987e5", "#d95926", "#199e70"))
THEMES = (LIGHT, DARK)

PX = 0.75  # points per CSS pixel: a 2px line is 1.5 pt
FAMILY = ("Agave", "JitoLabs", "Rakurai", "Firedancer", "AgaveBam", "FireBAM", "HarmonicAgave", "HarmonicFiredancer")
NAMES = {"Agave": "Agave", "JitoLabs": "Jito-Solana", "Rakurai": "Rakurai", "Firedancer": "Firedancer",
         "AgaveBam": "Agave + BAM", "FireBAM": "Firedancer + BAM", "HarmonicAgave": "Agave + Harmonic",
         "HarmonicFiredancer": "Firedancer + Harmonic"}
SOURCE = "github: data/derived · itb-analysis figures"


def _rc(t: Theme) -> dict:
    return {
        "font.family": "DejaVu Sans", "font.size": 9, "svg.fonttype": "path", "svg.hashsalt": "itb",
        "figure.facecolor": t.surface, "axes.facecolor": t.surface, "savefig.facecolor": t.surface,
        "text.color": t.ink, "axes.edgecolor": t.axis, "axes.labelcolor": t.ink2, "axes.linewidth": PX,
        "xtick.color": t.axis, "ytick.color": t.axis, "xtick.labelcolor": t.ink2, "ytick.labelcolor": t.ink2,
        "xtick.major.size": 0, "ytick.major.size": 0, "xtick.major.pad": 4, "ytick.major.pad": 4,
        "xtick.labelsize": 8, "ytick.labelsize": 8, "axes.unicode_minus": True,
    }


class Canvas:
    """A figure laid out in inches from the top-left corner, so text, legend and plot rows line up exactly."""

    def __init__(self, t: Theme, width: float, height: float):
        self.t, self.w, self.h = t, width, height
        self.fig = plt.figure(figsize=(width, height))

    def axes(self, left: float, top: float, width: float, height: float):
        ax = self.fig.add_axes((left / self.w, 1 - (top + height) / self.h, width / self.w, height / self.h))
        for s in ax.spines.values():
            s.set_visible(False)
        return ax

    def text(self, x: float, y: float, s: str, **kw):
        kw.setdefault("va", "top")
        return self.fig.text(x / self.w, 1 - y / self.h, s, **kw)

    def header(self, title: str, subtitle: str, x: float = 0.25) -> None:
        self.text(x, 0.22, title, fontsize=12.5, fontweight="bold", color=self.t.ink)
        self.text(x, 0.52, subtitle, fontsize=8.5, color=self.t.ink2, linespacing=1.45)

    def legend(self, x: float, y: float, handles: list, labels: list[str], ncol: int) -> None:
        self.fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(x / self.w, 1 - y / self.h), ncol=ncol,
                        frameon=False, fontsize=8.5, labelcolor=self.t.ink2, handlelength=1.8, handletextpad=0.6,
                        columnspacing=2.0, borderaxespad=0, borderpad=0)

    def footnote(self, s: str, x: float = 0.25) -> None:
        self.text(x, self.h - 0.12, s, fontsize=7.5, color=self.t.muted, va="bottom", linespacing=1.45)


def _dot(t: Theme, color: str) -> Line2D:
    return Line2D([], [], color=color, lw=2 * PX, marker="o", ms=6.5, mfc=color, mec=t.surface, mew=1.5)


def _interval(ax, lo: float, hi: float, est: float, y: float, color: str, t: Theme) -> None:
    ax.plot([lo, hi], [y, y], color=color, lw=2 * PX, solid_capstyle="round", zorder=3)
    ax.plot([est], [y], "o", ms=7, mfc=color, mec=t.surface, mew=1.5, zorder=4)


def _ordered(validators: list[dict]) -> list[dict]:
    return sorted(validators, key=lambda v: (FAMILY.index(v["client_id"]) if v["client_id"] in FAMILY else len(FAMILY),
                                             v["target_identity"]))


def _row_labels(c: Canvas, ax, rows: list[tuple[str, dict | str]], x0: float, x1: float) -> None:
    """Group name left and identity prefix right in the label column; section headers in bold."""
    tr = blended_transform_factory(c.fig.transFigure, ax.transData)
    for y, (kind, item) in enumerate(rows):
        if kind == "header":
            c.fig.text(x0 / c.w, y + 0.12, item, transform=tr, va="center", fontsize=8, fontweight="bold", color=c.t.ink2)
            continue
        c.fig.text(x0 / c.w, y, NAMES.get(item["client_id"], item["client_id"]), transform=tr, va="center", fontsize=9,
                   color=c.t.ink)
        c.fig.text(x1 / c.w, y, item["target_identity"][:8], transform=tr, va="center", ha="right", fontsize=8,
                   family="DejaVu Sans Mono", color=c.t.muted)


# ------------------------------------------------------------------------------------------------ identification
PANELS = {
    "c1": ("C1 · A vs B", "P(A lands before B)", "reward/cost and CU price → 1 · fee → 0"),
    "c2": ("C2 · A′ vs B", "P(A′ lands before B)", "reward/cost and fee → 0 · CU price → 1"),
    "c3": ("C3 · A vs A′", "P(A lands before A′)", "reward/cost → 1 · CU price and fee → tie"),
}


def fig_identification(res: dict, t: Theme) -> plt.Figure:
    vs = list(res["validators"].values())
    core, ext = _ordered([v for v in vs if v["confirmatory"]]), _ordered([v for v in vs if not v["confirmatory"]])
    rows: list[tuple[str, dict | str]] = [("header", "Core targets · confirmatory")] + [("row", v) for v in core]
    if ext:
        rows += [("header", "Extended targets · exploratory")] + [("row", v) for v in ext]
    slot, top, label_w, gap, right = 0.30, 2.0, 2.75, 0.32, 0.25
    width = 10.0
    c = Canvas(t, width, top + slot * len(rows) + 0.95)
    c.header("Every group orders by reward ÷ cost, none by arrival",
             "Solana mainnet after Alpenglow, 2026-10-24. Each row is one validator group (client × ingress); the unit is one leader window.\n"
             "The three contrasts are built so that the candidate rules disagree: only reward ÷ (cost + 1) predicts the pattern 1 · 0 · 1.")
    c.legend(0.25, 1.05, [_dot(t, t.series[0]), _dot(t, t.series[1]), Patch(facecolor=t.band, edgecolor="none")],
             ["priority label: P(first-named probe lands first)", "send order: P(first-sent probe lands first)",
              "tie band 0.35–0.65 (equivalence margin)"], ncol=3)
    pw = (width - label_w - right - 2 * gap) / 3
    first_ax = None
    for i, (cid, (title, ylab, pred)) in enumerate(PANELS.items()):
        ax = c.axes(label_w + i * (pw + gap), top, pw, slot * len(rows))
        first_ax = first_ax or ax
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(len(rows) - 0.5, -0.5)
        ax.axvspan(0.35, 0.65, color=t.band, lw=0, zorder=0)
        for x in (0, 0.5, 1):
            ax.axvline(x, color=t.grid, lw=PX, zorder=1)
        ax.set_yticks([])
        ax.set_xticks([0, 0.5, 1], ["0", "0.5", "1"])
        c.text(label_w + i * (pw + gap), top - 0.50, title, fontsize=10, fontweight="bold", color=t.ink, va="bottom")
        c.text(label_w + i * (pw + gap), top - 0.30, ylab, fontsize=8, color=t.ink2, va="bottom")
        c.text(label_w + i * (pw + gap), top - 0.12, pred, fontsize=7.5, color=t.muted, va="bottom")
        for y, (kind, v) in enumerate(rows):
            if kind != "row":
                continue
            for d, eff, color in ((-0.14, v["label"][cid], t.series[0]), (0.14, v["order"][cid], t.series[1])):
                lo, hi = eff["ci_bonferroni"]
                _interval(ax, lo, hi, eff["estimate"], y + d, color, t)
    _row_labels(c, first_ax, rows, 0.25, label_w - 0.3)
    c.footnote("Dots: estimates. Lines: exact 95 % Clopper–Pearson intervals, Bonferroni-adjusted over the 36-effect family; extended groups "
               "use the same adjustment and are exploratory.\nn = 20–43 windows per group and contrast; both members of the pair landed. "
               "Probes A, B, A′ differ only in requested compute, CU price and loaded-data limit. Table: REPORT.md §2.")
    return c.fig


# ------------------------------------------------------------------------------------------------ arrival
def window_frame(raw: Path, manifest_path: Path, designs: dict) -> pd.DataFrame:
    """One row per complete window of the main contrasts (all three pairs landed): its group, regime, achieved offset
    and whether every contrast went reward/cost's way. Same run selection and eligibility as the report."""
    dirs, _ = report.select_runs(raw, report.load_manifest(manifest_path))
    run = load_runs(dirs)
    windows = outcomes.window_table(run, designs)
    pairs = outcomes.pair_table(run, designs=designs, windows=windows)
    pairs = pairs[pairs["pair_kind"].isin(stats.CONTRASTS)]
    offsets = report.achieved_offsets(run).set_index(["run_id", "target_identity", "seq"])["achieved_offset_ms"]
    rows = []
    for (target, client, ingress), g in pairs.groupby(["target_identity", "client_id", "ingress"]):
        regime = g.drop_duplicates(["run_id", "seq"]).set_index(["run_id", "seq"])["regime"]
        for (run_id, seq), h in stats.window_hits(g, "reward_cost").iterrows():
            rows.append({"target_identity": target, "client_id": client, "ingress": ingress, "run_id": run_id,
                         "seq": int(seq), "regime": regime[(run_id, seq)], "complete": h["n"] == h["needed"],
                         "all_hit": bool(h["all_hit"]), "offset_ms": offsets.get((run_id, target, int(seq)), np.nan)})
    return pd.DataFrame(rows)


SECTIONS = (("Agave family · direct ingress", ("Agave", "JitoLabs", "Rakurai")),
            ("Firedancer · direct ingress", ("Firedancer",)),
            ("Block builders · shared ingress", ("AgaveBam", "FireBAM", "HarmonicAgave", "HarmonicFiredancer")))


def fig_arrival(wf: pd.DataFrame, t: Theme) -> plt.Figure:
    comp = wf[wf["complete"] & wf["offset_ms"].notna()]
    groups = comp[["target_identity", "client_id", "ingress"]].drop_duplicates().to_dict("records")
    rows: list[tuple[str, dict | str]] = []
    for title, clients in SECTIONS:
        members = _ordered([g for g in groups if g["client_id"] in clients])
        if members:
            rows += [("header", title)] + [("row", g) for g in members]
    slot, top, label_w, right_w = 0.30, 1.75, 2.75, 2.05
    width = 10.0
    c = Canvas(t, width, top + slot * len(rows) + 0.95)
    c.header("The Agave family keeps priority order only for what is queued before its slot",
             "Each dot is one leader window: did all three contrasts follow reward ÷ (cost + 1)? Horizontal position: when our first probe finished\n"
             "sending, relative to the first shred of the leader's slot. Firedancer and the builders keep the order either way.")
    c.legend(0.25, 1.05, [Line2D([], [], ls="", marker="o", ms=7, mfc=t.series[0], mec=t.surface, mew=1.5),
                          Line2D([], [], ls="", marker="o", ms=7, mfc=t.series[1], mec=t.surface, mew=1.5)],
             ["all three contrasts followed reward ÷ cost", "at least one did not"], ncol=2)
    pw = width - label_w - right_w
    ax = c.axes(label_w, top, pw, slot * len(rows))
    ax.set_xlim(-320, 540)
    ax.set_ylim(len(rows) - 0.5, -0.5)
    for x in (-300, -200, -100, 100, 200, 300, 400, 500):
        ax.axvline(x, color=t.grid, lw=PX, zorder=0)
    ax.axvline(0, color=t.ink2, lw=PX, zorder=1)
    ax.set_yticks([])
    ax.set_xticks([-300, -200, -100, 0, 100, 200, 300, 400, 500], ["−300", "−200", "−100", "0", "+100", "+200", "+300", "+400", "+500 ms"])
    c.text(label_w + pw * (320 - 160) / 860, top - 0.12, "←  queued before the slot", fontsize=8, color=t.ink2, ha="center", va="bottom")
    c.text(label_w + pw * (320 + 160) / 860, top - 0.12, "arrives during the slot  →", fontsize=8, color=t.ink2, ha="center", va="bottom")
    xr = label_w + pw + 0.35
    c.text(xr + 0.55, top - 0.12, "before", fontsize=8, color=t.ink2, ha="center", va="bottom")
    c.text(xr + 1.35, top - 0.12, "during", fontsize=8, color=t.ink2, ha="center", va="bottom")
    c.text(xr + 0.95, top - 0.32, "followed all three", fontsize=7.5, color=t.muted, ha="center", va="bottom")
    tr = blended_transform_factory(c.fig.transFigure, ax.transData)
    for y, (kind, g) in enumerate(rows):
        if kind != "row":
            continue
        w = comp[comp["target_identity"] == g["target_identity"]].sort_values("seq")
        jitter = ((w["seq"].to_numpy() * 0.6180339887) % 1 - 0.5) * 0.5
        for hit, color, z in ((True, t.series[0], 3), (False, t.series[1], 4)):
            m = (w["all_hit"] == hit).to_numpy()
            ax.plot(w["offset_ms"].to_numpy()[m], y + jitter[m], "o", ms=6.5, mfc=color, mec=t.surface, mew=1.2, ls="", zorder=z)
        for dx, before in ((0.55, True), (1.35, False)):
            s = w[(w["offset_ms"] < 0) == before]
            txt = f"{int(s['all_hit'].sum())}/{len(s)}" if len(s) else "–"
            c.fig.text((xr + dx) / c.w, y, txt, transform=tr, ha="center", va="center", fontsize=8.5,
                       color=t.ink if len(s) and s["all_hit"].all() else (t.ink if len(s) else t.muted),
                       fontweight="bold" if len(s) and not s["all_hit"].all() else "normal")
    _row_labels(c, ax, rows, 0.25, label_w - 0.3)
    dropped = int((~wf["complete"]).sum())
    c.footnote(f"Complete windows only: all three pairs landed ({dropped} windows without a complete set omitted). Shared BAM / Harmonic ingress "
               "receives everything during the window,\nso builder windows all sit right of zero. Bold counts: windows where the rule broke. "
               "Regime split with intervals: REPORT.md §3.")
    return c.fig


# ------------------------------------------------------------------------------------------------ races
RACE_GROUPS = (("Agave family", ("Agave", "JitoLabs", "Rakurai"), "direct"),
               ("Firedancer", ("Firedancer",), "direct"),
               ("Firedancer + Harmonic", ("HarmonicFiredancer",), "harmonic_remote_tpu"),
               ("Agave + Harmonic", ("HarmonicAgave",), "harmonic_remote_tpu"))


def _horizon(points: list[tuple[float, int, int]]) -> str:
    lo, hi = study2.horizon(points)
    if lo is None:
        return f"horizon < {hi:.0f} ms"
    return f"horizon ≈ {lo:.0f}–{hi:.0f} ms" if hi is not None else f"horizon > {lo:.0f} ms"


def fig_races(races: dict[tuple, list[int]], t: Theme) -> plt.Figure:
    dts = sorted({dt for (_, _, dt) in races})
    width, top, gap = 10.0, 1.75, 0.35
    c = Canvas(t, width, top + 2.3 + 0.95)
    c.header("How long a head start can a higher-priority transaction overcome?",
             "Stage 2, exploratory. Races where the low-priority probe was sent Δt ms before the high-priority one: share in which the high-priority\n"
             "probe still landed first. When the high-priority probe was sent first, it landed first in every race, on every validator.")
    pw = (width - 0.6 - 0.25 - 3 * gap) / 4
    for i, (name, clients, ingress) in enumerate(RACE_GROUPS):
        pts = []
        for dt in dts:
            k = sum(v[2] for (cl, ing, d), v in races.items() if cl in clients and ing == ingress and d == dt)
            n = sum(v[3] for (cl, ing, d), v in races.items() if cl in clients and ing == ingress and d == dt)
            pts.append((dt, k, n))
        x0 = 0.6 + i * (pw + gap)
        ax = c.axes(x0, top, pw, 2.3)
        ax.set_xlim(-0.4, len(dts) - 0.6)
        ax.set_ylim(-0.04, 1.04)
        for y in (0, 0.5, 1):
            ax.axhline(y, color=t.grid if y else t.axis, lw=PX, zorder=0)
        ax.set_xticks(range(len(dts)), [f"{dt:.0f}" for dt in dts])
        ax.set_yticks([0, 0.5, 1], ["0", "0.5", "1"] if i == 0 else [])
        ax.set_xlabel("head start, ms", fontsize=8, color=t.muted, labelpad=4)
        c.text(x0, top - 0.36, name, fontsize=10, fontweight="bold", color=t.ink, va="bottom")
        c.text(x0, top - 0.16, _horizon(pts), fontsize=8, color=t.ink2, va="bottom")
        xs = [j for j, (_, _, n) in enumerate(pts) if n]
        ax.plot(xs, [pts[j][1] / pts[j][2] for j in xs], color=t.series[0], lw=2 * PX, zorder=2, solid_joinstyle="round")
        for j in xs:
            dt, k, n = pts[j]
            lo, hi = stats.clopper_pearson(k, n, 0.05)
            ax.plot([j, j], [lo, hi], color=t.series[0], lw=PX, alpha=0.55, zorder=1)
            ax.plot([j], [k / n], "o", ms=7, mfc=t.series[0], mec=t.surface, mew=1.5, zorder=3)
            ax.text(j + 0.12, k / n + (0.06 if k / n < 0.9 else -0.08), f"{k}/{n}", fontsize=7.5, color=t.ink2, va="center")
    c.footnote("Thin lines: exact 95 % Clopper–Pearson intervals (exploratory, no multiplicity adjustment). Evaluable windows, both racers landed. "
               "BAM groups ran too few races to show.\nhi: 3,000,000 µlamports/CU; lo: 1,000,000 µlamports/CU with a 64 MiB loaded-data request. "
               "Table: REPORT.md §5, data/derived/exploratory_stage2.md.")
    return c.fig


# ------------------------------------------------------------------------------------------------ hold cliff
HOLD_ROWS = (("Agave", "Agave"), ("JitoLabs", "Jito-Solana"), ("Firedancer", "Firedancer"))
HOLD_STATUS = (("landed_target", "landed in the target window"), ("expired_confirmed", "expired"),
               ("spillover_same_validator_other_window", "landed in a later window"))


def fig_hold(hold: dict[tuple, dict[str, int]], t: Theme) -> plt.Figure:
    width, top = 10.0, 1.75
    rows = [r for r in HOLD_ROWS if any(cl == r[0] for (cl, _, _) in hold)]
    c = Canvas(t, width, top + 0.6 * len(rows) + 0.2 + 0.95)
    c.header("Agave drops what it held too long; Firedancer keeps it",
             "Stage 2, exploratory. Identical probes sent 7 s, 3 s and 0.5 s before the target's leader window, direct ingress. One square per probe\n"
             "sent. Agave forwards held packets only while they are at most 20 slots old, about 4 s at the observed slot cadence.")
    colors = dict(zip([s for s, _ in HOLD_STATUS], t.series))
    used = {s for v in hold.values() for s, n in v.items() if n and s in colors}
    c.legend(0.25, 1.05, [Rectangle((0, 0), 1, 1, facecolor=colors[s], edgecolor="none") for s, _ in HOLD_STATUS if s in used],
             [lab for s, lab in HOLD_STATUS if s in used], ncol=3)
    label_w = 1.6
    ax = c.axes(label_w, top, width - label_w - 0.4, 0.6 * len(rows))
    ax.set_xlim(-8.2, 0.2)
    ax.set_ylim(len(rows) - 0.25, -0.5)
    ax.axvspan(-8.2, -4.0, color=t.band, lw=0, zorder=0)
    ax.axvline(-4.0, color=t.ink2, lw=PX, zorder=1)
    ax.text(-4.08, -0.62, "older than 20 slots ≈ 4 s", fontsize=7.5, color=t.ink2, ha="right", va="bottom")
    ax.axvline(0, color=t.axis, lw=PX, zorder=1)
    ax.set_yticks([])
    ax.set_xticks([-8, -7, -6, -5, -4, -3, -2, -1, 0], ["−8", "−7", "−6", "−5", "−4", "−3", "−2", "−1", "0 s"])
    ax.set_xlabel("sent before the target's leader window", fontsize=8, color=t.muted, labelpad=4)
    tr = blended_transform_factory(c.fig.transFigure, ax.transData)
    sq, step = 0.13, 0.16  # square width and pitch, in seconds of the x axis
    not_sent = 0
    for y, (client, name) in enumerate(rows):
        c.fig.text(0.25 / c.w, y, name, transform=tr, va="center", fontsize=9, color=t.ink)
        for (cl, _, off), counts in sorted(hold.items(), key=lambda kv: kv[0][2]):
            if cl != client:
                continue
            not_sent += counts.get("not_sent", 0)
            cells = [s for s, _ in HOLD_STATUS for _ in range(counts.get(s, 0))]
            x = off - (len(cells) * step - (step - sq)) / 2
            for s in cells:
                ax.add_patch(Rectangle((x, y - 0.17), sq, 0.34, facecolor=colors[s], edgecolor="none", zorder=3))
                x += step
            landed = counts.get("landed_target", 0)
            ax.text(off, y + 0.36, f"{landed}/{len(cells)}", fontsize=7.5, color=t.ink2, ha="center", va="top")
    c.footnote(f"Counts under each group: landed in the target window / probes sent. {not_sent} planned probes were not sent "
               "and are not shown.\nTable: REPORT.md §5, data/derived/exploratory_stage2.md.")
    return c.fig


# ------------------------------------------------------------------------------------------------ Study 2
STUDY2_DTS = (0.0, 2.0, 5.0, 10.0, 25.0, 50.0)


def _claim_for(res2: dict, c: dict) -> str:
    """'H1-agave: supported' for the hypothesis whose frozen group this curve is, else 'exploratory'."""
    for h in res2.get("hypotheses", []):
        if h["pair_kind"] == "race" and any((g["identity"], g["client_id"], g["ingress"]) == (c["target_identity"], c["client_id"], c["ingress"])
                                            for g in h["groups"]):
            return f"{h['id']}: {h.get('published_claim', h['verdict'])}"
    return "exploratory"


def _day(runs: list[dict]) -> str:
    days = sorted({r["started_at"][:10] for r in runs if r.get("started_at")})
    return days[0] if len(days) == 1 else (f"{days[0]}…{days[-1]}" if days else "")


def fig_study2_races(res2: dict, t: Theme) -> plt.Figure:
    curves = _ordered([c for c in res2.get("curves", {}).values() if c["overtake_lo_first"]])
    ncol = 3
    nrow = max(1, -(-len(curves) // ncol))
    width, top, gap, ph = 10.0, 1.75, 0.35, 1.9
    c0 = Canvas(t, width, top + nrow * (ph + 0.95) + 0.55)
    c0.header("How far does each client reorder against arrival?",
              f"Study 2, pre-registered, {_day(res2.get('runs', []))}. Share of races in which the high-priority probe landed before a low-priority one sent\n"
              "Δt ms earlier (at 0 ms both go out together). The 2 ms cell decides H1 / H2; the other cells are exploratory.")
    pw = (width - 0.6 - 0.25 - (ncol - 1) * gap) / ncol
    for i, c in enumerate(curves):
        r, col = divmod(i, ncol)
        x0, y0 = 0.6 + col * (pw + gap), top + r * (ph + 0.95)
        ax = c0.axes(x0, y0, pw, ph)
        ax.set_xlim(-0.4, len(STUDY2_DTS) - 0.6)
        ax.set_ylim(-0.04, 1.04)
        for y in (0, 0.5, 1):
            ax.axhline(y, color=t.grid if y else t.axis, lw=PX, zorder=0)
        ax.axvspan(0.6, 1.4, color=t.band, lw=0, zorder=0)
        ax.set_xticks(range(len(STUDY2_DTS)), [f"{dt:g}" for dt in STUDY2_DTS])
        ax.set_yticks([0, 0.5, 1], ["0", "0.5", "1"] if col == 0 else [])
        ax.set_xlabel("head start Δt, ms", fontsize=8, color=t.muted, labelpad=3)
        name = f"{NAMES.get(c['client_id'], c['client_id'])}"
        c0.text(x0, y0 - 0.40, name, fontsize=10, fontweight="bold", color=t.ink, va="bottom")
        c0.text(x0 + pw, y0 - 0.40, c["target_identity"][:8], fontsize=7.5, family="DejaVu Sans Mono", color=t.muted,
                va="bottom", ha="right")
        c0.text(x0, y0 - 0.20, _claim_for(res2, c), fontsize=7.5, color=t.ink2, va="bottom")
        pts = [(j, *c["overtake_lo_first"].get(f"{dt:g}", (0, 0))) for j, dt in enumerate(STUDY2_DTS)]
        xs = [j for j, k, n in pts if n]
        ax.plot(xs, [pts[j][1] / pts[j][2] for j in xs], color=t.series[0], lw=2 * PX, zorder=2, solid_joinstyle="round")
        for j, k, n in pts:
            if not n:
                continue
            lo, hi = stats.clopper_pearson(k, n, 0.05)
            ax.plot([j, j], [lo, hi], color=t.series[0], lw=PX, alpha=0.55, zorder=1)
            ax.plot([j], [k / n], "o", ms=7 if j != 1 else 8.5, mfc=t.series[0], mec=t.surface, mew=1.5, zorder=3)
            ax.text(j + 0.13, k / n + (0.07 if k / n < 0.88 else -0.09), f"{k}/{n}", fontsize=7, color=t.ink2, va="center")
    c0.footnote("Dots: overtakes / races where both landed, in evaluable windows. Thin lines: exact 95 % Clopper–Pearson intervals. Shaded: the "
                "confirmatory 2 ms cell (Holm over six,\none-sided exact binomial; PREREGISTRATION-2 §3–§4). Δt is the gap between our two sends. "
                "Tables: REPORT.md, data/derived/study2/summary.md.")
    return c0.fig


def fig_replication(res1: dict, res2: dict, t: Theme) -> plt.Figure:
    rep = res2.get("replication", {}).get("validators", {})
    keys = [k for k, v in res1["validators"].items() if v["confirmatory"] and k in rep]
    rows: list[tuple[str, dict | str]] = [("row", res1["validators"][k]) for k in
                                          sorted(keys, key=lambda k: (FAMILY.index(res1["validators"][k]["client_id"])
                                                                      if res1["validators"][k]["client_id"] in FAMILY else 99, k))]
    slot, top, label_w, gap, right = 0.42, 2.0, 2.75, 0.32, 0.25
    width = 10.0
    c = Canvas(t, width, top + slot * max(len(rows), 1) + 0.95)
    c.header("A second day, the same rule",
             f"The Study 1 confirmatory procedure, unchanged, on {_day(res2.get('replication', {}).get('runs', []))} (Study 2) against {_day(res1.get('runs', []))} "
             "(Study 1), for the six core targets.\nOnly reward ÷ (cost + 1) predicts the pattern 1 · 0 · 1; a target replicates when its published claim is the same.")
    c.legend(0.25, 1.05, [_dot(t, t.muted), _dot(t, t.series[0])], ["Study 1", "Study 2"], ncol=2)
    pw = (width - label_w - right - 2 * gap) / 3
    first_ax = None
    for i, (cid, (title, ylab, pred)) in enumerate(PANELS.items()):
        ax = c.axes(label_w + i * (pw + gap), top, pw, slot * max(len(rows), 1))
        first_ax = first_ax or ax
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(len(rows) - 0.5, -0.5)
        ax.axvspan(0.35, 0.65, color=t.band, lw=0, zorder=0)
        for x in (0, 0.5, 1):
            ax.axvline(x, color=t.grid, lw=PX, zorder=1)
        ax.set_yticks([])
        ax.set_xticks([0, 0.5, 1], ["0", "0.5", "1"])
        c.text(label_w + i * (pw + gap), top - 0.50, title, fontsize=10, fontweight="bold", color=t.ink, va="bottom")
        c.text(label_w + i * (pw + gap), top - 0.30, ylab, fontsize=8, color=t.ink2, va="bottom")
        c.text(label_w + i * (pw + gap), top - 0.12, pred, fontsize=7.5, color=t.muted, va="bottom")
        for y, (_, v) in enumerate(rows):
            key = f"{v['target_identity']}|{v['client_id']}|{v['ingress']}"
            for d, eff, color in ((-0.12, v["label"][cid], t.muted), (0.12, rep[key]["label"][cid], t.series[0])):
                if eff["n"]:
                    _interval(ax, *eff["ci_bonferroni"], eff["estimate"], y + d, color, t)
    _row_labels(c, first_ax, rows, 0.25, label_w - 0.3)
    c.footnote("Dots: estimates. Lines: exact 95 % Clopper–Pearson intervals, Bonferroni-adjusted over each study's 36-effect family. "
               "The windows of the two studies\nare never pooled. Replication table: REPORT.md, data/derived/study2/summary.md.")
    return c.fig


STUDY3_PANELS = {
    "c4": ("C4 · Y vs A", "P(Y lands before A)", "reward/cost → 1 · cost alone → 0", 0.0),
    "c5": ("C5 · hi vs A", "P(hi lands before A)", "reward/cost → 1 · cost alone → tie, 0.5", 0.5),
}


def fig_study3(res3: dict, t: Theme) -> plt.Figure:
    hyps = {(h["groups"][0]["identity"], h["pair_kind"]): h for h in res3.get("hypotheses", [])}
    diag = {(d["target_identity"], d["pair_kind"]): d for d in res3.get("diagnostics", []) if d["confirmatory_group"]}
    rows: list[tuple[str, dict | str]] = [("row", {"client_id": r["client_id"], "target_identity": r["identity"]})
                                          for r in res3.get("identification", [])]
    rows = [("row", v) for v in _ordered([v for _, v in rows])]
    slot, top, label_w, gap, right = 0.42, 2.0, 2.75, 0.75, 0.6
    width = 10.0
    c = Canvas(t, width, top + slot * max(len(rows), 1) + 0.95)
    c.header("The reward counts, not just the cost",
             f"Study 3, pre-registered, {_day(res3.get('runs', []))}, the six core targets. C4: Y requests more compute than A but pays more per cost unit. "
             "C5: hi and A cost the same,\nhi pays more. Reward ÷ (cost + 1) predicts 1 · 1; ordering by requested cost alone predicts 0 · 0.5.")
    c.legend(0.25, 1.05, [_dot(t, t.series[0]), _dot(t, t.series[1]), Line2D([], [], color=t.muted, lw=PX, ls=(0, (3, 3)))],
             ["priority label: P(higher reward per cost lands first)", "send order: P(first-sent probe lands first)",
              "what cost alone predicts"], ncol=3)
    pw = (width - label_w - right - gap) / 2
    first_ax = None
    for i, (kind, (title, ylab, pred, cost_only)) in enumerate(STUDY3_PANELS.items()):
        ax = c.axes(label_w + i * (pw + gap), top, pw, slot * max(len(rows), 1))
        first_ax = first_ax or ax
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(len(rows) - 0.5, -0.5)
        for x in (0, 0.5, 1):
            ax.axvline(x, color=t.grid, lw=PX, zorder=1)
        ax.axvline(cost_only, color=t.muted, lw=PX, ls=(0, (3, 3)), zorder=2)
        ax.set_yticks([])
        ax.set_xticks([0, 0.5, 1], ["0", "0.5", "1"])
        c.text(label_w + i * (pw + gap), top - 0.50, title, fontsize=10, fontweight="bold", color=t.ink, va="bottom")
        c.text(label_w + i * (pw + gap), top - 0.30, ylab, fontsize=8, color=t.ink2, va="bottom")
        c.text(label_w + i * (pw + gap), top - 0.12, pred, fontsize=7.5, color=t.muted, va="bottom")
        for y, (_, v) in enumerate(rows):
            h, d = hyps.get((v["target_identity"], kind)), diag.get((v["target_identity"], kind))
            if h and h["n"]:
                _interval(ax, *h["ci95"], h["estimate"], y - 0.12, t.series[0], t)
                ax.text(1.09, y - 0.12, f"{h['k']}/{h['n']}", fontsize=7.5, color=t.ink2, va="center", clip_on=False)
            if d and d["first_sent_first"][1]:
                k, n = d["first_sent_first"]
                lo, hi = stats.clopper_pearson(k, n, 0.05)
                _interval(ax, lo, hi, k / n, y + 0.12, t.series[1], t)
    _row_labels(c, first_ax, rows, 0.25, label_w - 0.3)
    c.footnote("Dots: estimates over evaluable windows where both probes landed (k/n at the right). Lines: exact 95 % Clopper–Pearson intervals; the tests are "
               "one-sided exact binomial,\nHolm over twelve (PREREGISTRATION-3 §4). A, Y and hi differ only in CU limit and CU price. "
               "Table: REPORT.md §6.5, data/derived/study3/summary.md.")
    return c.fig


# ------------------------------------------------------------------------------------------------ driver
def _svg(fig: plt.Figure) -> bytes:
    buf = io.StringIO()  # no newline translation, so the bytes are LF on every platform
    fig.savefig(buf, format="svg", metadata={"Date": None})
    plt.close(fig)
    return buf.getvalue().encode()


def render(results: Path, raw: Path, manifest: Path, design: Path) -> dict[str, bytes]:
    """File name -> SVG bytes for every figure in both themes."""
    res = json.loads(results.read_text())
    designs = load_designs(sorted(design.parent.glob("*.jsonl")))
    wf = window_frame(raw, manifest, designs)
    s2 = exploratory.load_stage2(raw, design)
    races, hold = exploratory.races(s2.probes), exploratory.hold(s2.probes)
    # Study 2 figures join once its results are committed next to Study 1's (data/derived/study2/results.json).
    study2_path = results.parent / "study2" / "results.json"
    res2 = json.loads(study2_path.read_text()) if study2_path.exists() else None
    study3_path = results.parent / "study3" / "results.json"
    res3 = json.loads(study3_path.read_text()) if study3_path.exists() else None
    out = {}
    for t in THEMES:
        suffix = "" if t is LIGHT else "-dark"
        with plt.rc_context(_rc(t)):
            makers = [("identification", lambda: fig_identification(res, t)), ("arrival", lambda: fig_arrival(wf, t)),
                      ("races", lambda: fig_races(races, t)), ("hold", lambda: fig_hold(hold, t))]
            if res2 is not None:
                makers += [("study2-races", lambda: fig_study2_races(res2, t)),
                           ("study2-replication", lambda: fig_replication(res, res2, t))]
            if res3 is not None:
                makers += [("study3-contrasts", lambda: fig_study3(res3, t))]
            for name, make in makers:
                out[f"{name}{suffix}.svg"] = _svg(make())
    return out


def build(results: Path, raw: Path, manifest: Path, design: Path, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, data in render(results, raw, manifest, design).items():
        (out / name).write_bytes(data)
        written.append(out / name)
    return written


def check(results: Path, raw: Path, manifest: Path, design: Path, committed: Path) -> list[str]:
    """Committed figures that a fresh drawing does not reproduce byte for byte (missing ones included)."""
    return [name for name, data in render(results, raw, manifest, design).items()
            if not (committed / name).exists() or (committed / name).read_bytes() != data]
