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
  and the selection bound are all applied.
- **Replicates:** 40 per scenario.

```bash
PYTHONPATH=analysis python scripts/oc_study2.py --reps 40   # writes data/derived/oc-study2.{json,md}
```

## Scenarios

| Scenario | What is true |
|---|---|
| `study1_picture` | Agave and Jito-Solana: arrival order (FIFO). Firedancer: a priority pass every 15 ms, later-arrival-first ties. Harmonic: auctions every 25 ms (Firedancer + Harmonic) and 60 ms (Agave + Harmonic). BAM: every 50 ms. Every hypothesis is true. |
| `weak_effects` | Agave family: arrival order plus 2 ms of independent jitter per transaction (true O(2) ≈ 0.24). Firedancer: passes every 6 ms (O(2) ≈ 0.67). Harmonic and BAM: auctions every 8 ms (O(2) ≈ 0.75). Every hypothesis is true, but the race effects are weak. |
| `opposite` | Agave family: priority passes every 15 ms with random ties. Firedancer and Harmonic: FIFO. Firedancer ties: random. Every hypothesis is false. |

## Results: share of simulated campaigns in which each hypothesis is published as supported

| Scenario | H1-agave | H1-jito | H2-firedancer | H2-firedancer-harmonic | H2-agave-harmonic | H3-firedancer-ties |
|---|---|---|---|---|---|---|
| `study1_picture` | 1.00 | 1.00 | 0.97 | 0.97 | 1.00 | 1.00 |
| `weak_effects` | 0.78 | 0.72 | 0.33 | 0.68 | 0.62 | 1.00 |
| `opposite` (all false) | **0.00** | **0.00** | **0.00** | **0.00** | **0.00** | **0.00** |

**Median informative pairs** per hypothesis: 26–27 races (planned 35), 44–45 equal-key pairs (planned 59). The
shortfall is the simulated 10 % loss per member plus the injected observation failures.

**Selection-robust share** (supported, and still passing at 0.05/6 when every incomplete pair is counted against
it), under `study1_picture`:

| H1-agave | H1-jito | H2-firedancer | H2-firedancer-harmonic | H2-agave-harmonic | H3-firedancer-ties |
|---|---|---|---|---|---|
| 0.80 | 0.93 | 0.28 | 0.60 | 0.78 | 1.00 |

## Reading

- **If Study 1's exploratory picture is right, Study 2 confirms it**: each hypothesis in 97–100 % of campaigns.
- **If the picture is wrong in the opposite direction, no hypothesis is ever supported** (0 of 40 for each). That is
  the family-wise error the Holm procedure controls, observed at zero.
- **Weak effects are found only part of the time**: 33–78 % for the races. A "not supported" verdict in Study 2 is
  therefore reported with its interval, never as evidence against the hypothesis (PREREGISTRATION-2 §4).
- **The selection bound is strict at 90 % landing.** With 10 % of members lost, a supported Firedancer race claim
  survives the worst case in 28 % of campaigns. When it does not, it carries "(assumes selection)", exactly as in
  Study 1.
- **In Study 1 the real landing rate was higher.** Probes that left the process landed in the target window at
  100 % for 8 of 10 validators (CAMPAIGN-LOG). Live n is expected nearer the planned 35 and 59.
- **What the simulation cannot show:** a scheduler unlike every model here. The hi-first controls and the
  achieved-gap check (PREREGISTRATION-2 §8) are the live guards against that.
