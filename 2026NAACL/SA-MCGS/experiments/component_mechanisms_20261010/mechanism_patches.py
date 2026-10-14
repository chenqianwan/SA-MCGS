"""Isolated search interventions; no SDK construction or global monkey-patches.

Load the frozen science package before importing this module. The production
search/evaluation/backpropagation/core selection implementation remains inherited.
Only search guidance, instance randomness, and rollout-local metadata differ.
"""
from __future__ import annotations

import copy
from contextvars import ContextVar
import hashlib
import json
import random
import types
from typing import Any, Callable

from src.modules.alphago_mcgs import AlphaGoMCGS


ARMS = (
    "full", "no_relation_guidance", "no_critical_revisit", "no_both",
    "random_windows",
)
PATCH_VERSION = "component_mechanisms.v1"


def derive_search_seed(master_seed: int, *identity_parts: str) -> int:
    """Stable across hosts/processes; callers decide the paired identity scope."""
    value = json.dumps([master_seed, *identity_parts], ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8")
    return int.from_bytes(hashlib.sha256(value).digest()[:8], "big")


def _bind_instance_random(fn: Callable, instance: Any, rng: random.Random):
    """Keep the original function bytecode; replace its RNG binding privately."""
    globals_copy = dict(fn.__globals__)
    globals_copy["random"] = rng
    private_fn = types.FunctionType(fn.__code__, globals_copy, fn.__name__,
                                    fn.__defaults__, fn.__closure__)
    private_fn.__kwdefaults__ = fn.__kwdefaults__
    private_fn.__annotations__ = fn.__annotations__
    return types.MethodType(private_fn, instance)


class MechanismMCGS(AlphaGoMCGS):
    """Five-arm SA search with unchanged ledger and final-core machinery.

    ``seed`` controls only the local search RNG, not provider-side sampling.
    ``trace_callback`` is synchronous and receives a detached completed event;
    it can append durable progress but is not a resumable search checkpoint.
    """

    def __init__(self, llm_client, config: dict, *, arm: str, seed: int,
                 trace_callback: Callable[[dict], None] | None = None):
        if arm not in ARMS:
            raise ValueError(f"Unknown mechanism arm: {arm}")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("seed must be an integer")
        self.arm = arm
        self.search_seed = seed
        self._instance_rng = random.Random(seed)
        self._selection_context: ContextVar[dict | None] = ContextVar(
            f"mcgs_selection_{id(self)}", default=None)
        self.trace_callback = trace_callback
        self._search_active = False
        self.effective_config = copy.deepcopy(config)
        settings = self.effective_config.get(
            "alphago_mcgs", self.effective_config.get("mcgs", {}))
        settings.setdefault("trace", True)
        super().__init__(llm_client=llm_client, config=self.effective_config)
        if not self.trace_enabled:
            raise ValueError("Mechanism study requires trace=True")
        if not self.critical_pair_ledger_enabled or not self.relation_first_enabled:
            raise ValueError("All arms require the Full relation/ledger base configuration")
        self.relation_guidance_enabled = arm not in {
            "no_relation_guidance", "no_both", "random_windows"}
        self.critical_revisit_enabled = arm not in {
            "no_critical_revisit", "no_both", "random_windows"}
        # Keep relation_first=True: this preserves ledger/context/core behavior
        # and the original shared probe cadence. Only the prior bonus is zeroed.
        if arm in {"no_relation_guidance", "no_both"}:
            self.relation_prior_weight = 0.0
            settings.setdefault("evidence", {})["relation_prior_weight"] = 0.0
        if arm in {"no_critical_revisit", "no_both"}:
            self.critical_pair_revisit_fraction = 0.0
            settings.setdefault("evidence", {})["critical_pair_revisit_fraction"] = 0.0
        self._ucb_select_seed = _bind_instance_random(
            AlphaGoMCGS._ucb_select_seed, self, self._instance_rng)
        self._original_select = _bind_instance_random(
            AlphaGoMCGS._select_and_expand, self, self._instance_rng)

    @property
    def _last_selection_meta(self) -> dict:
        value = self._selection_context.get()
        return value if value is not None else {}

    @_last_selection_meta.setter
    def _last_selection_meta(self, value: dict) -> None:
        # asyncio tasks inherit a context but each later assignment is local.
        self._selection_context.set(copy.deepcopy(value))

    def _best_relation_pair(self):
        # The production probe selector tries critical revisit first. Disabling
        # only this fallback leaves critical eligibility and cadence unchanged.
        if self.arm in {"no_relation_guidance", "no_both"}:
            return None
        return super()._best_relation_pair()

    def _select_and_expand(self, iteration: int) -> list[str]:
        if self.arm != "random_windows":
            return self._original_select(iteration)
        nodes = list(self._scc_ids)
        if not nodes:
            return []
        target = min(self.window_size, len(nodes))
        seed_node = self._instance_rng.choice(nodes)
        window, seen = [seed_node], {seed_node}
        while len(window) < target:
            frontier = []
            for node in window:
                frontier.extend(n for n in self._adjacency.get(node, []) if n not in seen)
                frontier.extend(n for n in self._reverse_adj.get(node, []) if n not in seen)
            candidates = list(dict.fromkeys(frontier))
            if not candidates:
                candidates = [node for node in nodes if node not in seen]
            if not candidates:
                break
            node = self._instance_rng.choice(candidates)
            window.append(node)
            seen.add(node)
        self._last_selection_meta = {
            "mode": "random_local_window", "seed": seed_node,
            "random_seed": self.search_seed,
        }
        self._selection_events.append({
            "iteration": iteration + 1, "window": list(window),
            **self._last_selection_meta,
        })
        return window

    def _record_trace(self, iteration, window, entry, is_tt_hit):
        super()._record_trace(iteration, window, entry, is_tt_hit)
        event = self._trace_events[-1]
        self._assert_event_metadata(event)
        if self.trace_callback is not None:
            self.trace_callback(copy.deepcopy(event))

    def _assert_event_metadata(self, event: dict) -> None:
        expected = next((item for item in reversed(self._selection_events)
                         if item["iteration"] == event["iteration"]), None)
        if expected is None or expected["window"] != event["window"]:
            raise AssertionError("Completed rollout does not match its selected window")
        meta = event["selection"]
        for key, value in expected.items():
            if key not in {"iteration", "window"} and meta.get(key) != value:
                raise AssertionError(f"Rollout selection metadata mismatch: {key}")
        if "window" in meta and meta["window"] != event["window"]:
            raise AssertionError("Probe metadata belongs to a different window")

    def mechanism_audit(self) -> dict:
        return {
            "patch_version": PATCH_VERSION,
            "arm": self.arm,
            "search_seed": self.search_seed,
            "rng_scope": "instance; provider sampling seed is not set here",
            "metadata_scope": "per-instance ContextVar, per-rollout asyncio task",
            "ledger_enabled": self.critical_pair_ledger_enabled,
            "relation_guidance_enabled": self.relation_guidance_enabled,
            "critical_revisit_enabled": self.critical_revisit_enabled,
            "random_windows": self.arm == "random_windows",
            "relation_prior_weight": self.relation_prior_weight,
            "probe_fraction": self.relation_probe_fraction,
            "critical_pair_revisit_fraction": self.critical_pair_revisit_fraction,
            "probe_cadence_policy": "unchanged production gate; critical checked before ordinary relation probe",
            "internal_concurrency": self.concurrency,
            "trace_events": len(self._trace_events),
            "selection_events": len(self._selection_events),
            "completed_trace_metadata_verified": True,
            "core_selector": "unchanged production native core",
        }

    async def search(self, graph, scc_info):
        if self._search_active:
            raise RuntimeError("Do not run two searches on one MechanismMCGS instance")
        self._search_active = True
        self._instance_rng.seed(self.search_seed)
        try:
            result = await super().search(graph, scc_info)
            result["mechanism_audit"] = self.mechanism_audit()
            return result
        finally:
            self._search_active = False

