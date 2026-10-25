## Replication (hypothesis R)

| Target | Client | Ingress | Study 1 claim | Study 2 claim | Replicated |
|---|---|---|---|---|---|
| `7QQGNm3p` | Agave | direct | reward_cost | reward_cost | **yes** |
| `HEL1USMZ` | Jito-Solana | direct | reward_cost | reward_cost | **yes** |
| `EvnRmnMr` | Firedancer | direct | reward_cost | reward_cost | **yes** |
| `DRpbCBMx` | Agave + BAM | bam_node | reward_cost | reward_cost | **yes** |
| `Fd7btgyS` | Agave + Harmonic | harmonic_remote_tpu | reward_cost | reward_cost | **yes** |
| `JUPiTERr` | Firedancer + Harmonic | harmonic_remote_tpu | reward_cost | reward_cost | **yes** |

## Hypotheses H1–H3

| ID | Estimand | k/n | Estimate [95 % CI] | Holm p | Published claim | Per target |
|---|---|---|---|---|---|---|
| `H1-agave` | O(2 ms) < 0.5 | 7/35 | 0.20 [0.08, 0.37] | 0.00051 | **supported** | `7QQGNm3p` 7/35 |
| `H1-jito` | O(2 ms) < 0.5 | 6/29 | 0.21 [0.08, 0.40] | 0.0012 | **supported** | `HEL1USMZ` 6/29 |
| `H2-firedancer` | O(2 ms) > 0.5 | 31/31 | 1.00 [0.89, 1.00] | 0 | **supported** | `EvnRmnMr` 31/31 |
| `H2-firedancer-harmonic` | O(2 ms) > 0.5 | 32/33 | 0.97 [0.84, 1.00] | 0 | **supported** | `JUPiTERr` 32/33 |
| `H2-agave-harmonic` | O(2 ms) > 0.5 | 30/31 | 0.97 [0.83, 1.00] | 0 | **supported** | `Fd7btgyS` 30/31 |
| `H3-firedancer-ties` | E(10 ms) < 0.5 | 4/54 | 0.07 [0.02, 0.18] | 0 | **supported** | `9eGrDohd` 3/23, `EvnRmnMr` 1/31 |

## Sensitivity analyses

| Analysis | `H1-agave` | `H1-jito` | `H2-firedancer` | `H2-firedancer-harmonic` | `H2-agave-harmonic` | `H3-firedancer-ties` |
|---|---|---|---|---|---|---|
| censored | 7/35 supported | 6/29 supported | 31/31 supported | 32/33 supported | 30/31 supported | 4/54 supported |
| including transition ambiguous | 7/35 supported | 6/29 supported | 31/31 supported | 32/33 supported | 30/31 supported | 4/54 supported |
| achieved gap within 0.5ms | 4/23 supported | 2/23 supported | 20/20 supported | 22/23 supported | 19/20 supported | 3/34 supported |
| same slot | 7/35 supported | 6/28 supported | 31/31 supported | 32/33 supported | 30/31 supported | 4/54 supported |
| equal key both sent before first shred | 7/35 supported | 6/29 supported | 31/31 supported | 32/33 supported | 30/31 supported | 4/54 supported |

## Overtakes against a head start (exploratory; cells: hi landed first / races)

| Group | Δt 0 ms | Δt 2 ms | Δt 5 ms | Δt 10 ms | Δt 25 ms | Δt 50 ms | Horizon bracket | Equal key (first-sent first) |
|---|---|---|---|---|---|---|---|---|
| Agave `7QQGNm3p` | 10/12 | 7/35 | 0/15 | 0/12 | 0/12 | 0/13 | 0–2 ms | 10 ms: 23/35 |
| Agave + BAM `DRpbCBMx` | 3/3 | 14/14 | 4/6 | 5/5 | 3/6 | 0/5 | 25–50 ms | – |
| Firedancer `9eGrDohd` | – | – | – | – | – | – | – | 10 ms: 3/23 |
| Firedancer `EvnRmnMr` | 10/10 | 31/31 | 13/13 | 10/10 | 10/10 | 12/13 | > 50 ms | 10 ms: 1/31 |
| Agave + Harmonic `Fd7btgyS` | 10/10 | 30/31 | 11/13 | 7/12 | 1/10 | 0/11 | 10–25 ms | – |
| Firedancer + Harmonic `JUPiTERr` | 12/12 | 32/33 | 7/13 | 4/12 | 1/12 | 0/11 | 5–10 ms | – |
| Jito-Solana `HEL1USMZ` | 7/10 | 6/29 | 0/13 | 0/9 | 0/10 | 0/11 | 0–2 ms | 10 ms: 10/29 |
