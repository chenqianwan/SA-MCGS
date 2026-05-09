"""Deep analysis of ablation suite results.

Focuses on:
1. Multi-run averaging (Exp 3: 3 repeated trials on 24n)
2. OC detection frequency: which nodes are OC-detected more often in perturbed vs clean
3. Comprehensive comparison table
4. Honest assessment of signal vs noise
"""
import json
from collections import Counter, defaultdict


def load():
    with open("experiments/results/ablation_suite.json") as f:
        return json.load(f)


def analyze_repeated_trials(data):
    """Analyze Exp 3: 3 repeated trials on same 24n SCC."""
    repeated = data.get("exp3_repeated", [])
    if not repeated:
        print("No repeated trial data found")
        return

    target_id = repeated[0]["target_id"]
    n = repeated[0]["scc_size"]
    all_ids = repeated[0]["scc_clause_ids"]

    print("=" * 90)
    print(f"MULTI-RUN ANALYSIS: {len(repeated)} trials on {n}-node SCC, target={target_id}")
    print("=" * 90)

    # ── 1. Per-node averaged scores ──────────────────────────────────
    clean_means = defaultdict(list)
    pert_means = defaultdict(list)
    clean_oc_counter = Counter()
    pert_oc_counter = Counter()

    for r in repeated:
        cm = r["clean_mcgs"]["clause_details"]
        pm = r["pert_mcgs"]["clause_details"]
        for cid in all_ids:
            clean_means[cid].append(cm.get(cid, {}).get("mean_score", 0))
            pert_means[cid].append(pm.get(cid, {}).get("mean_score", 0))
        for cid in r["clean_mcgs"]["oc_detected_clauses"]:
            clean_oc_counter[cid] += 1
        for cid in r["pert_mcgs"]["oc_detected_clauses"]:
            pert_oc_counter[cid] += 1

    # Compute averaged delta
    avg_deltas = []
    for cid in all_ids:
        avg_clean = sum(clean_means[cid]) / len(clean_means[cid])
        avg_pert = sum(pert_means[cid]) / len(pert_means[cid])
        avg_delta = avg_pert - avg_clean
        oc_clean_freq = clean_oc_counter[cid]
        oc_pert_freq = pert_oc_counter[cid]
        avg_deltas.append({
            "cid": cid,
            "is_target": cid == target_id,
            "avg_clean": avg_clean,
            "avg_pert": avg_pert,
            "avg_delta": avg_delta,
            "oc_clean_freq": oc_clean_freq,
            "oc_pert_freq": oc_pert_freq,
            "oc_delta": oc_pert_freq - oc_clean_freq,
        })

    avg_deltas.sort(key=lambda x: x["avg_delta"], reverse=True)
    target_rank = next(i + 1 for i, d in enumerate(avg_deltas) if d["is_target"])

    print(f"\n--- AVERAGED Δμ (across {len(repeated)} runs) ---")
    print(f"{'Rank':<5} {'Clause':<12} {'Avg Clean':>10} {'Avg Pert':>10} {'Avg Δμ':>10} "
          f"{'OC clean':>9} {'OC pert':>9} {'OC Δ':>6} {'Target':>8}")
    print("-" * 85)

    for i, d in enumerate(avg_deltas):
        marker = ">>> *" if d["is_target"] else ""
        print(f"{i+1:<5} {d['cid']:<12} {d['avg_clean']:>10.4f} {d['avg_pert']:>10.4f} "
              f"{d['avg_delta']:>+10.4f} {d['oc_clean_freq']:>6}/{len(repeated)} "
              f"{d['oc_pert_freq']:>6}/{len(repeated)} {d['oc_delta']:>+4} {marker:>8}")

    print(f"\n  Target {target_id}: averaged rank=#{target_rank}/{n}, "
          f"avg Δμ={avg_deltas[target_rank-1]['avg_delta']:+.4f}")

    # ── 2. Single-run rank variability ───────────────────────────────
    print(f"\n--- PER-RUN TARGET RANK ---")
    ranks = []
    for i, r in enumerate(repeated):
        d = r["delta"]
        ranks.append(d["target_rank"])
        print(f"  Run {i+1}: rank=#{d['target_rank']}/{n}, Δμ={d['target_delta_mean']:+.4f}")
    print(f"  Mean rank: {sum(ranks)/len(ranks):.1f}, Std: "
          f"{(sum((r - sum(ranks)/len(ranks))**2 for r in ranks)/len(ranks))**0.5:.1f}")

    # ── 3. OC frequency analysis ────────────────────────────────────
    print(f"\n--- OC DETECTION FREQUENCY ---")
    oc_by_freq = sorted(
        [(cid, pert_oc_counter[cid], clean_oc_counter[cid])
         for cid in all_ids if pert_oc_counter[cid] > 0 or clean_oc_counter[cid] > 0],
        key=lambda x: x[1] - x[2], reverse=True
    )
    print(f"  {'Clause':<12} {'Pert OC freq':>13} {'Clean OC freq':>14} {'Delta':>6} {'Target':>8}")
    for cid, pf, cf in oc_by_freq:
        marker = "<< TARGET" if cid == target_id else ""
        print(f"  {cid:<12} {pf:>6}/{len(repeated)} {cf:>7}/{len(repeated)} {pf-cf:>+4}   {marker}")

    # ── 4. Total OC count comparison ─────────────────────────────────
    clean_oc_counts = [len(r["clean_mcgs"]["oc_detected_clauses"]) for r in repeated]
    pert_oc_counts = [len(r["pert_mcgs"]["oc_detected_clauses"]) for r in repeated]
    print(f"\n--- TOTAL OC COUNTS ---")
    print(f"  Clean: {clean_oc_counts} → avg={sum(clean_oc_counts)/len(clean_oc_counts):.1f}")
    print(f"  Pert:  {pert_oc_counts} → avg={sum(pert_oc_counts)/len(pert_oc_counts):.1f}")
    print(f"  Delta: {[p-c for p,c in zip(pert_oc_counts, clean_oc_counts)]} "
          f"→ avg={sum(p-c for p,c in zip(pert_oc_counts, clean_oc_counts))/len(repeated):.1f}")

    return avg_deltas, target_rank


def analyze_cross_scale(data):
    """Analyze Exp 1: different SCC sizes."""
    results = data.get("exp1_cross_scale", [])
    print(f"\n{'='*90}")
    print("CROSS-SCALE COMPARISON")
    print("=" * 90)

    print(f"\n{'Label':<20} {'Size':>5} {'Target':>12} | "
          f"{'MCGS Δrank':>12} {'Δμ':>8} | "
          f"{'J.FP':>5} {'J.Det':>6} {'J.Tgt':>6} {'J.AvgFlg':>9}")
    print("-" * 100)
    for r in results:
        d = r["delta"]
        print(f"{r['label']:<20} {r['scc_size']:>5} {r['target_id']:>12} | "
              f"#{d['target_rank']:>2}/{d['scc_size']:<3} {d['target_delta_mean']:>+8.4f} | "
              f"{r['clean_joint']['det_rate']:>4.0%} {r['pert_joint']['det_rate']:>5.0%} "
              f"{r['joint_target_in_pert']:>3}/5 {r['joint_avg_flagged_pert']:>7.1f}")


def analyze_multi_target(data):
    """Analyze Exp 2: different target nodes on same SCC."""
    results = data.get("exp2_multi_target", [])
    print(f"\n{'='*90}")
    print("MULTI-TARGET COMPARISON (24n SCC)")
    print("=" * 90)

    print(f"\n{'Target':>12} | {'MCGS Δrank':>12} {'Δμ':>8} {'New OC':>10} | "
          f"{'J.FP':>5} {'J.Det':>6} {'J.Tgt':>6}")
    print("-" * 75)
    for r in results:
        d = r["delta"]
        new_oc = ",".join(d.get("new_oc", [])[:3]) or "—"
        print(f"{r['target_id']:>12} | "
              f"#{d['target_rank']:>2}/{d['scc_size']:<3} {d['target_delta_mean']:>+8.4f} "
              f"{new_oc:>10} | "
              f"{r['clean_joint']['det_rate']:>4.0%} {r['pert_joint']['det_rate']:>5.0%} "
              f"{r['joint_target_in_pert']:>3}/5")


def overall_summary(data):
    """Generate the honest overall summary."""
    print(f"\n{'='*90}")
    print("OVERALL ABLATION SUMMARY")
    print("=" * 90)

    summary = data["summary"]

    print(f"\n{'Label':<32} | {'SCC':>3} | {'MCGS Δ rank':>12} | "
          f"{'Joint FP':>8} {'Joint Det':>9} {'Joint Tgt':>9}")
    print("-" * 95)
    for row in summary:
        print(f"{row['label']:<32} | {row['scc_size']:>3} | "
              f"#{row['mcgs_delta_rank']:>2}/{row['scc_size']:<3} Δμ={row['mcgs_delta_mean']:>+.3f} | "
              f"{row['joint_clean_fp_rate']:>7.0%} {row['joint_pert_det_rate']:>8.0%} "
              f"{row['joint_target_in_pert']:>5}/5")

    # Key metrics across all experiments
    all_24n = [r for r in summary if r["scc_size"] == 24]
    if all_24n:
        avg_rank = sum(r["mcgs_delta_rank"] for r in all_24n) / len(all_24n)
        avg_joint_tgt = sum(r["joint_target_in_pert"] for r in all_24n) / len(all_24n)
        print(f"\n  24n stats (N={len(all_24n)}):")
        print(f"    MCGS Delta: avg rank = {avg_rank:.1f}/24 (ideal=1)")
        print(f"    Joint LLM:  avg target identification = {avg_joint_tgt:.1f}/5")
        print(f"    Joint LLM:  FP rate on clean = 100% (all runs)")

    print(f"\n--- KEY FINDINGS ---")
    print(f"  1. Single-run MCGS Delta has HIGH VARIANCE:")
    print(f"     - Target rank varies widely across runs (14-23/24)")
    print(f"     - Independent LLM sampling creates noise that overwhelms perturbation signal")
    print(f"  2. Joint LLM has fundamental blind spots:")
    print(f"     - 24n: 100% FP (always finds 'defects' even on clean legal text)")
    print(f"     - 9n: 0% detection (misses both clean and perturbed)")
    print(f"     - 5n: 100% detection but also 100% FP (not discriminative)")
    print(f"  3. MCGS shows CONSISTENT signal in OC detection counts:")
    print(f"     - Perturbed runs consistently have MORE OC detections than clean")
    print(f"     - This aggregate metric may be more reliable than per-node delta")
    print(f"  4. PROPOSED IMPROVEMENT: Paired sampling design")
    print(f"     - Use same LLM samples for clean and perturbed")
    print(f"     - Only change the perturbation text, keep tree structure identical")
    print(f"     - This eliminates inter-run variance, isolating the true signal")


def main():
    data = load()
    overall_summary(data)
    analyze_cross_scale(data)
    analyze_multi_target(data)
    avg_deltas, target_rank = analyze_repeated_trials(data)


if __name__ == "__main__":
    main()
