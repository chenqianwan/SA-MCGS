"""Delta Analysis: Compare Clean vs Perturbed MCGS on 24n SCC.

Computes per-node risk delta to identify injected defect from noise.
Uses existing experiment data — no LLM calls needed.
"""
import json

def main():
    with open("experiments/results/control_24n.json") as f:
        clean = json.load(f)
    with open("experiments/results/verdict_fair_24n.json") as f:
        perturbed = json.load(f)

    clean_details = clean["mcgs"]["clause_details"]
    pert_case = perturbed["cases"][0]
    pert_details = pert_case["mcgs_clause_details"]
    target_id = pert_case["target_id"]

    clean_oc = set(clean["mcgs"]["oc_detected_clauses"])
    pert_oc = set(pert_case["mcgs_oc_detected_clauses"])

    clean_hr = set(clean["mcgs"]["high_risk_clauses"])
    pert_hr = set(pert_case["mcgs_high_risk_clauses"])

    all_ids = sorted(clean_details.keys())

    print("=" * 90)
    print(f"DELTA ANALYSIS: Clean vs Perturbed MCGS on {len(all_ids)}-node SCC")
    print(f"Target (injected defect): {target_id}")
    print("=" * 90)

    # Compute deltas
    deltas = []
    for cid in all_ids:
        c = clean_details.get(cid, {})
        p = pert_details.get(cid, {})
        c_mean = c.get("mean_score", 0)
        p_mean = p.get("mean_score", 0)
        c_max = c.get("max_score", 0)
        p_max = p.get("max_score", 0)
        c_std = c.get("std_score", 0)
        p_std = p.get("std_score", 0)

        delta_mean = p_mean - c_mean
        delta_max = p_max - c_max
        delta_std = p_std - c_std

        oc_change = ""
        if cid in pert_oc and cid not in clean_oc:
            oc_change = "NEW_OC"
        elif cid in clean_oc and cid not in pert_oc:
            oc_change = "LOST_OC"
        elif cid in clean_oc and cid in pert_oc:
            oc_change = "BOTH_OC"

        hr_change = ""
        if cid in pert_hr and cid not in clean_hr:
            hr_change = "NEW_HR"
        elif cid in clean_hr and cid not in pert_hr:
            hr_change = "LOST_HR"

        deltas.append({
            "cid": cid,
            "is_target": cid == target_id,
            "clean_mean": c_mean,
            "pert_mean": p_mean,
            "delta_mean": delta_mean,
            "clean_max": c_max,
            "pert_max": p_max,
            "delta_max": delta_max,
            "clean_std": c_std,
            "pert_std": p_std,
            "delta_std": delta_std,
            "oc_change": oc_change,
            "hr_change": hr_change,
        })

    # Sort by delta_mean descending (biggest risk increase first)
    deltas.sort(key=lambda x: x["delta_mean"], reverse=True)

    # Print table
    print(f"\n{'Rank':<5} {'Clause':<12} {'Clean μ':>8} {'Pert μ':>8} {'Δμ':>8} "
          f"{'Clean max':>10} {'Pert max':>10} {'Δmax':>6} "
          f"{'Δstd':>8} {'OC Change':>10} {'HR Change':>10} {'Target':>8}")
    print("-" * 120)

    for i, d in enumerate(deltas):
        marker = ">>> *" if d["is_target"] else ""
        print(f"{i+1:<5} {d['cid']:<12} {d['clean_mean']:>8.3f} {d['pert_mean']:>8.3f} {d['delta_mean']:>+8.3f} "
              f"{d['clean_max']:>10.2f} {d['pert_max']:>10.2f} {d['delta_max']:>+6.2f} "
              f"{d['delta_std']:>+8.3f} {d['oc_change']:>10} {d['hr_change']:>10} {marker:>8}")

    # Summary
    print("\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)

    target_delta = next(d for d in deltas if d["is_target"])
    target_rank = next(i+1 for i, d in enumerate(deltas) if d["is_target"])
    print(f"\nTarget node: {target_id}")
    print(f"  Rank by Δμ: #{target_rank} out of {len(deltas)}")
    print(f"  Δμ = {target_delta['delta_mean']:+.3f} (clean={target_delta['clean_mean']:.3f} → pert={target_delta['pert_mean']:.3f})")
    print(f"  Δmax = {target_delta['delta_max']:+.2f}")
    print(f"  OC change: {target_delta['oc_change'] or 'none'}")
    print(f"  HR change: {target_delta['hr_change'] or 'none'}")

    # New OC detections
    new_oc = pert_oc - clean_oc
    lost_oc = clean_oc - pert_oc
    print(f"\nOC Detection Changes:")
    print(f"  Clean OC ({len(clean_oc)}): {sorted(clean_oc)}")
    print(f"  Pert  OC ({len(pert_oc)}):  {sorted(pert_oc)}")
    print(f"  NEW OC (only in Perturbed):  {sorted(new_oc)}")
    print(f"  LOST OC (only in Clean):     {sorted(lost_oc)}")

    # New HR detections
    new_hr = pert_hr - clean_hr
    lost_hr = clean_hr - pert_hr
    print(f"\nHR Detection Changes:")
    print(f"  Clean HR ({len(clean_hr)}): {len(clean_hr)} clauses")
    print(f"  Pert  HR ({len(pert_hr)}):  {len(pert_hr)} clauses")
    print(f"  NEW HR (only in Perturbed):  {sorted(new_hr)}")

    # Top-3 delta nodes
    print(f"\nTop-5 nodes by risk increase (Δμ):")
    for i, d in enumerate(deltas[:5]):
        marker = " <<<< TARGET" if d["is_target"] else ""
        print(f"  #{i+1} {d['cid']}: Δμ={d['delta_mean']:+.3f}, "
              f"Δmax={d['delta_max']:+.2f}, OC={d['oc_change'] or '—'}{marker}")

    # Bottom-3 (risk decrease)
    print(f"\nTop-5 nodes by risk decrease (Δμ):")
    for d in deltas[-5:]:
        marker = " <<<< TARGET" if d["is_target"] else ""
        print(f"  {d['cid']}: Δμ={d['delta_mean']:+.3f}, "
              f"Δmax={d['delta_max']:+.2f}, OC={d['oc_change'] or '—'}{marker}")

    # Joint LLM comparison
    print(f"\n{'='*90}")
    print("JOINT LLM COMPARISON")
    print(f"{'='*90}")

    clean_joint = clean["joint"]
    pert_joint = pert_case

    c_avg_flagged = sum(t["num_flagged"] for t in clean_joint["trials"]) / len(clean_joint["trials"])
    p_avg_flagged = sum(len(t["issues_found"]) for t in pert_joint["joint_trials"]) / len(pert_joint["joint_trials"])

    print(f"\n  Clean Joint LLM: FP rate={clean_joint['false_positive_rate']:.0%}, avg flagged={c_avg_flagged:.1f}/{len(all_ids)}")
    print(f"  Pert  Joint LLM: det rate={pert_joint['joint_found_defect_rate']:.0%}, avg flagged={p_avg_flagged:.1f}/{len(all_ids)}")
    print(f"  Delta flagged: {p_avg_flagged - c_avg_flagged:+.1f} clauses")

    # Check if Joint LLM specifically identified the target
    target_in_joint = 0
    for t in pert_joint["joint_trials"]:
        if target_id in t["issues_found"]:
            target_in_joint += 1
    print(f"  Joint LLM identified TARGET ({target_id}): {target_in_joint}/{len(pert_joint['joint_trials'])} trials")

    # Save results
    output = {
        "experiment": "delta_analysis_24n",
        "target_id": target_id,
        "scc_size": len(all_ids),
        "target_rank_by_delta_mean": target_rank,
        "target_delta_mean": target_delta["delta_mean"],
        "target_delta_max": target_delta["delta_max"],
        "new_oc_detections": sorted(new_oc),
        "lost_oc_detections": sorted(lost_oc),
        "new_hr_detections": sorted(new_hr),
        "joint_llm_target_identification_rate": target_in_joint / len(pert_joint["joint_trials"]),
        "joint_llm_avg_flagged_clean": c_avg_flagged,
        "joint_llm_avg_flagged_perturbed": p_avg_flagged,
        "deltas": deltas,
    }
    with open("experiments/results/delta_24n.json", "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nDetailed results saved to experiments/results/delta_24n.json")


if __name__ == "__main__":
    main()
