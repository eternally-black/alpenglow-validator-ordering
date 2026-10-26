# Study 3 — operating characteristics (before freezing)

**What this checks.** Study 3 asks per core target whether the reward enters the ordering key. It runs twelve
hypotheses, H4 and H5 for each of six targets. A target's key is identified as reward ÷ (cost + 1), among the
registered candidates, when both are supported and its frozen Study 1 and Study 2 claims are `reward_cost`
(PREREGISTRATION-3 §5). This page answers three questions:
- How often is the key identified when it really is reward ÷ cost?
- How often when the scheduler orders by cost alone?
- What happens under a key outside the registered candidates?

**Method.**
- **Design:** the Study 3 design to be frozen (`design/design-study3.jsonl`, SHA-256 `bfaa83b6…`): 32 windows per
  target, one C4 and one C5 pair in each.
- **Simulation:** `itb_analysis.sim` with schedulers whose key is known, at the measured in-window slot of 198 ms.
  - Each member lands with probability 0.90, except in one scenario that uses each target's observed rate.
  - Study 1's observation failures are injected: lost streams, unproduced blocks, gossip changes.
- **Analysis:** `itb_analysis.study3`, the code the live data will go through, including window eligibility, Holm over
  twelve, the selection bound, the positive-control gate and the selection qualifier.
- **Replicates:** 100 per scenario. Every share comes with its 95 % Clopper–Pearson interval over the replicates.
  These are simulation results under the stated models, not a guarantee of power.

```bash
PYTHONPATH=analysis python scripts/oc_study3.py --reps 100   # writes data/derived/oc-study3.{json,md}
```

## Scenarios

| Scenario | What is true |
|---|---|
| `reward_cost` | Every target orders by reward ÷ (cost + 1): the truth that Studies 1 and 2 point to. Each member lands with probability 0.90 |
| `reward_cost_observed_landing` | The same rule, with each member landing at its target's Study 2 rate for the small probes A and B: Agave and Jito 1.00, Firedancer 0.94, the Harmonic builders 0.93 and 0.94, BAM 0.89. BAM's Study 2 losses were whole windows, so drawing them per member is pessimistic for BAM |
| `weak` | Half of each target's windows order by reward ÷ cost, the other half FIFO (L ≈ 0.75) |
| `cost_only` | Every target orders by requested cost alone, ties random. Every hypothesis is false; C5 sits exactly at its null, 0.5 |
| `control_fails` | Agave orders by cost alone, the other five by reward ÷ cost. The positive-control gate must withdraw the non-control targets |
| `additive` | Every target orders by reward − cost, a key outside the registered candidates. It ranks every registered pair as reward ÷ cost does |

## Results

**Identified, counting verdicts that assume selection** (`reward_cost_identified_assuming_selection`):

| Scenario | `7QQGNm3p` Agave | `HEL1USMZ` Jito-Solana | `EvnRmnMr` Firedancer | `DRpbCBMx` Agave + BAM | `Fd7btgyS` Agave + Harmonic | `JUPiTERr` Firedancer + Harmonic |
|---|---|---|---|---|---|---|
| `reward_cost` | **1.00** (0.96–1.00) | **1.00** (0.96–1.00) | **1.00** (0.96–1.00) | **1.00** (0.96–1.00) | **1.00** (0.96–1.00) | **1.00** (0.96–1.00) |
| `reward_cost_observed_landing` | **1.00** (0.96–1.00) | **1.00** (0.96–1.00) | **1.00** (0.96–1.00) | **1.00** (0.96–1.00) | **1.00** (0.96–1.00) | **1.00** (0.96–1.00) |
| `weak` | 0.24 (0.16–0.34) | 0.04 (0.01–0.10) | 0.15 (0.09–0.24) | 0.05 (0.02–0.11) | 0.04 (0.01–0.10) | 0.06 (0.02–0.13) |
| `cost_only` | **0.00** (0.00–0.04) | **0.00** (0.00–0.04) | **0.00** (0.00–0.04) | **0.00** (0.00–0.04) | **0.00** (0.00–0.04) | **0.00** (0.00–0.04) |
| `control_fails` | 0.00 (0.00–0.04) | 0.00 (0.00–0.04) | 1.00 (0.96–1.00) | 0.00 (0.00–0.04) | 0.00 (0.00–0.04) | 0.00 (0.00–0.04) |
| `additive` | 1.00 (0.96–1.00) | 1.00 (0.96–1.00) | 1.00 (0.96–1.00) | 1.00 (0.96–1.00) | 1.00 (0.96–1.00) | 1.00 (0.96–1.00) |

**Identified and robust to selection** (`reward_cost_identified`: no qualifier on the target or on either control):

| Scenario | `7QQGNm3p` | `HEL1USMZ` | `EvnRmnMr` | `DRpbCBMx` | `Fd7btgyS` | `JUPiTERr` |
|---|---|---|---|---|---|---|
| `reward_cost` | 0.39 (0.29–0.49) | 0.26 (0.18–0.36) | 0.39 (0.29–0.49) | 0.21 (0.13–0.30) | 0.18 (0.11–0.27) | 0.23 (0.15–0.32) |
| `reward_cost_observed_landing` | **0.97** (0.91–0.99) | **0.97** (0.91–0.99) | **0.97** (0.91–0.99) | 0.33 (0.24–0.43) | 0.82 (0.73–0.89) | 0.85 (0.76–0.91) |
| `cost_only` | 0.00 (0.00–0.04) | 0.00 (0.00–0.04) | 0.00 (0.00–0.04) | 0.00 (0.00–0.04) | 0.00 (0.00–0.04) | 0.00 (0.00–0.04) |
| `additive` | 0.39 (0.29–0.49) | 0.26 (0.18–0.36) | 0.39 (0.29–0.49) | 0.21 (0.13–0.30) | 0.18 (0.11–0.27) | 0.23 (0.15–0.32) |

The `weak` and `control_fails` rows are 0.00 here, except Firedancer in `control_fails` at 0.62 (0.52–0.72).

**Positive-control gate:**

| Scenario | Gate passed | Passed without the selection qualifier |
|---|---|---|
| `reward_cost` | 1.00 (0.96–1.00) | 0.39 (0.29–0.49) |
| `reward_cost_observed_landing` | 1.00 (0.96–1.00) | 0.97 (0.91–0.99) |
| `weak` | 0.08 (0.04–0.15) | 0.00 (0.00–0.04) |
| `cost_only` | 0.00 (0.00–0.04) | 0.00 (0.00–0.04) |
| `control_fails` | 0.00 (0.00–0.04) | 0.00 (0.00–0.04) |
| `additive` | 1.00 (0.96–1.00) | 0.39 (0.29–0.49) |

**Informative pairs:** a median of 24–25 per hypothesis at 0.90 landing (planned 32), and 24–30 at the observed
rates.

**False support under `cost_only`:** 1 of 100 campaigns supported any hypothesis (95 % CI up to 0.05). It was an H5,
which sits exactly at its null under cost alone, so no key was identified in any campaign.

## Reading

- **If the key is reward ÷ cost, Study 3 shows it for every target**, in every simulated campaign. At 0.90 landing
  per member, though, the verdict usually carries "(assumes selection)":
  - About one pair in five is then incomplete, and the worst-case bound at α/12 often fails for at least one of the
    four control hypotheses.
  - A control that passes only under the selection assumption puts the qualifier on every target's verdict (§6).
- **At the landing rates Study 2 observed, most verdicts are robust:** 0.97 for Agave, Jito-Solana and Firedancer,
  0.82–0.85 for the Harmonic builders. BAM's 0.33 reflects the pessimistic per-member draw; in Study 2 BAM had no
  incomplete pair at all.
- **If the key is cost alone, Study 3 never says reward ÷ cost.** C4 then goes against the hypothesis, and C5 sits at
  one half. False support stays at the nominal level that Holm guarantees.
- **The positive-control gate is strict.**
  - When Agave orders by cost alone, the four non-control targets are withdrawn. Firedancer, the other control, keeps
    its claim.
  - In the `weak` scenario, the gate withdraws most claims: a control that misses one hypothesis by chance withdraws
    the rest. Weak effects are not what Studies 1 and 2 saw, since their buffered and builder windows held the rule
    almost perfectly. If the effects are weak, Study 3 will say little; it will not say something wrong.
- **An additive key, reward − cost, is identified exactly as often as reward ÷ cost.** The two rank every probe pair of
  the three studies the same way, so the simulated campaigns come out identical. This is why the verdict reads
  "among the registered candidates" (PREREGISTRATION-3 §10).
- **What the simulation cannot show:** a scheduler unlike every model here, or dependence between windows. The exact
  binomial test assumes windows are independent. Each target's Study 3 estimates are reported with their intervals
  whatever the verdict.
