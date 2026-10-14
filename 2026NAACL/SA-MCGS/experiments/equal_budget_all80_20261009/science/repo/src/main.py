"""CLI 入口"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
import yaml
from loguru import logger

app = typer.Typer(
    name="sa-mcgs",
    help="Contract Risk Evaluation via Structure-Aware Monte Carlo Graph Search",
)


def _create_llm_client(llm_config: dict):
    from .llm import AnthropicClient, LocalClient, OpenAIClient

    provider = llm_config.get("provider", "openai")
    if provider == "openai":
        return OpenAIClient(llm_config)
    elif provider == "anthropic":
        return AnthropicClient(llm_config)
    elif provider == "local":
        return LocalClient(llm_config)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


@app.command()
def evaluate(
    contract_path: str = typer.Argument(..., help="合同文件路径 (txt / pdf)"),
    config_path: str = typer.Option("config/default.yaml", help="配置文件路径"),
    output_path: str = typer.Option("data/results/output.json", help="结果输出路径"),
    contract_id: str = typer.Option("contract_001", help="合同标识符"),
):
    """评估单份合同的风险"""
    from .pipeline import SaMCGSPipeline
    from .utils.logger import setup_logger

    config = _load_config(config_path)
    setup_logger(config)

    raw_text = Path(contract_path).read_text(encoding="utf-8")
    llm_client = _create_llm_client(config["llm"])

    pipeline = SaMCGSPipeline(config, llm_client)
    result = asyncio.run(pipeline.run(raw_text, contract_id=contract_id))

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"Results saved to {output_path}")


@app.command()
def analyze(
    data_dir: str = typer.Argument(..., help="合同数据目录"),
    config_path: str = typer.Option("config/default.yaml", help="配置文件路径"),
    output_path: str = typer.Option("data/results/analysis.json", help="分析结果路径"),
):
    """批量分析合同的依赖图结构（论文实证分析用）"""
    from .pipeline import SaMCGSPipeline
    from .utils.logger import setup_logger

    config = _load_config(config_path)
    setup_logger(config)

    data_path = Path(data_dir)
    contract_files = sorted(data_path.glob("*.txt")) + sorted(data_path.glob("*.pdf"))

    if not contract_files:
        typer.echo(f"No contract files found in {data_dir}")
        raise typer.Exit(1)

    llm_client = _create_llm_client(config["llm"])
    pipeline = SaMCGSPipeline(config, llm_client)

    all_stats = []
    for fpath in contract_files:
        typer.echo(f"Analyzing {fpath.name}...")
        raw_text = fpath.read_text(encoding="utf-8")
        stats = asyncio.run(pipeline.analyze_structure(raw_text))
        stats["file"] = fpath.name
        all_stats.append(stats)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_stats, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"Analysis saved to {output_path} ({len(all_stats)} contracts)")


@app.command()
def quantlaw(
    data_dir: str = typer.Argument(..., help="QuantLaw 数据根目录 (包含 us/de/us_reg 子目录)"),
    config_path: str = typer.Option("config/default.yaml", help="配置文件路径"),
    output_path: str = typer.Option("data/results/quantlaw_analysis.json", help="结果输出路径"),
    mode: str = typer.Option("analyze", help="'analyze' (仅结构分析) 或 'evaluate' (完整 pipeline)"),
    single_file: str = typer.Option(None, help="单个 .gpickle.gz 文件路径 (优先于 data_dir)"),
):
    """使用 QuantLaw 预构建图数据进行 SCC 分析"""
    from .data.loader import QuantLawLoader
    from .pipeline import SaMCGSPipeline
    from .utils.logger import setup_logger

    config = _load_config(config_path)
    setup_logger(config)

    llm_client = _create_llm_client(config["llm"])
    pipeline = SaMCGSPipeline(config, llm_client)

    loader = QuantLawLoader(data_dir, config)

    if single_file:
        pair = loader.load_single(single_file)
        if not pair:
            typer.echo(f"Failed to load {single_file}")
            raise typer.Exit(1)
        graphs = [pair]
    else:
        graphs = loader.load()

    if not graphs:
        typer.echo(f"No QuantLaw graphs found in {data_dir}")
        raise typer.Exit(1)

    all_results = []
    for graph_id, dep_graph in graphs:
        typer.echo(f"Processing {graph_id} ({len(dep_graph.clauses)} nodes, {len(dep_graph.edges)} edges)...")
        if mode == "analyze":
            stats = pipeline.analyze_graph_structure(dep_graph)
            stats["graph_id"] = graph_id
            all_results.append(stats)
        elif mode == "evaluate":
            result = asyncio.run(pipeline.run_from_graph(dep_graph, graph_id=graph_id))
            all_results.append(json.loads(result.model_dump_json()))
        else:
            typer.echo(f"Unknown mode: {mode}. Use 'analyze' or 'evaluate'.")
            raise typer.Exit(1)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"Results saved to {output_path} ({len(all_results)} graphs)")


def _load_config(path: str) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        logger.warning(f"Config not found at {path}; using defaults")
        return _default_config()
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _default_config() -> dict:
    return {
        "llm": {"provider": "openai", "model": "gpt-4o", "api_key_env": "OPENAI_API_KEY"},
        "parsing": {"max_clause_length": 2000},
        "graph": {"max_clauses_per_batch": 20, "min_dependency_weight": 0.3},
        "scc": {"num_samples": 5, "temperature": 0.7},
        "pruning": {"variance_threshold": 0.01, "influence_threshold": 0.2},
        "mcgs": {"num_rollouts": 100, "ucb_exploration_weight": 1.414},
        "aggregation": {"high_risk_threshold": 0.7, "high_uncertainty_threshold": 0.15},
        "logging": {"level": "INFO"},
    }


if __name__ == "__main__":
    app()
