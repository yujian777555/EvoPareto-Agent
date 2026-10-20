"""Offline power / exact-test limits for RQ3 multi-seed design (no model calls).

Deterministic. Used to generate numbers quoted in RQ3_MULTI_SEED_DESIGN.md.
"""
from __future__ import annotations

import math
from itertools import combinations


def exact_wilcoxon_min_two_sided_p(n: int) -> float:
    """Smallest possible two-sided exact Wilcoxon signed-rank p-value at n.

    All |d| distinct and all same sign -> one tail mass = 1/2^n.
    Two-sided p_min = 2/2^n (capped at 1).
    """
    if n <= 0:
        return 1.0
    return min(1.0, 2.0 / (2.0 ** n))


def can_reject_alpha05_exact_two_sided(n: int, alpha: float = 0.05) -> bool:
    return exact_wilcoxon_min_two_sided_p(n) <= alpha + 1e-15


def normal_approx_R(mu_d: float, sigma_d: float, alpha: float = 0.05, power: float = 0.80) -> float:
    """R = ((z_{1-a/2}+z_{1-b}) * sigma / mu)^2 — paired-mean approximation."""
    # z values for two-sided alpha=0.05, power=0.80
    z_a = 1.959963984540054 if abs(alpha - 0.05) < 1e-12 else 1.96
    z_b = 0.8416212335729143 if abs(power - 0.80) < 1e-12 else 0.84
    if abs(mu_d) < 1e-15:
        return float("inf")
    return ((z_a + z_b) * sigma_d / mu_d) ** 2


def binom_sign_test_min_two_sided_p(n: int) -> float:
    """Sign test: min two-sided p = 2/2^n (all same direction)."""
    return min(1.0, 2.0 / (2.0 ** n))


def main() -> int:
    lines = []
    lines.append("Exact two-sided Wilcoxon signed-rank minimum p-value")
    lines.append("R  p_min_two_sided  reject_at_0.05")
    for n in range(1, 16):
        p = exact_wilcoxon_min_two_sided_p(n)
        lines.append("%2d  %.6f  %s" % (n, p, "YES" if can_reject_alpha05_exact_two_sided(n) else "NO"))

    lines.append("")
    lines.append("Sign test min two-sided p")
    for n in range(1, 16):
        p = binom_sign_test_min_two_sided_p(n)
        lines.append("%2d  %.6f  %s" % (n, p, "YES" if p <= 0.05 else "NO"))

    lines.append("")
    lines.append("Normal-approx R for paired seed differences (alpha=0.05 two-sided, power=0.80)")
    lines.append("mu_d  sigma_d  R_approx")
    for mu, sig in [(0.02, 0.04), (0.05, 0.06), (0.05, 0.04), (0.08, 0.05), (0.10, 0.06)]:
        r = normal_approx_R(mu, sig)
        lines.append("%.2f  %.2f  %.1f" % (mu, sig, r))

    text = "\n".join(lines)
    print(text)
    # also write to docs as a small appendix
    from pathlib import Path
    Path("docs/level3_pilot_r4_design/RQ3_POWER_TABLES.txt").write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
