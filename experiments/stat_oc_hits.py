import json
from collections import Counter

def analyze_oc_hit_rate():
    with open("experiments/results/ablation_suite.json") as f:
        data = json.load(f)
    
    all_cases = []
    for exp_key in ["exp1_cross_scale", "exp2_multi_target", "exp3_repeated"]:
        all_cases.extend(data.get(exp_key, []))
    
    print("=" * 100)
    print(f"{'Condition':<30} | {'Size':<4} | {'Target':<12} | {'OC Detected List':<40} | {'Hit?'}")
    print("-" * 100)
    
    hits = 0
    total = len(all_cases)
    
    for c in all_cases:
        target = c["target_id"]
        # In the JSON, it's under pert_mcgs -> oc_detected_clauses
        oc_list = c.get("pert_mcgs", {}).get("oc_detected_clauses", [])
        is_hit = target in oc_list
        if is_hit:
            hits += 1
        
        hit_str = "✅ YES" if is_hit else "❌ NO"
        oc_str = ", ".join(oc_list[:5]) + ("..." if len(oc_list) > 5 else "")
        label = c.get("label", "N/A")
        size = c.get("scc_size", 0)
        
        print(f"{label:<30} | {size:<4} | {target:<12} | {oc_str:<40} | {hit_str}")
        
    print("-" * 100)
    print(f"OVERALL OC TARGET HIT RATE: {hits}/{total} ({hits/total:.1%})")
    
    # Also check False Positives in Clean runs
    print("\n" + "=" * 100)
    print("FALSE POSITIVE ANALYSIS (CLEAN RUNS)")
    print("-" * 100)
    fp_total_oc = 0
    for c in all_cases:
        clean_oc = c.get("clean_mcgs", {}).get("oc_detected_clauses", [])
        fp_total_oc += len(clean_oc)
    
    print(f"Average OC detections in CLEAN SCCs: {fp_total_oc/total:.2f} nodes per SCC")
    print("=" * 100)

if __name__ == "__main__":
    analyze_oc_hit_rate()
