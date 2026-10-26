## Identification (Study 3 with Studies 1 and 2)

Positive-control gate: passed.

| Target | Client | Ingress | Study 1 | Study 2 | C4: Y before A | C5: hi before A | Verdict (PREREGISTRATION-3 §5) |
|---|---|---|---|---|---|---|---|
| `7QQGNm3p` | Agave | direct | reward_cost | reward_cost | supported | supported | **reward ÷ (cost + 1) identified among the registered candidates** |
| `HEL1USMZ` | Jito-Solana | direct | reward_cost | reward_cost | supported | supported | **reward ÷ (cost + 1) identified among the registered candidates** |
| `EvnRmnMr` | Firedancer | direct | reward_cost | reward_cost | supported | supported | **reward ÷ (cost + 1) identified among the registered candidates** |
| `DRpbCBMx` | Agave + BAM | bam_node | reward_cost | reward_cost | supported | supported | **reward ÷ (cost + 1) identified among the registered candidates** |
| `Fd7btgyS` | Agave + Harmonic | harmonic_remote_tpu | reward_cost | reward_cost | supported | supported | **reward ÷ (cost + 1) identified among the registered candidates** |
| `JUPiTERr` | Firedancer + Harmonic | harmonic_remote_tpu | reward_cost | reward_cost | supported | supported | **reward ÷ (cost + 1) identified among the registered candidates** |

## Hypotheses H4 and H5

| ID | Estimand | k/n | Estimate [95 % CI] | Holm p | Incomplete pairs | Windows evaluable / attempted | Published claim |
|---|---|---|---|---|---|---|---|
| `H4-7QQGNm3p` | P(Y before A) > 0.5 | 31/31 | 1.00 [0.89, 1.00] | < 10⁻⁶ | 0 | 31/32 | **supported** |
| `H5-7QQGNm3p` | P(hi before A) > 0.5 | 31/31 | 1.00 [0.89, 1.00] | < 10⁻⁶ | 0 | 31/32 | **supported** |
| `H4-HEL1USMZ` | P(Y before A) > 0.5 | 29/29 | 1.00 [0.88, 1.00] | < 10⁻⁶ | 0 | 29/32 | **supported** |
| `H5-HEL1USMZ` | P(hi before A) > 0.5 | 29/29 | 1.00 [0.88, 1.00] | < 10⁻⁶ | 0 | 29/32 | **supported** |
| `H4-EvnRmnMr` | P(Y before A) > 0.5 | 24/24 | 1.00 [0.86, 1.00] | < 10⁻⁶ | 0 | 24/32 | **supported** |
| `H5-EvnRmnMr` | P(hi before A) > 0.5 | 24/24 | 1.00 [0.86, 1.00] | < 10⁻⁶ | 0 | 24/32 | **supported** |
| `H4-DRpbCBMx` | P(Y before A) > 0.5 | 21/21 | 1.00 [0.84, 1.00] | 1e-06 | 3 | 24/32 | **supported** |
| `H5-DRpbCBMx` | P(hi before A) > 0.5 | 21/21 | 1.00 [0.84, 1.00] | 1e-06 | 3 | 24/32 | **supported** |
| `H4-Fd7btgyS` | P(Y before A) > 0.5 | 24/24 | 1.00 [0.86, 1.00] | < 10⁻⁶ | 0 | 24/32 | **supported** |
| `H5-Fd7btgyS` | P(hi before A) > 0.5 | 24/24 | 1.00 [0.86, 1.00] | < 10⁻⁶ | 0 | 24/32 | **supported** |
| `H4-JUPiTERr` | P(Y before A) > 0.5 | 30/30 | 1.00 [0.88, 1.00] | < 10⁻⁶ | 0 | 30/32 | **supported** |
| `H5-JUPiTERr` | P(hi before A) > 0.5 | 30/30 | 1.00 [0.88, 1.00] | < 10⁻⁶ | 0 | 30/32 | **supported** |

## Windows per target

| Target | Windows attempted | Evaluable | Excluded, by reason |
|---|---|---|---|
| `7QQGNm3p` | 32 | 31 | not_all_sent 1 |
| `DRpbCBMx` | 32 | 24 | not_all_sent 8 |
| `EvnRmnMr` | 32 | 24 | not_all_sent 8 |
| `Fd7btgyS` | 32 | 24 | not_all_sent 8 |
| `HEL1USMZ` | 32 | 29 | not_all_sent 3 |
| `JUPiTERr` | 32 | 30 | not_all_sent 2 |

## Sensitivity analyses

| Analysis | `H4-7QQGNm3p` | `H5-7QQGNm3p` | `H4-HEL1USMZ` | `H5-HEL1USMZ` | `H4-EvnRmnMr` | `H5-EvnRmnMr` | `H4-DRpbCBMx` | `H5-DRpbCBMx` | `H4-Fd7btgyS` | `H5-Fd7btgyS` | `H4-JUPiTERr` | `H5-JUPiTERr` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| censored | 31/31 supported | 31/31 supported | 29/29 supported | 29/29 supported | 24/24 supported | 24/24 supported | 21/21 supported | 21/21 supported | 24/24 supported | 24/24 supported | 30/30 supported | 30/30 supported |
| including transition ambiguous | 31/31 supported | 31/31 supported | 29/29 supported | 29/29 supported | 24/24 supported | 24/24 supported | 21/21 supported | 21/21 supported | 24/24 supported | 24/24 supported | 30/30 supported | 30/30 supported |
| same slot | 31/31 supported | 31/31 supported | 29/29 supported | 29/29 supported | 24/24 supported | 24/24 supported | 21/21 supported | 21/21 supported | 24/24 supported | 24/24 supported | 30/30 supported | 30/30 supported |

## Per-target diagnostics (descriptive)

| Target | Client | Ingress | Contrast | Group | Pairs | Evaluable pairs | x landed | A landed | Both landed | First sent first |
|---|---|---|---|---|---|---|---|---|---|---|
| `7QQGNm3p` | Agave | direct | C4 | confirmatory | 32 | 31 | Y 31/31 | A 31/31 | 31 | 15/31 |
| `7QQGNm3p` | Agave | direct | C5 | confirmatory | 32 | 31 | hi 31/31 | A 31/31 | 31 | 16/31 |
| `DRpbCBMx` | Agave + BAM | bam_node | C4 | confirmatory | 32 | 24 | Y 21/24 | A 21/24 | 21 | 11/21 |
| `DRpbCBMx` | Agave + BAM | bam_node | C5 | confirmatory | 32 | 24 | hi 21/24 | A 21/24 | 21 | 11/21 |
| `EvnRmnMr` | Firedancer | direct | C4 | confirmatory | 32 | 24 | Y 24/24 | A 24/24 | 24 | 13/24 |
| `EvnRmnMr` | Firedancer | direct | C5 | confirmatory | 32 | 24 | hi 24/24 | A 24/24 | 24 | 12/24 |
| `Fd7btgyS` | Agave + Harmonic | harmonic_remote_tpu | C4 | confirmatory | 32 | 24 | Y 24/24 | A 24/24 | 24 | 11/24 |
| `Fd7btgyS` | Agave + Harmonic | harmonic_remote_tpu | C5 | confirmatory | 32 | 24 | hi 24/24 | A 24/24 | 24 | 11/24 |
| `HEL1USMZ` | Jito-Solana | direct | C4 | confirmatory | 32 | 29 | Y 29/29 | A 29/29 | 29 | 15/29 |
| `HEL1USMZ` | Jito-Solana | direct | C5 | confirmatory | 32 | 29 | hi 29/29 | A 29/29 | 29 | 14/29 |
| `JUPiTERr` | Firedancer + Harmonic | harmonic_remote_tpu | C4 | confirmatory | 32 | 30 | Y 30/30 | A 30/30 | 30 | 14/30 |
| `JUPiTERr` | Firedancer + Harmonic | harmonic_remote_tpu | C5 | confirmatory | 32 | 30 | hi 30/30 | A 30/30 | 30 | 14/30 |
