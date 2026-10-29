"""Deterministic reference pricing.

The reference price is code, not LLM output: providers quote around it and
guardrails reject anything outside the band. The energy factor is derived from
real weather (Open-Meteo) but the dollars-per-kWh model is SIMULATED and
labelled as such in the UI.
"""
import math
from typing import Dict

# CPU-second estimates per job type. Deliberately conservative so quotes cover
# the real metered cost reported by the workers.
JOB_UNITS: Dict[str, int] = {
    "image_resize": 4,
    "matrix_multiply": 4,
}

REGION_MULTIPLIERS_BPS: Dict[str, int] = {
    "Region A (simulated)": 10_000,
    "Region B (simulated)": 9_200,
    "Region C (simulated)": 11_500,
}

DEFAULT_REGION = "Region A (simulated)"
DEFAULT_CPU_COST_MICRO = 250_000  # 0.25 USD per CPU-second of a burstable node


def region_multiplier_bps(region_label: str) -> int:
    return REGION_MULTIPLIERS_BPS.get(region_label, 10_000)


def energy_factor(temp_c: float, load_factor: float = 1.0) -> float:
    """SIMULATED price factor from real temperature: cooling cost above 20C."""
    cooling = max(0.0, temp_c - 20.0) * 0.012
    return round((1.0 + cooling) * max(0.85, min(1.25, load_factor)), 4)


def estimate_cpu_seconds(job_type: str, size: int) -> float:
    if job_type == "image_resize":
        # ~0.8 s of CPU per megapixel, floored so tiny jobs still meter.
        pixels = max(1, size)
        return max(0.2, round(pixels / 1_000_000 * 0.8, 4))
    if job_type == "matrix_multiply":
        # O(n^3) with a numpy fast path; empirical constant.
        return max(0.2, round((size ** 3) / 5e7, 4))
    return max(0.2, round(JOB_UNITS.get(job_type, 1) / 1000, 4))


def reference_price_micro(profile: dict, job_type: str, size: int,
                          energy: float = 1.0, quantity: int = 1) -> int:
    base_cost = int(profile.get("base_cost_micro", DEFAULT_CPU_COST_MICRO))
    cpu_seconds = estimate_cpu_seconds(job_type, size)
    multiplier = region_multiplier_bps(profile.get("region_label", DEFAULT_REGION)) / 10_000
    raw = base_cost * cpu_seconds * multiplier * energy
    # Add a 15% provider margin, floor at one micro per unit.
    price = int(math.ceil(raw * 1.15)) * max(1, quantity)
    return max(1, price)


def quote(profile: dict, job_type: str, size: int, energy: float = 1.0,
          quantity: int = 1) -> dict:
    cpu_seconds = estimate_cpu_seconds(job_type, size)
    price = reference_price_micro(profile, job_type, size, energy, quantity)
    return {
        "reference_price_micro": price,
        "estimated_cpu_seconds": cpu_seconds,
        "energy_factor": energy,
        "region_multiplier_bps": region_multiplier_bps(profile.get("region_label", DEFAULT_REGION)),
        "simulated_inputs": ["energy_factor", "region_multiplier"],
    }
