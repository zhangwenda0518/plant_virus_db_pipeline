"""Command Line Interface (CLI) for PrimerForge.

Integrates the BiophysicsEngine, SpecificityEngine, and MLScorer pipelines to generate,
check specificity, filter variants, run empirical GBDT scoring, and print ranked primer pairs.
"""

import os
import click
from typing import Any, Dict, List

from primerforge.biophysics import BiophysicsEngine, PrimerPair
from primerforge.specificity import SpecificityEngine, VariantAwareFilter
from primerforge.ml_scorer import MLScorer
from primerforge.optimizer import MultiplexOptimizer, TiledAmpliconRouter
from primerforge.utils import setup_logger

logger = setup_logger("primerforge.cli")


@click.group()
@click.version_option(package_name="primerforge")
def main() -> None:
    """PrimerForge: Pangenome-Aware & Machine-Learning PCR Primer Design Platform.

    Provides high-reliability primer design by combining classic thermodynamics
    with machine learning and variant filtering.
    """
    pass


@main.command(name="design")
@click.option(
    "--target",
    "-t",
    required=True,
    type=str,
    help="Target DNA template sequence (5' to 3') or path to a FASTA file.",
)
@click.option(
    "--opt-tm",
    type=float,
    default=60.0,
    help="Optimal melting temperature (Tm) in Celsius.",
)
@click.option(
    "--min-tm",
    type=float,
    default=57.0,
    help="Minimum allowed melting temperature (Tm) in Celsius.",
)
@click.option(
    "--max-tm",
    type=float,
    default=63.0,
    help="Maximum allowed melting temperature (Tm) in Celsius.",
)
@click.option(
    "--opt-size",
    type=int,
    default=20,
    help="Optimal primer length in nucleotides.",
)
@click.option(
    "--min-size",
    type=int,
    default=18,
    help="Minimum allowed primer length in nucleotides.",
)
@click.option(
    "--max-size",
    type=int,
    default=24,
    help="Maximum allowed primer length in nucleotides.",
)
@click.option(
    "--pangenome",
    "-p",
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Path to pangenome FASTA index for specificity checking.",
)
@click.option(
    "--vcf",
    "-v",
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Path to VCF file containing population variation coordinates.",
)
@click.option(
    "--maf",
    type=float,
    default=0.01,
    help="Minor allele frequency (MAF) threshold for variant filtering.",
)
@click.option(
    "--num-return",
    "-n",
    type=int,
    default=10,
    help="Number of top primer pairs to print.",
)
@click.option(
    "--multiplex",
    "-m",
    is_flag=True,
    help="Enable multiplex design optimization mode.",
)
@click.option(
    "--tiled",
    is_flag=True,
    help="Enable dynamic tiled-amplicon router mode for long templates.",
)
@click.option(
    "--retrain",
    "-r",
    is_flag=True,
    help="Force complete curation of the 30k-pair database and retrain the LightGBM success model.",
)
@click.option(
    "--retrain-hybrid",
    is_flag=True,
    help="Force full curation of the 100k-pair hybrid database and retrain the premium hybrid LightGBM success model.",
)
@click.option(
    "--retrain-ultra",
    is_flag=True,
    help="Force full curation of the 500k-pair ultra-scale hybrid database and retrain the ensembled LightGBM success models.",
)
@click.option(
    "--model-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default="models",
    help="Path to custom directory containing serialized ensembled model files.",
)
@click.option(
    "--use-real-data",
    is_flag=True,
    default=False,
    help="Retrain the ML success model using real public data before designing primers.",
)
@click.option(
    "--retrain-real",
    is_flag=True,
    default=False,
    help="Trigger curation of real public databases and retrain the LightGBM models (or ultra ensemble).",
)
def design(
    target: str,
    opt_tm: float,
    min_tm: float,
    max_tm: float,
    opt_size: int,
    min_size: int,
    max_size: int,
    pangenome: str | None,
    vcf: str | None,
    maf: float,
    num_return: int,
    multiplex: bool,
    tiled: bool,
    retrain: bool,
    retrain_hybrid: bool,
    retrain_ultra: bool,
    model_dir: str,
    use_real_data: bool,
    retrain_real: bool,
) -> None:
    """Executes the PrimerForge primer design pipeline on a target locus."""
    logger.info("Initializing PrimerForge Design Engine...")

    # Load target sequence from path if it is a FASTA file
    target_sequence = target
    if os.path.exists(target):
        logger.info(f"Loading target sequence from FASTA: {target}...")
        try:
            with open(target, "r") as f:
                lines = [line.strip() for line in f if not line.startswith(">")]
                target_sequence = "".join(lines).upper()
        except Exception as e:
            logger.error(f"Failed to read target FASTA: {e}")
            raise click.ClickException(f"Invalid FASTA file: {e}")

    logger.info(
        f"Target Template: {target_sequence[:30]}..."
        if len(target_sequence) > 30
        else f"Target Template: {target_sequence}"
    )

    # 1. Biophysical Candidate Generation
    biophys_engine = BiophysicsEngine(
        opt_tm=opt_tm,
        min_tm=min_tm,
        max_tm=max_tm,
        opt_size=opt_size,
        min_size=min_size,
        max_size=max_size,
    )

    # 2. Setup Machine Learning Scorer
    ml_scorer = MLScorer(
        model_path=os.path.join(model_dir, "primerforge_lightgbm.model")
    )
    if retrain_ultra:
        click.echo(
            "Force retraining ultra model: Curation pipeline compiling ultra-scale ensembled databases..."
        )
        ml_scorer.train_ultra_hybrid_model(target_size=2000, n_samples=2000)
        click.echo("GBDT ensembled ultra model retraining completed successfully!")
    elif retrain_hybrid:
        click.echo(
            "Force retraining hybrid model: Curation pipeline compiling real-world + synthetic databases..."
        )
        ml_scorer.train_hybrid_model(target_size=2000, n_samples=2000)
        click.echo("GBDT hybrid model retraining completed successfully!")
    elif retrain:
        click.echo(
            "Force retraining: Curation pipeline compiling the 30k-pair database..."
        )
        ml_scorer.train_full_model()
        click.echo("GBDT model retraining completed successfully!")
    elif retrain_real:
        logger.info("Real public data retraining triggered via --retrain-real")
        click.echo("Real public data retraining triggered via --retrain-real")
        ml_scorer.retrain_with_public_real_data()
        click.echo("Retraining using real public data completed successfully!")
    elif use_real_data:
        click.echo("Retraining model using real public data...")
        ml_scorer.retrain_with_public_real_data()
        click.echo("Retraining using real public data completed successfully!")

    if tiled:
        click.echo("Running Dynamic Programming Tiled-Amplicon Router...")
        router = TiledAmpliconRouter(biophys_engine, ml_scorer)
        selected_tiles = router.design_tiled_amplicons(
            target_sequence, tile_size=400, overlap=50
        )

        if not selected_tiles:
            click.echo(
                "Error: No overlapping tiled amplicons could be designed matching your specifications."
            )
            return

        if multiplex:
            click.echo(
                "Running ILP multiplex optimization on tiled candidate amplicons..."
            )
            optimizer = MultiplexOptimizer(biophys_engine)
            # Assemble the optimal compatible subset up to num_return-plex
            final_tiles, obj_val = optimizer.optimize_panel(
                selected_tiles, max_plex=num_return, delta_g_threshold=-4.5
            )
        else:
            # If not multiplex, keep up to num_return tiles
            final_tiles = selected_tiles[:num_return]
            obj_val = sum(item["predicted_success"] for item in final_tiles)

        click.echo("\n" + "=" * 80)
        if multiplex:
            click.echo("          PRIMERFORGE OPTIMIZED MULTIPLEX TILED AMPLICON PANEL")
        else:
            click.echo("               PRIMERFORGE OPTIMIZED TILED AMPLICON PANEL")
        click.echo("=" * 80)
        click.echo(
            f"  Reference Sequence Length: {len(target_sequence)}bp | Selected Tiles: {len(final_tiles)}"
        )
        click.echo(f"  Panel Objective Value: {obj_val:.2f}")
        click.echo("=" * 80)

        for r_idx, item in enumerate(final_tiles, 1):
            pair = item["pair"]
            success_pct = f"{item['predicted_success'] * 100:.1f}%"
            click.echo(
                f"\n[Tile Set {r_idx}] Success Probability: {success_pct} | Range: {item['abs_start']}-{item['abs_end']}bp"
            )
            click.echo(
                f"  Forward: {pair.forward.sequence} (Tm={pair.forward.tm:.1f}°C, GC={pair.forward.gc_percent:.1f}%)"
            )
            click.echo(
                f"  Reverse: {pair.reverse.sequence} (Tm={pair.reverse.tm:.1f}°C, GC={pair.reverse.gc_percent:.1f}%)"
            )
            click.echo(
                f"  Product Size: {pair.product_size}bp | Cross Dimer: {pair.cross_dimer_dg:.2f} kcal/mol"
            )
        click.echo("=" * 80 + "\n")
        return

    try:
        candidates = biophys_engine.generate_candidates(
            target_sequence, num_return=max(50, num_return * 5)
        )
    except Exception as e:
        raise click.ClickException(str(e))

    if not candidates:
        click.echo(
            "Error: No thermodynamic primer candidates found matching your specifications."
        )
        return

    # 2. Specificity and Variation Check Setup
    spec_engine = None
    var_filter = None

    if pangenome:
        spec_engine = SpecificityEngine()
        try:
            spec_engine.index_pangenome(pangenome)
        except Exception as e:
            raise click.ClickException(f"Failed to index pangenome: {e}")

        if vcf:
            var_filter = VariantAwareFilter()
            try:
                var_filter.load_variants(vcf)
            except Exception as e:
                raise click.ClickException(f"Failed to load VCF: {e}")

    # 3. Instantiate Machine Learning Scorer (already initialized above)

    # 4. Pipeline Run and Multi-Dimensional Evaluation
    evaluated_pairs: List[Dict[str, Any]] = []

    for idx, pair in enumerate(candidates):
        off_target_f = 0
        off_target_r = 0
        variant_penalty = 0.0
        is_valid = True

        min_var_dist_f = 20.0
        min_var_dist_r = 20.0
        max_var_maf_f = 0.0
        max_var_maf_r = 0.0

        if spec_engine:
            # Map forward and reverse primers against the reference
            hits_f = spec_engine.check_specificity(pair.forward.sequence)
            hits_r = spec_engine.check_specificity(pair.reverse.sequence)

            # Count off-targets (any hit outside the primary target locus)
            off_target_f = max(0, len(hits_f) - 1)
            off_target_r = max(0, len(hits_r) - 1)

            # Variant checks: scan coordinate hits and apply penalty
            if var_filter:
                for hit in hits_f:
                    penalty, valid = var_filter.evaluate_primer(
                        primer_seq=pair.forward.sequence,
                        start_pos=hit.start,
                        strand=hit.strand,
                        maf_threshold=maf,
                    )
                    variant_penalty += penalty
                    if not valid:
                        is_valid = False

                    # Extract variant metadata for GBDT feature vector
                    for var in var_filter.variants:
                        if (
                            hit.start
                            <= var.pos
                            <= hit.start + len(pair.forward.sequence)
                        ):
                            if var.maf >= maf:
                                dist = (
                                    (hit.start + len(pair.forward.sequence) - var.pos)
                                    if hit.strand == 1
                                    else (var.pos - hit.start)
                                )
                                if dist < min_var_dist_f:
                                    min_var_dist_f = float(dist)
                                if var.maf > max_var_maf_f:
                                    max_var_maf_f = var.maf

                for hit in hits_r:
                    penalty, valid = var_filter.evaluate_primer(
                        primer_seq=pair.reverse.sequence,
                        start_pos=hit.start,
                        strand=hit.strand,
                        maf_threshold=maf,
                    )
                    variant_penalty += penalty
                    if not valid:
                        is_valid = False

                    for var in var_filter.variants:
                        if (
                            hit.start
                            <= var.pos
                            <= hit.start + len(pair.reverse.sequence)
                        ):
                            if var.maf >= maf:
                                dist = (
                                    (var.pos - hit.start)
                                    if hit.strand == -1
                                    else (
                                        hit.start + len(pair.reverse.sequence) - var.pos
                                    )
                                )
                                if dist < min_var_dist_r:
                                    min_var_dist_r = float(dist)
                                if var.maf > max_var_maf_r:
                                    max_var_maf_r = var.maf

        spec_metadata = {
            "f_off_targets": off_target_f,
            "r_off_targets": off_target_r,
            "f_var_dist": min_var_dist_f,
            "r_var_dist": min_var_dist_r,
            "f_var_maf": max_var_maf_f,
            "r_var_maf": max_var_maf_r,
        }

        # Predict PCR success score using trained LightGBM booster
        predicted_success = ml_scorer.predict_success(pair, spec_metadata)
        total_penalty = (
            pair.penalty + (off_target_f + off_target_r) * 10.0 + variant_penalty
        )

        evaluated_pairs.append(
            {
                "pair": pair,
                "off_targets": off_target_f + off_target_r,
                "variant_penalty": variant_penalty,
                "is_valid": is_valid,
                "total_penalty": total_penalty,
                "predicted_success": predicted_success,
            }
        )

    # 5. Sort and Filter Output Candidates
    ranked_pairs = sorted(
        evaluated_pairs,
        key=lambda x: (not x["is_valid"], -x["predicted_success"], x["total_penalty"]),
    )

    if multiplex:
        click.echo("Running Integer Linear Programming (ILP) multiplex optimization...")
        optimizer = MultiplexOptimizer(biophys_engine)
        selected_pairs, obj_val = optimizer.optimize_panel(
            ranked_pairs, max_plex=num_return, delta_g_threshold=-4.5
        )

        click.echo("\n" + "=" * 80)
        click.echo("               PRIMERFORGE OPTIMIZED MULTIPLEX PANEL RESULTS")
        click.echo("=" * 80)
        click.echo(
            f"  Target Plex Limit: {num_return}-plex | Selected Compatible Loci: {len(selected_pairs)}"
        )
        click.echo(f"  Multiplex Panel Objective Value: {obj_val:.2f}")
        click.echo("=" * 80)

        for r_idx, item in enumerate(selected_pairs, 1):
            pair = item["pair"]
            success_pct = f"{item['predicted_success'] * 100:.1f}%"
            click.echo(
                f"\n[Multiplex Set {r_idx}] Success Probability: {success_pct} | Locus ID: {item.get('target_id')}"
            )
            click.echo(
                f"  Forward: {pair.forward.sequence} (Tm={pair.forward.tm:.1f}°C, GC={pair.forward.gc_percent:.1f}%)"
            )
            click.echo(
                f"  Reverse: {pair.reverse.sequence} (Tm={pair.reverse.tm:.1f}°C, GC={pair.reverse.gc_percent:.1f}%)"
            )
            click.echo(
                f"  Product Size: {pair.product_size}bp | Cross Dimer: {pair.cross_dimer_dg:.2f} kcal/mol"
            )
            click.echo(
                f"  Metrics: Off-Targets={item['off_targets']} | Base Penalty={pair.penalty:.2f}"
            )
        click.echo("=" * 80 + "\n")
    else:
        # Print Top Single-Locus Results
        click.echo("\n" + "=" * 80)
        click.echo("                   PRIMERFORGE OPTIMIZED DESIGN RESULTS")
        click.echo("=" * 80)

        top_n = ranked_pairs[:num_return]
        for r_idx, item in enumerate(top_n, 1):
            pair = item["pair"]
            valid_status = "PASS" if item["is_valid"] else "FAIL (3' SNP)"
            success_pct = f"{item['predicted_success'] * 100:.1f}%"

            click.echo(
                f"\n[Rank {r_idx}] Success Probability: {success_pct} | Status: {valid_status}"
            )
            click.echo(
                f"  Forward: {pair.forward.sequence} (Tm={pair.forward.tm:.1f}°C, GC={pair.forward.gc_percent:.1f}%)"
            )
            click.echo(
                f"  Reverse: {pair.reverse.sequence} (Tm={pair.reverse.tm:.1f}°C, GC={pair.reverse.gc_percent:.1f}%)"
            )
            click.echo(
                f"  Product Size: {pair.product_size}bp | Cross Dimer: {pair.cross_dimer_dg:.2f} kcal/mol"
            )
            click.echo(
                f"  Metrics: Off-Targets={item['off_targets']} | Variant Penalty={item['variant_penalty']:.1f} | Base Penalty={pair.penalty:.2f}"
            )

        click.echo("=" * 80 + "\n")


@main.command(name="active-learn")
@click.option(
    "--batch-size",
    "-b",
    type=int,
    default=15,
    help="Number of query samples per iteration.",
)
@click.option(
    "--iterations",
    "-i",
    type=int,
    default=5,
    help="Number of active learning loops.",
)
@click.option(
    "--strategy",
    "-s",
    type=click.Choice(["random", "entropy", "epistemic", "aleatoric", "hybrid"]),
    default="hybrid",
    help="Acquisition function strategy to evaluate.",
)
@click.option(
    "--out-plot",
    type=str,
    default="plots/active_learning_comparison.png",
    help="Path to save the comparative learning curves plot.",
)
def active_learn(
    batch_size: int,
    iterations: int,
    strategy: str,
    out_plot: str,
) -> None:
    """Runs a simulated closed-loop active learning cycle and compares performance."""
    click.echo(f"Initializing Active Learning Comparison Experiment...")
    click.echo(
        f"  Strategy: {strategy} vs. random | Batch Size: {batch_size} | Iterations: {iterations}"
    )

    import random
    import numpy as np
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from primerforge.active_learning import BiophysicalOracle, ActiveLearningEngine
    from primerforge.biophysics import BiophysicsEngine
    from primerforge.ml_scorer import MLScorer

    # 1. Generate realistic target template sequence
    random.seed(42)
    np.random.seed(42)
    bases = ["A", "T", "G", "C"]
    target_seq = "".join(
        random.choices(bases, weights=[0.25, 0.25, 0.25, 0.25], k=1200)
    )

    # 2. Design candidate primer pairs
    biophys_engine = BiophysicsEngine(
        min_tm=54.0, max_tm=66.0, min_size=18, max_size=25
    )
    candidates = biophys_engine.generate_candidates(target_seq, num_return=300)

    if len(candidates) < 100:
        click.echo(
            "Error: Could not generate enough candidate primers for active learning simulation."
        )
        return

    click.echo(f"Generated {len(candidates)} biophysical candidate primer pairs.")

    # 3. Create spec metadata pool
    spec_pool = []
    for _ in range(len(candidates)):
        spec_pool.append(
            {
                "f_off_targets": float(
                    np.random.choice([0, 1, 2], p=[0.8, 0.15, 0.05])
                ),
                "r_off_targets": float(
                    np.random.choice([0, 1, 2], p=[0.8, 0.15, 0.05])
                ),
                "f_var_dist": float(
                    np.random.choice([20.0, 1.0, 3.0, 8.0], p=[0.7, 0.1, 0.1, 0.1])
                ),
                "r_var_dist": float(
                    np.random.choice([20.0, 1.0, 3.0, 8.0], p=[0.7, 0.1, 0.1, 0.1])
                ),
                "f_var_maf": float(np.random.choice([0.0, 0.05, 0.2, 0.8])),
                "r_var_maf": float(np.random.choice([0.0, 0.05, 0.2, 0.8])),
            }
        )

    # 4. Instantiate oracle
    oracle = BiophysicalOracle(noise_std=0.05)

    # 5. Partition candidate pool:
    #   - 50 samples for validation pool (labeled)
    #   - 20 samples for initial seed pool (labeled)
    #   - 230 samples for unlabeled selection pool
    val_candidates = candidates[:50]
    val_specs = spec_pool[:50]
    val_set = []
    for pair, spec in zip(val_candidates, val_specs):
        label = oracle.evaluate(pair, spec, deterministic=True)
        val_set.append((pair, spec, label))

    seed_candidates = candidates[50:70]
    seed_specs = spec_pool[50:70]
    seed_set = []
    for pair, spec in zip(seed_candidates, seed_specs):
        label = oracle.evaluate(pair, spec, deterministic=True)
        seed_set.append((pair, spec, label))

    al_pool_candidates = candidates[70:]
    al_pool_specs = spec_pool[70:]
    unlabeled_pool = list(zip(al_pool_candidates, al_pool_specs))

    # Helper function to compute validation ROC AUC using pure NumPy
    def eval_roc_auc(scorer_instance, validation_dataset) -> float:
        y_true = []
        y_scores = []
        for pair, spec, label in validation_dataset:
            y_true.append(label)
            y_scores.append(scorer_instance.predict_success(pair, spec))

        y_true = np.array(y_true)
        y_scores = np.array(y_scores)

        if len(np.unique(y_true)) < 2:
            return 0.5

        # Compute AUC using pure NumPy rank sums
        desc_score_indices = np.argsort(y_scores)[::-1]
        y_true_sorted = y_true[desc_score_indices]

        tps = np.cumsum(y_true_sorted)
        fps = 1 + np.arange(len(y_true_sorted)) - tps

        tpr = tps / tps[-1]
        fpr = fps / fps[-1]

        # Trapezoid integration
        try:
            return float(np.trapezoid(tpr, fpr))
        except AttributeError:
            return float(np.trapz(tpr, fpr))

    strategies_to_test = [strategy, "random"]
    histories = {}

    for strat in strategies_to_test:
        click.echo(f"\nEvaluating Active Learning Strategy: '{strat}'...")
        # Create a fresh temporary scorer to prevent overwriting main models
        tmp_model_path = f"models/tmp_al_{strat}.model"
        scorer_tmp = MLScorer(model_path=tmp_model_path)

        # Reset engine and seeds
        engine = ActiveLearningEngine(scorer_tmp, oracle)
        engine.load_initial_labeled_data(list(seed_set))
        engine.load_unlabeled_pool(list(unlabeled_pool))

        # Initial retrain to establish baseline
        engine.retrain_ensemble()
        baseline_auc = eval_roc_auc(scorer_tmp, val_set)
        click.echo(
            f"  Baseline (Seeds={len(seed_set)}) | Val ROC AUC: {baseline_auc:.4f}"
        )

        auc_history = [baseline_auc]

        # Active Learning iterations loop
        for itr in range(iterations):
            engine.query_and_label_next_batch(
                batch_size=batch_size, strategy=strat, deterministic=True
            )
            engine.retrain_ensemble()
            auc = eval_roc_auc(scorer_tmp, val_set)
            click.echo(
                f"  Iteration {itr+1}/{iterations} (Pool size={len(engine.labeled_pool)}) | Val ROC AUC: {auc:.4f}"
            )
            auc_history.append(auc)

        histories[strat] = auc_history

        # Cleanup temp model files
        if os.path.exists(tmp_model_path):
            os.remove(tmp_model_path)

    # 6. Plot the comparison curves
    os.makedirs(os.path.dirname(out_plot) or "plots", exist_ok=True)
    plt.figure(figsize=(10, 6), facecolor="#0f172a")
    ax = plt.axes()
    ax.set_facecolor("#1e293b")

    # Custom styling matching the publication theme
    ax.spines["bottom"].set_color("#334155")
    ax.spines["top"].set_color("#334155")
    ax.spines["left"].set_color("#334155")
    ax.spines["right"].set_color("#334155")
    ax.tick_params(colors="#e2e8f0")
    ax.yaxis.label.set_color("#e2e8f0")
    ax.xaxis.label.set_color("#e2e8f0")

    x_axis = np.arange(len(next(iter(histories.values())))) * batch_size + len(seed_set)

    colors = {strategy: "#06b6d4", "random": "#64748b"}
    styles = {strategy: "-", "random": "--"}

    for strat, hist in histories.items():
        label_text = (
            f"Uncertainty: {strat.capitalize()}"
            if strat != "random"
            else "Random Baseline"
        )
        plt.plot(
            x_axis,
            hist,
            label=label_text,
            color=colors.get(strat, "#a78bfa"),
            linestyle=styles.get(strat, "-"),
            linewidth=2.5,
            marker="o",
        )

    plt.title(
        "Active Learning Convergence Comparison",
        color="#e2e8f0",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    plt.xlabel("Number of Labeled Training Samples", fontsize=12)
    plt.ylabel("Validation ROC AUC Score", fontsize=12)
    plt.grid(True, linestyle=":", color="#334155")
    plt.legend(facecolor="#1e293b", edgecolor="#334155", labelcolor="#e2e8f0")

    plt.savefig(out_plot, dpi=300, bbox_inches="tight")
    plt.close()

    click.echo("\n" + "=" * 60)
    click.echo("            ACTIVE LEARNING SIMULATION EXPERIMENT SUMMARY")
    click.echo("=" * 60)
    click.echo(f"  Comparison plot successfully saved to: {out_plot}")
    click.echo("  Results Table:")
    click.echo("  " + " | ".join(["Samples", f"{strategy.upper()} AUC", "RANDOM AUC"]))
    click.echo("  " + "--- | --- | ---")
    for i, x_val in enumerate(x_axis):
        strat_auc = histories[strategy][i]
        rand_auc = histories["random"][i]
        click.echo(f"  {x_val} | {strat_auc:.4f} | {rand_auc:.4f}")
    click.echo("=" * 60 + "\n")


if __name__ == "__main__":
    main()
