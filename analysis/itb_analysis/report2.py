"""Study 2 tables for REPORT.md, from the output of `study2.compute` (the frozen decision code: this module only
formats what it decided).

    python -m itb_analysis.cli study2 report      # recompute data/derived/study2/results.json + summary.md
    python -m itb_analysis.cli study2 reproduce   # recompute and compare with the committed results
"""

from __future__ import annotations

from .stats import clopper_pearson

NAMES = {"Agave": "Agave", "JitoLabs": "Jito-Solana", "Rakurai": "Rakurai", "Firedancer": "Firedancer",
         "AgaveBam": "Agave + BAM", "FireBAM": "Firedancer + BAM", "HarmonicAgave": "Agave + Harmonic",
         "HarmonicFiredancer": "Firedancer + Harmonic"}


def _kn(cell) -> str:
    return "–" if not cell or cell[1] == 0 else f"{cell[0]}/{cell[1]}"


def _kn_ci(cell) -> str:
    """k/n with its exact 95 % Clopper-Pearson interval (PREREGISTRATION-2 §7)."""
    if not cell or cell[1] == 0:
        return "–"
    lo, hi = clopper_pearson(cell[0], cell[1], 0.05)
    return f"{cell[0]}/{cell[1]} ({lo:.2f}–{hi:.2f})"


def _p(x: float) -> str:
    """The results files keep six decimals, so a positive p-value below 10^-6 is stored as 0: print it as a bound."""
    return "< 10⁻⁶" if x == 0 else f"{x:.2g}"


def _monotone(cells: list) -> bool:
    shares = [k / n for k, n in cells if n]
    return all(b <= a for a, b in zip(shares, shares[1:]))


def replication_table(res: dict) -> str:
    lines = ["| Target | Client | Ingress | Study 1 claim | Study 2 claim | Replicated |", "|---|---|---|---|---|---|"]
    for r in res.get("replicated", []):
        lines.append(f"| `{r['identity'][:8]}` | {NAMES.get(r['client_id'], r['client_id'])} | {r['ingress']} | "
                     f"{r['study1_claim']} | {r['study2_claim'] or '–'} | {'**yes**' if r['replicated'] else 'no'} |")
    return "\n".join(lines)


def hypotheses_table(res: dict) -> str:
    lines = ["| ID | Estimand | k/n | Estimate [95 % CI] | Holm p | Published claim | Per target |",
             "|---|---|---|---|---|---|---|"]
    for h in res.get("hypotheses", []):
        est = "–" if not h["n"] else f"{h['estimate']:.2f} [{h['ci95'][0]:.2f}, {h['ci95'][1]:.2f}]"
        sym = "O" if h["pair_kind"] == "race" else "E"
        per = ", ".join(f"`{t[:8]}` {k}/{n}" for t, (k, n) in h.get("by_target", {}).items())
        lines.append(f"| `{h['id']}` | {sym}({h['dt_ms']:g} ms) {'<' if h['side'] == 'less' else '>'} 0.5 | {h['k']}/{h['n']} | "
                     f"{est} | {_p(h['p_holm'])} | **{h['published_claim']}** | {per} |")
    return "\n".join(lines)


def sensitivity_table(res: dict) -> str:
    sens = res.get("sensitivity", {})
    ids = [h["id"] for h in res.get("hypotheses", [])]
    lines = ["| Analysis | " + " | ".join(f"`{i}`" for i in ids) + " |", "|---|" + "---|" * len(ids)]
    for name, rows in sens.items():
        cells = [f"{rows[i]['k']}/{rows[i]['n']} {rows[i]['verdict']}" if i in rows else "–" for i in ids]
        lines.append(f"| {name.replace('_', ' ')} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def curves_table(res: dict) -> str:
    curves = res.get("curves", {})
    dts = sorted({float(dt) for c in curves.values() for dt in c["overtake_lo_first"]})
    lines = ["| Group | " + " | ".join(f"Δt {dt:g} ms" for dt in dts) + " | Horizon bracket (descriptive) | Equal key (first-sent first) |",
             "|---|" + "---|" * (len(dts) + 2)]
    for c in sorted(curves.values(), key=lambda c: (c["client_id"] or "", c["target_identity"])):
        raw = [c["overtake_lo_first"].get(f"{dt:g}") for dt in dts]
        cells = [_kn_ci(x) for x in raw]
        hz = c.get("horizon_ms")
        bracket = "–" if not hz else (f"< {hz[1]:g} ms" if hz[0] is None else
                                      (f"{hz[0]:g}–{hz[1]:g} ms" if hz[1] is not None else f"> {hz[0]:g} ms"))
        if hz and not _monotone([x for x in raw if x]):
            bracket += " (non-monotone)"
        eq = ", ".join(f"{dt} ms: {_kn(v)}" for dt, v in c["equal_key_first_sent_first"].items()) or "–"
        lines.append(f"| {NAMES.get(c['client_id'], c['client_id'])} `{c['target_identity'][:8]}` | " + " | ".join(cells)
                     + f" | {bracket} | {eq} |")
    return "\n".join(lines)


def markdown_summary(res: dict) -> str:
    parts = ["## Replication (hypothesis R)", replication_table(res)]
    if res.get("hypotheses"):
        parts += ["## Hypotheses H1–H3", hypotheses_table(res), "## Sensitivity analyses", sensitivity_table(res),
                  "## Overtakes against a head start (exploratory; cells: hi landed first / races, exact 95 % interval)",
                  curves_table(res)]
    return "\n\n".join(parts) + "\n"
