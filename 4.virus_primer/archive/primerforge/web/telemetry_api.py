"""FastAPI Telemetry Ingestion API for clinical-grade laboratory curve syncing.

Implements:
  1. Second Derivative Maximum (SDM) Cq curve analyzer.
  2. Melt curve local maxima peak counter.
  3. POST /api/v1/telemetry/ingest REST endpoint.
  4. Automated EWC and Online Platt model refitting triggers.
"""

import math
from typing import Any, Dict, List, Optional, Tuple
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import numpy as np

from primerforge.biophysics import BiophysicsEngine, PrimerPair, PrimerSequence
from primerforge.ml_scorer import MLScorer
from primerforge.utils import setup_logger

logger = setup_logger("primerforge.telemetry_api")

app = FastAPI(
    title="PrimerForge Telemetry Sync API",
    description="Clinical-Grade Lab qPCR/Melt curve syncing & EWC continual calibration",
    version="0.3.0",
)

# Global lazy-initialized singletons
_BIOPHYS_ENGINE: Optional[BiophysicsEngine] = None
_ML_SCORER: Optional[MLScorer] = None


def get_biophys_engine() -> BiophysicsEngine:
    global _BIOPHYS_ENGINE
    if _BIOPHYS_ENGINE is None:
        _BIOPHYS_ENGINE = BiophysicsEngine()
    return _BIOPHYS_ENGINE


def get_ml_scorer() -> MLScorer:
    global _ML_SCORER
    if _ML_SCORER is None:
        _ML_SCORER = MLScorer()
    return _ML_SCORER


# ── Pydantic Request Models ────────────────────────────────────────────────


class TelemetryExperiment(BaseModel):
    forward_seq: str
    reverse_seq: str
    fluorescence_cycles: List[float]
    temperature_dissociation: Optional[List[float]] = None
    fluorescence_dissociation: Optional[List[float]] = None


class TelemetryBatchRequest(BaseModel):
    experiments: List[TelemetryExperiment]


# ── Signal Processing & Curve Analysis ─────────────────────────────────────


def analyze_qpcr_curve(
    cycles: List[float],
) -> Tuple[float, float, bool]:
    """Extracts quantification cycle (Cq) via Second Derivative Maximum (SDM).

    Args:
        cycles: List of raw fluorescence values (1 per cycle, e.g. length 40).

    Returns:
        Tuple[float, float, bool]: (Cq, max_first_derivative, is_success)
    """
    N = len(cycles)
    if N < 15:
        # Too short to compute background baseline or central differences
        return 40.0, 0.0, False

    f = np.array(cycles, dtype=np.float64)

    # 1. Baseline Subtraction (average of cycles 2 to 10)
    baseline_avg = float(np.mean(f[2:11]))
    baseline_std = float(np.std(f[2:11]))
    f_clean = f - baseline_avg

    # 2. Central Finite Differences for Derivatives
    # First derivative: d1[t] = (f[t+1] - f[t-1]) / 2
    d1 = np.zeros(N, dtype=np.float64)
    d1[1 : N - 1] = (f_clean[2:N] - f_clean[0 : N - 2]) / 2.0
    d1[0] = f_clean[1] - f_clean[0]
    d1[N - 1] = f_clean[N - 1] - f_clean[N - 2]

    # Second derivative: d2[t] = f[t+1] - 2*f[t] + f[t-1]
    d2 = np.zeros(N, dtype=np.float64)
    d2[1 : N - 1] = f_clean[2:N] - 2.0 * f_clean[1 : N - 1] + f_clean[0 : N - 2]
    d2[0] = d2[1]
    d2[N - 1] = d2[N - 2]

    # 3. Find Second Derivative Maximum (SDM) within amplification phase
    # Avoid early cycles to filter out baseline fluctuations
    amplification_d2 = d2[3 : N - 2]
    max_d2_idx = int(np.argmax(amplification_d2)) + 3
    max_d2_val = float(d2[max_d2_idx])

    max_d1_val = float(np.max(d1))

    # 4. Signal-to-Noise Ratio (SNR) and Viability Checks
    # Standard sigmoidal curves have a high derivative relative to baseline standard deviation
    noise_thresh = max(0.5, 3.0 * baseline_std)
    total_change = float(np.max(f_clean) - np.min(f_clean))

    is_success = False
    cq = 40.0

    if max_d2_val > noise_thresh and total_change > 5.0 and max_d1_val > 0.5:
        cq = float(max_d2_idx)
        if cq <= 35.0:
            is_success = True

    return cq, max_d1_val, is_success


def analyze_melt_curve(
    temps: List[float],
    fluor: List[float],
) -> int:
    """Estimates the number of melting peaks from a dissociation temperature curve.

    Args:
        temps: Temperature readings (5'->3' sorted list).
        fluor: Raw fluorescence readings at corresponding temperatures.

    Returns:
        int: Number of melting peaks (local maxima in negative derivative -dF/dT).
    """
    N = len(temps)
    if N < 5 or len(fluor) != N:
        return 1

    t_arr = np.array(temps, dtype=np.float64)
    f_arr = np.array(fluor, dtype=np.float64)

    # 1. Compute negative derivative -dF/dT
    # -dF/dT[i] = -(F[i+1] - F[i-1]) / (T[i+1] - T[i-1])
    neg_deriv = np.zeros(N, dtype=np.float64)
    neg_deriv[1 : N - 1] = -(f_arr[2:N] - f_arr[0 : N - 2]) / (
        t_arr[2:N] - t_arr[0 : N - 2] + 1e-8
    )
    neg_deriv[0] = neg_deriv[1]
    neg_deriv[N - 1] = neg_deriv[N - 2]

    # 2. Smooth negative derivative using a simple 3-point moving average
    smoothed = np.convolve(neg_deriv, np.ones(3) / 3.0, mode="same")

    # 3. Detect peaks (local maxima exceeding a noise prominence filter)
    peaks_count = 0
    max_peak_val = max(1e-5, float(np.max(smoothed)))
    prominence_threshold = 0.15 * max_peak_val

    for i in range(1, N - 1):
        val = smoothed[i]
        if val > smoothed[i - 1] and val > smoothed[i + 1]:
            if val > prominence_threshold:
                peaks_count += 1

    return max(1, peaks_count)


# ── FastAPI Routes ─────────────────────────────────────────────────────────


@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "PrimerForge Telemetry API"}


@app.post("/api/v1/telemetry/ingest")
def ingest_telemetry(payload: TelemetryBatchRequest) -> Dict[str, Any]:
    """Ingests, parses, and auto-calibrates the ensembled model from custom telemetry."""
    if not payload.experiments:
        raise HTTPException(
            status_code=400, detail="Request must contain at least 1 experiment."
        )

    biophys = get_biophys_engine()
    scorer = get_ml_scorer()

    results = []
    pairs_to_calibrate: List[PrimerPair] = []
    outcomes_to_calibrate: List[Dict[str, float]] = []

    for idx, exp in enumerate(payload.experiments):
        f_seq = exp.forward_seq.upper().strip()
        r_seq = exp.reverse_seq.upper().strip()

        # 1. Run digital signal processing algorithms
        cq, max_deriv, is_success = analyze_qpcr_curve(exp.fluorescence_cycles)

        melt_peaks_count = 1
        if (
            exp.temperature_dissociation is not None
            and exp.fluorescence_dissociation is not None
        ):
            melt_peaks_count = analyze_melt_curve(
                exp.temperature_dissociation, exp.fluorescence_dissociation
            )

        # 2. Assemble PrimerPair thermodynamics
        f_thermo = biophys.calculate_thermo_features(f_seq)
        f_sequence_obj = PrimerSequence(
            sequence=f_seq,
            start=0,
            length=len(f_seq),
            tm=f_thermo["tm"],
            gc_percent=sum(1 for c in f_seq if c in "GC") * 100.0 / len(f_seq),
            hairpin_dg=f_thermo["hairpin_dg"],
            homodimer_dg=f_thermo["homodimer_dg"],
            penalty=0.0,
        )

        r_thermo = biophys.calculate_thermo_features(r_seq)
        r_sequence_obj = PrimerSequence(
            sequence=r_seq,
            start=0,
            length=len(r_seq),
            tm=r_thermo["tm"],
            gc_percent=sum(1 for c in r_seq if c in "GC") * 100.0 / len(r_seq),
            hairpin_dg=r_thermo["hairpin_dg"],
            homodimer_dg=r_thermo["homodimer_dg"],
            penalty=0.0,
        )

        pair = PrimerPair(
            forward=f_sequence_obj,
            reverse=r_sequence_obj,
            product_size=100,  # Proxy average product size
            cross_dimer_dg=biophys.calculate_heterodimer_dg(f_seq, r_seq),
            penalty=0.0,
        )

        pairs_to_calibrate.append(pair)

        empirical_success = 0.95 if is_success else 0.05
        outcome = {
            "success": empirical_success,
            "ct_value": cq,
            "endpoint_yield": max(0.0, float(max(exp.fluorescence_cycles) - min(exp.fluorescence_cycles))),
            "melt_peaks": float(melt_peaks_count),
        }
        outcomes_to_calibrate.append(outcome)

        results.append(
            {
                "experiment_index": idx,
                "forward": f_seq,
                "reverse": r_seq,
                "Cq": round(cq, 2),
                "melt_peaks": melt_peaks_count,
                "empirical_success": is_success,
            }
        )

    # 3. Trigger EWC Continual Learning and Recalibration
    logger.info(
        f"Triggering automated EWC calibration on N={len(pairs_to_calibrate)} new outcomes..."
    )
    try:
        # Perform 5 epochs of regularized continual learning
        losses_report = scorer.update_from_new_data(
            pairs_to_calibrate, outcomes_to_calibrate, epochs=5
        )
        logger.info("EWC parameters updated successfully.")

        # Serialize and save ensembled calibration parameters back to models/
        scorer.save()
        logger.info("Ensembled calibration state saved successfully.")
    except Exception as e:
        logger.error(f"Continual learning refitting failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Continual learning calibration failed: {e}"
        )

    return {
        "status": "success",
        "processed": len(payload.experiments),
        "results": results,
        "calibration_metrics": {
            "new_losses": [float(l) for l in losses_report.get("new_losses", [])],
            "ewc_penalties": [
                float(l) for l in losses_report.get("ewc_penalties", [])
            ],
            "replay_losses": [
                float(l) for l in losses_report.get("replay_losses", [])
            ],
            "platt_a": round(float(scorer.platt_a), 4),
            "platt_b": round(float(scorer.platt_b), 4),
        },
    }
