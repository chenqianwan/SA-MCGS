"""顶层 Pipeline 编排

Step 1: Raw Contract Documents → (Clause Segmentation & Classification)
Step 2: Clause & Dependency Extraction → Directed Dependency Graph
Step 3: Domain-Informed Graph Pruning  (⭐ noise + hierarchy + info bottleneck)
Step 4: SCC Detection (Tarjan's)
Step 5: DAG 确定性评估 + SCC 多采样
Step 6: 三层搜索树剪枝 (variance / dominance / influence)
Step 7: MCGS 搜索
Step 8: 统计聚合 + Risk Identification
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from .llm.base import BaseLLMClient
from .models.evaluation import ContractFinalResult
from .modules.aggregator import Aggregator
from .modules.clause_classifier import ClauseClassifier
from .modules.dag_evaluator import DAGEvaluator
from .modules.graph_builder import GraphBuilder
from .modules.graph_pruning import DomainGraphPruner
from .modules.mcgs import MCGS
from .modules.parser import ClauseParser
from .modules.pruning import DominancePruner, InfluencePruner, VariancePruner
from .modules.risk_identifier import RiskIdentifier
from .modules.scc_sampler import SCCSampler
from .modules.tarjan import TarjanSCCDetector


class SaMCGSPipeline:
    def __init__(self, config: dict, llm_client: BaseLLMClient):
        self.config = config
        # Step 1-2: Parse + Classify + Build Graph
        self.parser = ClauseParser(llm_client, config)
        self.classifier = ClauseClassifier(llm_client, config)
        self.graph_builder = GraphBuilder(llm_client, config)
        # Step 3: Domain-Informed Graph Pruning
        self.graph_pruner = DomainGraphPruner(config)
        # Step 4: Tarjan SCC Detection
        self.tarjan = TarjanSCCDetector()
        # Step 5: DAG Eval + SCC Sampling
        self.dag_evaluator = DAGEvaluator(llm_client, config)
        self.scc_sampler = SCCSampler(llm_client, config)
        # Step 6: Three-stage search tree pruning
        self.variance_pruner = VariancePruner(config)
        self.dominance_pruner = DominancePruner(config)
        self.influence_pruner = InfluencePruner(config)
        # Step 7: MCGS
        self.mcgs = MCGS(config)
        # Step 8: Aggregation + Risk Identification
        self.aggregator = Aggregator(config)
        self.risk_identifier = RiskIdentifier(config)

    async def run(
        self, raw_text: str, contract_id: str = "contract"
    ) -> ContractFinalResult:

        # ===== Step 1-2: 条款分割 → 分类 → 依赖图 =====
        logger.info("Step 1: Parsing clauses...")
        clauses = await self.parser.parse(raw_text)
        logger.info(f"  Found {len(clauses)} clauses")

        logger.info("Step 1: Classifying clause types (Def/Obl/Cond/Rem/Lim)...")
        clauses = await self.classifier.classify(clauses)

        logger.info("Step 2: Building dependency graph...")
        graph = await self.graph_builder.build(clauses)
        logger.info(f"  Dependency graph: {len(graph.edges)} edges")

        # ===== Step 3: Domain-Informed Graph Pruning (⭐) =====
        logger.info("Step 3: Domain-Informed Graph Pruning...")
        gp_stats = self.graph_pruner.prune(graph)
        logger.info(f"  Edges after pruning: {len(graph.edges)}")

        # ===== Step 4: Tarjan SCC Detection =====
        logger.info("Step 4: Running Tarjan SCC detection...")
        graph = self.tarjan.detect(graph)
        logger.info(
            f"  {len(graph.sccs)} non-trivial SCCs, "
            f"DAG ratio={graph.metadata.get('dag_ratio', 0):.1%}"
        )

        # ===== Step 5: DAG 确定性评估 + SCC 采样 =====
        logger.info("Step 5: Evaluating DAG nodes (deterministic)...")
        dag_results = await self.dag_evaluator.evaluate(graph)
        logger.info(f"  Evaluated {len(dag_results)} DAG nodes")

        if graph.sccs:
            logger.info("Step 5: Multi-sampling SCCs (stochastic)...")
            scc_samples = await self.scc_sampler.sample_all_sccs(graph, dag_results, on_progress=on_progress)
        else:
            logger.info("Step 5: No SCCs to sample")
            scc_samples = {}

        # ===== Step 6: 三层搜索树剪枝 =====
        logger.info("Step 6a: Variance pruning...")
        vp_stats = self.variance_pruner.prune(graph)

        logger.info("Step 6: Building search tree...")
        search_tree = self.scc_sampler.build_search_tree(graph, scc_samples)

        logger.info("Step 6b: Dominance pruning...")
        dp_stats = self.dominance_pruner.prune(search_tree)

        logger.info("Step 6c: Influence pruning...")
        ip_stats = self.influence_pruner.prune(search_tree, graph)

        active_nodes = {
            sid: n
            for sid, n in search_tree.nodes.items()
            if n.active_branches
        }
        total_active = sum(len(n.active_branches) for n in active_nodes.values())
        logger.info(f"  Remaining: {len(active_nodes)} SCC nodes, {total_active} branches")

        # ===== Step 7: MCGS 搜索 =====
        if not active_nodes or total_active <= len(active_nodes):
            logger.info("Step 7: No search needed — all SCCs resolved by pruning")
            rollout_results: list[dict[str, Any]] = []
        else:
            logger.info(f"Step 7: Running MCGS ({self.mcgs.num_rollouts} rollouts)...")
            rollout_results = self.mcgs.search(search_tree, dag_results, graph)

        # ===== Step 8: 聚合 + 风险识别 =====
        logger.info("Step 8: Aggregating results...")
        collapsed_results = {}
        for scc in graph.sccs:
            if scc.is_collapsed and scc.collapsed_value:
                collapsed_results.update(scc.collapsed_value)

        result = self.aggregator.aggregate(
            rollout_results, dag_results, collapsed_results, graph
        )
        result.contract_id = contract_id

        logger.info("Step 8: SCC-based risk identification...")
        result = self.risk_identifier.identify(result, graph)

        logger.info(f"  Overall risk: {result.overall_risk_score:.4f}")
        logger.info(f"  High-risk clauses: {result.high_risk_clauses}")
        logger.info(f"  Uncertain clauses: {result.uncertain_clauses}")
        logger.info(f"  Risk patterns: {result.scc_statistics.get('pattern_count', 0)}")

        return result

    async def run_from_graph(
        self, graph: "DependencyGraph", graph_id: str = "graph", on_progress: Optional[callable] = None
    ) -> ContractFinalResult:
        """从预构建的 DependencyGraph 开始运行（跳过 Step 1-2）。

        用于 QuantLaw 等已有图结构的数据源。
        从 Step 3 (Domain-Informed Graph Pruning) 开始。
        """
        from .models.graph import DependencyGraph as _DG  # noqa: F811

        logger.info(f"Running from pre-built graph: {graph_id} "
                     f"({len(graph.clauses)} nodes, {len(graph.edges)} edges)")

        # ===== Step 3: Domain-Informed Graph Pruning (⭐) =====
        logger.info("Step 3: Domain-Informed Graph Pruning...")
        gp_stats = self.graph_pruner.prune(graph)
        logger.info(f"  Edges after pruning: {len(graph.edges)}")

        # ===== Step 4: Tarjan SCC Detection =====
        logger.info("Step 4: Running Tarjan SCC detection...")
        graph = self.tarjan.detect(graph)
        logger.info(
            f"  {len(graph.sccs)} non-trivial SCCs, "
            f"DAG ratio={graph.metadata.get('dag_ratio', 0):.1%}"
        )

        # ===== Step 5: DAG 确定性评估 + SCC 采样 =====
        logger.info("Step 5: Evaluating DAG nodes (deterministic)...")
        dag_results = await self.dag_evaluator.evaluate(graph, on_progress=on_progress)
        logger.info(f"  Evaluated {len(dag_results)} DAG nodes")

        if graph.sccs:
            logger.info("Step 5: Multi-sampling SCCs (stochastic)...")
            scc_samples = await self.scc_sampler.sample_all_sccs(graph, dag_results, on_progress=on_progress)
        else:
            logger.info("Step 5: No SCCs to sample")
            scc_samples = {}

        # ===== Step 6: 三层搜索树剪枝 =====
        logger.info("Step 6a: Variance pruning...")
        vp_stats = self.variance_pruner.prune(graph)

        logger.info("Step 6: Building search tree...")
        search_tree = self.scc_sampler.build_search_tree(graph, scc_samples)

        logger.info("Step 6b: Dominance pruning...")
        dp_stats = self.dominance_pruner.prune(search_tree)

        logger.info("Step 6c: Influence pruning...")
        ip_stats = self.influence_pruner.prune(search_tree, graph)

        active_nodes = {
            sid: n
            for sid, n in search_tree.nodes.items()
            if n.active_branches
        }
        total_active = sum(len(n.active_branches) for n in active_nodes.values())
        logger.info(f"  Remaining: {len(active_nodes)} SCC nodes, {total_active} branches")

        # ===== Step 7: MCGS 搜索 =====
        if not active_nodes or total_active <= len(active_nodes):
            logger.info("Step 7: No search needed — all SCCs resolved by pruning")
            rollout_results: list[dict[str, Any]] = []
        else:
            logger.info(f"Step 7: Running MCGS ({self.mcgs.num_rollouts} rollouts)...")
            rollout_results = self.mcgs.search(search_tree, dag_results, graph)

        # ===== Step 8: 聚合 + 风险识别 =====
        logger.info("Step 8: Aggregating results...")
        collapsed_results = {}
        for scc in graph.sccs:
            if scc.is_collapsed and scc.collapsed_value:
                collapsed_results.update(scc.collapsed_value)

        result = self.aggregator.aggregate(
            rollout_results, dag_results, collapsed_results, graph
        )
        result.contract_id = graph_id

        logger.info("Step 8: SCC-based risk identification...")
        result = self.risk_identifier.identify(result, graph)

        logger.info(f"  Overall risk: {result.overall_risk_score:.4f}")
        logger.info(f"  High-risk clauses: {result.high_risk_clauses}")
        logger.info(f"  Uncertain clauses: {result.uncertain_clauses}")
        logger.info(f"  Risk patterns: {result.scc_statistics.get('pattern_count', 0)}")

        return result

    def analyze_graph_structure(self, graph: "DependencyGraph") -> dict[str, Any]:
        """对预构建图只跑 Step 3-4，返回结构统计。"""
        pre_pruning_edges = len(graph.edges)
        gp_stats = self.graph_pruner.prune(graph)
        post_pruning_edges = len(graph.edges)

        graph = self.tarjan.detect(graph)
        return {
            "num_nodes": len(graph.clauses),
            "pre_pruning_edges": pre_pruning_edges,
            "post_pruning_edges": post_pruning_edges,
            "graph_pruning": gp_stats,
            **graph.metadata,
        }

    async def analyze_structure(self, raw_text: str) -> dict[str, Any]:
        """跑 Step 1-4，返回依赖图结构统计（用于论文实证分析）。
        包含剪枝前后对比。
        """
        clauses = await self.parser.parse(raw_text)
        clauses = await self.classifier.classify(clauses)
        graph = await self.graph_builder.build(clauses)

        pre_pruning_edges = len(graph.edges)
        gp_stats = self.graph_pruner.prune(graph)
        post_pruning_edges = len(graph.edges)

        graph = self.tarjan.detect(graph)
        return {
            "num_clauses": len(clauses),
            "pre_pruning_edges": pre_pruning_edges,
            "post_pruning_edges": post_pruning_edges,
            "graph_pruning": gp_stats,
            **graph.metadata,
        }
