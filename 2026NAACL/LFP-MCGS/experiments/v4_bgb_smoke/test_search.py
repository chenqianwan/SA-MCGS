"""Regression tests for Phase-3's fairness and exact-merge contract."""

from __future__ import annotations

from dataclasses import replace

from search_core import (
    Action,
    Atom,
    ChargeLedger,
    FormalOutcome,
    OracleGraphEnvironment,
    PUCTPlanner,
    SearchCase,
    SearchState,
    Source,
    SourcedFact,
    SourcedRule,
    exact_lfp,
    run_method,
)


def make_case(
    *,
    case_id: str = "tiny",
    source_ids=("a", "b", "c"),
    adjacency=None,
    outcomes=None,
    root="a",
    budget=8,
    query="goal(x)",
    label="entailed",
) -> SearchCase:
    adjacency = adjacency or {"a": ("b",), "b": ("c",), "c": ("a",)}
    outcomes = outcomes or {}
    sources = tuple(
        Source(source_id, f"public source {source_id}", outcomes.get(source_id, FormalOutcome()))
        for source_id in source_ids
    )
    return SearchCase(
        case_id=case_id,
        public_query="Is goal x established?",
        query_atom=Atom("goal", ("x",)),
        sources=sources,
        adjacency={key: tuple(value) for key, value in adjacency.items()},
        root_source_id=root,
        action_budget=budget,
        condition="Productive",
        scc_size=len(source_ids),
        gold_label=label,
    )


def test_diamond_paths_merge_only_in_exact_graph_table():
    case = make_case(
        case_id="diamond",
        source_ids=("a", "b", "c", "d"),
        adjacency={"a": ("b", "c"), "b": ("d",), "c": ("d",), "d": tuple()},
        root="a",
        budget=4,
        label="unknown",
    )
    env = OracleGraphEnvironment(case)
    ledger = ChargeLedger()
    root = env.root()
    via_b = env.step(root, Action("move", "b"), ledger, phase="simulation", branch_id="b")
    d_from_b = env.step(via_b, Action("move", "d"), ledger, phase="simulation", branch_id="b")
    via_c = env.step(root, Action("move", "c"), ledger, phase="simulation", branch_id="c")
    d_from_c = env.step(via_c, Action("move", "d"), ledger, phase="simulation", branch_id="c")
    assert env.state_key(d_from_b) == env.state_key(d_from_c)

    graph = PUCTPlanner(env, root, ChargeLedger(), seed=17, merge_states=True)
    first_id, first_hit = graph.intern_state(d_from_b)
    second_id, second_hit = graph.intern_state(d_from_c)
    assert not first_hit
    assert second_hit
    assert first_id == second_id
    assert graph.tt_hits == 1

    tree = PUCTPlanner(env, root, ChargeLedger(), seed=17, merge_states=False)
    first_id, _ = tree.intern_state(d_from_b)
    second_id, _ = tree.intern_state(d_from_c)
    assert first_id != second_id
    assert tree.tt_hits == 0


def test_same_closure_but_different_provenance_does_not_merge():
    case = make_case(
        source_ids=("a", "b", "h"),
        adjacency={"a": ("h",), "b": ("h",), "h": tuple()},
        root="h",
        label="unknown",
    )
    env = OracleGraphEnvironment(case)
    atom = Atom("shared", ("x",))
    facts_a = (SourcedFact(atom, "a"),)
    facts_b = (SourcedFact(atom, "b"),)
    closure_a, provenance_a = exact_lfp(facts_a, tuple())
    closure_b, provenance_b = exact_lfp(facts_b, tuple())
    assert closure_a == closure_b
    assert provenance_a != provenance_b
    base = env.root()
    state_a = replace(
        base,
        sourced_facts=facts_a,
        closure=closure_a,
        provenance=provenance_a,
        coverage=frozenset({"a", "b"}),
    )
    state_b = replace(
        base,
        sourced_facts=facts_b,
        closure=closure_b,
        provenance=provenance_b,
        coverage=frozenset({"a", "b"}),
    )
    assert state_a.location == state_b.location
    assert state_a.remaining_budget == state_b.remaining_budget
    assert env.action_mask(state_a) == env.action_mask(state_b)
    assert env.state_key(state_a) != env.state_key(state_b)
    planner = PUCTPlanner(env, base, ChargeLedger(), seed=17, merge_states=True)
    first_id, _ = planner.intern_state(state_a)
    second_id, second_hit = planner.intern_state(state_b)
    assert not second_hit
    assert first_id != second_id


def test_unseeded_positive_cycle_cannot_self_prove():
    p = Atom("p", ("x",))
    q = Atom("q", ("x",))
    rules = (
        SourcedRule("r1", p, (q,), "a"),
        SourcedRule("r2", q, (p,), "b"),
    )
    closure, provenance = exact_lfp(tuple(), rules)
    assert closure == frozenset()
    assert provenance == tuple()


def test_tree_and_graph_are_identical_when_merge_is_disabled():
    seed = Atom("seed", ("x",))
    bridge = Atom("bridge", ("x",))
    goal = Atom("goal", ("x",))
    outcomes = {
        "a": FormalOutcome((seed,), tuple()),
        "b": FormalOutcome(tuple(), (SourcedRule("r1", bridge, (seed,), "b"),)),
        "c": FormalOutcome(tuple(), (SourcedRule("r2", goal, (bridge,), "c"),)),
    }
    case = make_case(outcomes=outcomes)
    shared = {
        "seed": 29,
        "action_cap": 8,
        "simulation_transition_cap": 96,
        "simulations_per_move": 8,
        "merge_override": False,
    }
    tree = run_method(case, "tree", **shared)
    graph = run_method(case, "graph", **shared)
    assert tree["real_actions"] == graph["real_actions"]
    assert tree["proof_recovered"] == graph["proof_recovered"]
    assert tree["proof_sources"] == graph["proof_sources"]
    assert tree["final_closure"] == graph["final_closure"]
    assert tree["metrics"] == graph["metrics"]
    assert tree["ledger"] == graph["ledger"]


def test_every_hypothetical_oracle_reveal_is_charged():
    seed = Atom("seed", ("x",))
    case = make_case(outcomes={"a": FormalOutcome((seed,), tuple())}, label="unknown")
    result = run_method(
        case,
        "graph",
        17,
        simulation_transition_cap=48,
        simulations_per_move=6,
    )
    reveals = [event for event in result["ledger"] if event["oracle_reveal"]]
    assert len(reveals) == result["metrics"]["total_charged_reads"]
    assert all(event["phase"] in {"real", "simulation"} for event in reveals)

