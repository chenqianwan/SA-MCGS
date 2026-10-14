#!/usr/bin/env python3
"""Tokenize all frozen case prompts offline; never truncate or call a model."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def audit(tokenizer_path, max_model_len, output_path):
    from transformers import AutoTokenizer
    from science_support import load_science, science_args, save, tokenizer_hashes
    tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path), local_files_only=True, trust_remote_code=False)
    launcher, cost, manifest, graphs, plan = load_science()
    import methods_full as methods
    cost.validate_case_plan(plan, graphs)

    def count(prompt):
        ids = tokenizer.apply_chat_template([{'role': 'user', 'content': prompt}],
                                             tokenize=True, add_generation_prompt=True)
        if isinstance(ids, dict) or hasattr(ids, 'keys'):
            ids = ids['input_ids']
        return len(ids)

    rows = []
    for case in plan:
        graph, scc, _, _ = cost.prepare_injected_case(case, graphs)
        allowed = set(scc.clause_ids)
        edges = [edge for edge in graph.edges if edge.source in allowed and edge.target in allowed]
        full_prompt = cost.battle.DOMAIN_NAIVE_PROMPTS[case['domain']](
            graph.clauses, edges, scc.clause_ids, ranked=True,
            direct_subgraph=True, direct_subgraph_lite=False)
        full_input = count(full_prompt)
        source, aliases = methods.source_view(graph, scc)
        longest = max(aliases.values(), key=lambda value: (len(tokenizer.encode(value)), len(value)))
        stress_view = {'ranking': list(aliases.values()), 'H': list(aliases.values()),
                       'reported_conflict_pairs': [[longest, longest]] * 16}
        # Two maximally populated valid-size presentations cover the first actual judge invocation.
        selector_prompt = methods.judge_prompt(source, [
            {'candidate_id': 'C1', **stress_view}, {'candidate_id': 'C2', **stress_view}])
        selector_input = count(selector_prompt)
        machine = cost.AlphaGoMCGS(llm_client=None, config=cost.make_mcgs_config(science_args()))
        machine._init_state(graph, scc)
        windows = cost.deterministic_windows(machine, list(scc.clause_ids), 4)
        windows = list({frozenset(window): window for window in windows}.values())
        lea_inputs = [count(cost.battle.DOMAIN_MCGS_PROMPTS[case['domain']](machine, window))
                      for window in windows]
        rows.append({'case_uid': case['case_uid'], 'source_n': scc.size,
                     'full_input_tokens': full_input, 'full_requested_output_tokens': 12000,
                     'full_total_required': full_input + 12000,
                     'selector_two_full_presentations_input_tokens': selector_input,
                     'selector_requested_output_tokens': 256,
                     'selector_two_full_presentations_total_required': selector_input + 256,
                     'largest_lea_input_tokens': max(lea_inputs),
                     'lea_requested_output_tokens': 2048,
                     'largest_lea_total_required': max(lea_inputs) + 2048})
    required = max(max(row['full_total_required'], row['selector_two_full_presentations_total_required'],
                       row['largest_lea_total_required']) for row in rows)
    report = {'status': 'passed' if required <= max_model_len else 'context_too_short',
              'cases': len(rows), 'model_calls': 0, 'sa_model_calls': 0, 'truncation_enabled': False,
              'max_model_len': max_model_len, 'minimum_context_for_audited_requests': required,
              'max_full_input_tokens': max(row['full_input_tokens'] for row in rows),
              'max_two_candidate_selector_input_tokens': max(row['selector_two_full_presentations_input_tokens'] for row in rows),
              'tokenizer_hashes': tokenizer_hashes(tokenizer_path),
              'selector_growth_guard': 'Candidate count is dynamic. The unchanged method checks exact selector token count before adding each candidate and stops/excludes a candidate that cannot fit; it never truncates source or candidate presentations. This preflight checks two fully populated presentations, not an unbounded maximum candidate pool.',
              'rows': rows}
    save(output_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tokenizer-path', type=Path, required=True)
    parser.add_argument('--max-model-len', type=int, default=32768)
    parser.add_argument('--output', type=Path, default=ROOT/'preflight/context_validation.json')
    args = parser.parse_args()
    result = audit(args.tokenizer_path, args.max_model_len, args.output)
    print(json.dumps({key: value for key, value in result.items() if key not in ('rows', 'tokenizer_hashes')}))
    return 0 if result['status'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
