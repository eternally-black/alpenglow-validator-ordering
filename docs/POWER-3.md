# Study 3 — operating characteristics (before freezing)

**What this checks.** Study 3 asks per core target whether the reward enters the ordering key. It runs twelve
hypotheses, H4 and H5 for each of six targets. A target's key is identified as reward ÷ (cost + 1) when both are
supported and its Study 1 and Study 2 claims are `reward_cost` (PREREGISTRATION-3 §5). This page answers two questions:
- How often is the key identified when it really is reward ÷ cost?
- How often when the scheduler orders by cost alone?

**Method.**
- **Design:** the Study 3 design to be frozen (`design/design-study3.jsonl`): 32 windows per target, one C4 and one C5
  pair in each.
- **Simulation:** `itb_analysis.sim` with schedulers whose key is known. Each member lands with probability 0.9, and
  Study 1's observation failures are injected (lost streams, unproduced blocks, gossip changes).
- **Analysis:** `itb_analysis.study3`, the code the live data will go through, including window eligibility, Holm over
  twelve, the selection bound and the positive-control gate.
- **Replicates:** 100 per scenario.

```bash
PYTHONPATH=analysis python scripts/oc_study3.py --reps 100   # writes data/derived/oc-study3.{json,md}
```

## Scenarios

| Scenario | What is true |
|---|---|
| `reward_cost` | Every target orders by reward ÷ (cost + 1): the truth that Studies 1 and 2 point to |
| `weak` | Half of each target's windows order by reward ÷ cost, the other half FIFO (L ≈ 0.75) |
| `cost_only` | Every target orders by requested cost alone, ties random. Every hypothesis is false; C5 sits exactly at its null, 0.5 |
| `control_fails` | Agave orders by cost alone, the other five by reward ÷ cost. The positive-control gate must withdraw the non-control targets |

## Results: share of campaigns in which each target's key is identified as reward ÷ (cost + 1)

| Scenario | `7QQGNm3p` Agave | `HEL1USMZ` Jito-Solana | `EvnRmnMr` Firedancer | `DRpbCBMx` Agave + BAM | `Fd7btgyS` Agave + Harmonic | `JUPiTERr` Firedancer + Harmonic |
|---|---|---|---|---|---|---|
| `reward_cost` | **1.00** | **1.00** | **1.00** | **1.00** | **1.00** | **1.00** |
| `weak` | 0.24 | 0.05 | 0.17 | 0.04 | 0.03 | 0.06 |
| `cost_only` | **0.00** | **0.00** | **0.00** | **0.00** | **0.00** | **0.00** |
| `control_fails` | 0.00 | 0.00 | 1.00 | 0.00 | 0.00 | 0.00 |

**Informative pairs:** a median of 22–25 per hypothesis (planned 32), after the simulated 10 % loss per member and the
observation failures.

**False support under `cost_only`:** 1 of 100 campaigns supported any hypothesis (95 % CI up to 0.05). It was an H5
exactly at its null, so the key was identified in none.

## Reading

- **If the key is reward ÷ cost, Study 3 shows it for every target**, in every simulated campaign.
- **If the key is cost alone, Study 3 never says reward ÷ cost.** C4 then goes against the hypothesis, and C5 sits at
  one half. False support stays at the nominal level that Holm guarantees.
- **The positive-control gate is strict.**
  - When Agave orders by cost alone, the four non-control targets are withdrawn. Firedancer, the other control, keeps
    its claim.
  - In the `weak` scenario, the gate also withdraws most claims: a control that misses one hypothesis by chance
    withdraws the rest. Weak effects are not what Studies 1 and 2 saw, since their buffered and builder windows held
    the rule almost perfectly. If the effects are weak, Study 3 will say little; it will not say something wrong.
- **What the simulation cannot show:** a scheduler unlike every model here. Each target's Study 3 estimates are
  reported with their intervals whatever the verdict.
