# Study 2 — operating characteristics (before freezing)

**What this checks.** Study 2 decides six hypotheses (PREREGISTRATION-2 §3). Two questions follow:
- How often does the published procedure call each one *supported* when it is true?
- How often when it is false?

**Method.**
- **Design:** the frozen Study 2 design (`design/design-study2.jsonl`), stage 2. That gives 35 R windows per race
  target and 24 E windows for `9eGrDohd`.
- **Simulation:** run through `itb_analysis.sim` with schedulers whose horizon and tie-break are known. Every member
  lands with probability 0.9. Study 1's observation failures are injected:
  - lost streams;
  - unproduced blocks;
  - gossip changes.
- **Analysis:** `itb_analysis.study2`, the code the live data will go through. Window eligibility, Holm over the six,
  the selection bound and the §8 gates (hi-first controls, achieved gaps) are all applied. A hypothesis counts as
  supported when its published claim is.
- **Replicates:** 100 per scenario.

```bash
PYTHONPATH=analysis python scripts/oc_study2.py --reps 100  # writes data/derived/oc-study2.{json,md}
```

## Scenarios

| Scenario | What is true |
|---|---|
| `study1_picture` | Agave and Jito-Solana: arrival order (FIFO). Firedancer: a priority pass every 15 ms, later-arrival-first ties. Harmonic: auctions every 25 ms (Firedancer + Harmonic) and 60 ms (Agave + Harmonic). BAM: every 50 ms. Every hypothesis is true. |
| `weak_effects` | Agave family: arrival order plus 2 ms of independent jitter per transaction (true O(2) ≈ 0.24). Firedancer: passes every 6 ms (O(2) ≈ 0.67). Harmonic and BAM: auctions every 8 ms (O(2) ≈ 0.75). Every hypothesis is true, but the race effects are weak. |
| `opposite` | Agave family: priority passes every 15 ms with random ties. Firedancer and Harmonic: FIFO. Firedancer ties: random. Every hypothesis is false, by a wide margin. |
| `boundary_null` | Every group exactly at the null: priority passes or auctions every 4 ms, so O(2) = 0.5; Firedancer ties random, so E = 0.5. Every hypothesis is false, by the smallest possible margin: the hardest case for error control. |

## Results: share of simulated campaigns in which each hypothesis is published as supported

| Scenario | H1-agave | H1-jito | H2-firedancer | H2-firedancer-harmonic | H2-agave-harmonic | H3-firedancer-ties | Campaigns with any false support |
|---|---|---|---|---|---|---|---|
| `study1_picture` | 1.00 | 1.00 | 0.98 | 1.00 | 1.00 | 1.00 | — |
| `weak_effects` | 0.76 | 0.72 | 0.37 | 0.62 | 0.63 | 1.00 | — |
| `opposite` (all false) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0 / 100** (95 % upper bound 0.04) |
| `boundary_null` (all false) | 0.03 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 | **4 / 100** (95 % CI 0.01–0.10) |

**Median informative pairs** per hypothesis: 26–27 races (planned 35), 44–45 equal-key pairs (planned 59). The
shortfall is the simulated 10 % loss per member plus the injected observation failures.

**Selection-robust share** (supported without "(assumes selection)": still passing at 0.05/6 when every incomplete
pair is counted against it), under `study1_picture`:

| H1-agave | H1-jito | H2-firedancer | H2-firedancer-harmonic | H2-agave-harmonic | H3-firedancer-ties |
|---|---|---|---|---|---|
| 0.88 | 0.92 | 0.32 | 0.64 | 0.73 | 1.00 |

## Reading

- **If Study 1's exploratory picture is right, Study 2 confirms it**: each hypothesis in 98–100 % of campaigns.
- **False support stays at the nominal level.** With every hypothesis false by a wide margin, no campaign supports any
  of them (0 of 100). At the boundary, where each estimand is exactly 0.5, 4 of 100 campaigns support at least one,
  consistent with the ≤ 5 % family-wise error that Holm guarantees. Simulation can only bound that rate (95 % CI
  0.01–0.10); the guarantee itself is analytical.
- **Weak effects are found only part of the time**: 37–76 % for the races. A "not supported" verdict in Study 2 is
  therefore reported with its interval, never as evidence against the hypothesis (PREREGISTRATION-2 §4).
- **The selection bound is strict at 90 % landing.** With 10 % of members lost, a supported Firedancer race claim
  survives the worst case in 32 % of campaigns. When it does not, it carries "(assumes selection)", exactly as in
  Study 1.
- **The real landing rate was higher for most targets.** In Study 1 Stage 1, every sent probe landed for 5 of 10
  targets, and 80–99 % for the others (the "8 of 10" in CAMPAIGN-LOG refers to the pilot). Live n is expected
  between the simulated and the planned figures. Measured afterwards, in Study 2 Stage 2 every sent probe landed
  (REPORT §6).
- **No gate fired in any simulated campaign.** The simulator sends exactly on time and its schedulers respect
  priority. The gates guard against what the models leave out: a scheduler unlike every model here, or a sender that
  misses its gap.
