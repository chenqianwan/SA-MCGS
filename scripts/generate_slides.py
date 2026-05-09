"""
Generate presentation slides from the SA-MCGS paper using the SlidesAI (Alai) API.

Usage:
    python scripts/generate_slides.py --api-key YOUR_API_KEY
    
    Or set the environment variable:
    export SLIDESAI_API_KEY=YOUR_API_KEY
    python scripts/generate_slides.py

Get your API key at: https://app.getalai.com (Account Settings)
"""

import argparse
import json
import os
import time
import urllib.request
import urllib.error

API_BASE = "https://slides-api.getalai.com/api/v1"

PAPER_CONTENT = """
# Beyond Linear Prompting: Monte Carlo Graph Search as a System-2 Reasoning Framework for LLMs

## The Problem: LLMs Are Structurally Blind

Large Language Models excel at fluent generation but are fundamentally "System-1" reasoners — fast and intuitive, but structurally blind.

When tasks involve complex dependency graphs with cycles, LLMs fail silently, hallucinating coherent but logically flawed conclusions.

Key evidence:
- "Lost in the Middle" phenomenon: transformer attention degrades for mid-document information
- Chain-of-Thought helps sequential reasoning but cannot handle branching or cyclic logic
- Even GPT-4 achieves modest F1 on tasks requiring cross-document structural consistency

## Our Solution: SA-MCGS — Search-Augmented Reasoning

SA-MCGS (Structure-Aware Monte Carlo Graph Search) augments LLMs with "System-2" capabilities — deliberate, search-based exploration of structured problem spaces.

Core insight: Just as AlphaGo combined neural network intuition with MCTS to achieve superhuman Go play, LLMs need search augmentation for complex analytical tasks.

Architecture: LLM provides fast "System-1" evaluation + Graph Search provides deliberate "System-2" reasoning.

## The Four-Phase Framework

### Phase 1: Problem Decomposition → Graph Construction
- Transform unstructured input into a dependency graph
- Five canonical dependency types: Defines, Constrains, Triggers, Modifies, References
- Two-pass extraction: explicit references + implicit semantic dependencies

### Phase 2: Bottleneck Identification → SCC Detection
- Apply Tarjan's algorithm to find Strongly Connected Components (SCCs)
- SCCs are "logic kernels" where circular dependencies create reasoning bottlenecks
- Focus expensive search operations exclusively on these bottlenecks

### Phase 3: Monte Carlo Graph Search (MCGS)
- AlphaGo-inspired search with UCB selection + Dirichlet noise
- Transposition Tables for handling cyclic graphs efficiently
- Virtual Loss for parallel LLM evaluation
- Semantic Pruning (TACS) reduces search space by up to 75%

### Phase 4: Statistical Calibration → Online Conformal Prediction
- Transforms noisy LLM outputs into reliable verdicts
- Maintains pre-specified False Discovery Rate
- Domain-agnostic: can wrap any search-augmented reasoning system

## Case Study: Legal Contract Risk Detection

Why legal contracts? They represent an ideal testbed:
- Rich in cyclic dependencies between clauses
- Verifiable ground truth (contradictions, omissions, inconsistencies)
- Known LLM failures documented in literature

Experimental setup: 141 runs across 5 commercial contracts from CUAD dataset, with CLAUSE benchmark defect injections.

## Key Results: SA-MCGS vs. LLM Baselines

### Detection Performance (F1 Score)

| Method | Structural Flaws | Omissions | Inconsistencies |
|--------|:---:|:---:|:---:|
| LLaMA-3.3 | 0.15 | 0.50 | 0.55 |
| GPT-4o-mini | 0.47 | 0.45 | 0.44 |
| Gemini-2.5 | 0.47 | 0.64 | 0.64 |
| **SA-MCGS** | **1.00** | **1.00** | **1.00** |

SA-MCGS achieves 100% detection within SCC scope — the best LLM only reaches 47% on structural flaws.

## The Scaling Collapse of Pure LLM Reasoning

A critical finding for the AI community:

| Scale (Clauses) | Type A Detection | Type C Detection | Verdict |
|---|:---:|:---:|---|
| 5–50 | 100% | 0–40% | LLM sufficient |
| 60–80 | 80–100% | 0% | Tipping point |
| 100–150 | 60–80% | 0% | Search needed |
| 200+ | 0–20% | 0% | SA-MCGS mandatory |

Beyond 60–80 interdependent elements, pure LLM reasoning catastrophically fails. SA-MCGS maintains stable performance at 500+ clauses.

## The Magnifier Effect: Search Friction as Signal

Even for subtle defects (Type C), the search tree itself encodes diagnostic information:

| Defect Type | Direct Alarms | Subgraph Expansion |
|---|:---:|:---:|
| Type A (Explicit) | 2.4 | +5.8 nodes |
| Type B (Omission) | 2.0 | +4.5 nodes |
| Type C (Subtle) | 0.8 | **+8.4 nodes (300%+)** |
| Clean Baseline | 0.0 | 0 nodes |

The search process reveals information that single-pass evaluation cannot detect.

## Beyond Law: A General Reasoning Pattern

The SA-MCGS framework generalizes to any domain with complex dependencies:

- **Code Auditing**: Circular imports, mutual recursion, callback chains
- **Scientific Literature**: Citation graphs with conflicting findings
- **Knowledge Graphs**: Cyclic relationships requiring consistency checking
- **Multi-Agent Systems**: Agent interaction dependency verification

Design pattern: LLM as System-1 + Search as System-2 = Reliable AI Reasoning

## Key Takeaways

1. **Structured search is necessary, not optional** — LLMs alone fail on cyclic reasoning tasks
2. **Topological focus matters** — SCC detection concentrates search on the hardest 5% of the problem
3. **The search process is informative** — Friction patterns provide secondary signals invisible to single-pass inference
4. **The framework is domain-agnostic** — Legal contracts are just one instantiation of this System-2 reasoning paradigm

The future of reliable AI reasoning: fast LLM intuition + deliberate, structure-aware search.
"""


def api_request(endpoint: str, api_key: str, method: str = "GET", data: dict = None, retries: int = 3):
    url = f"{API_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(retries):
        if data:
            req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method=method)
        else:
            req = urllib.request.Request(url, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"API Error {e.code}: {body}")
            raise
        except (urllib.error.URLError, ConnectionResetError) as e:
            if attempt < retries - 1:
                print(f"Network error ({e}), retrying in 5s...")
                time.sleep(5)
                continue
            raise


def generate_presentation(api_key: str):
    print("Submitting presentation generation request...")

    payload = {
        "input_text": PAPER_CONTENT,
        "additional_instructions": (
            "This is an academic research paper presentation for a university course. "
            "Use a clean, professional, modern style suitable for a CS/AI research talk. "
            "Emphasize the key results with clear data tables and comparisons. "
            "Use a logical flow: Problem → Approach → Framework → Case Study → Results → Implications."
        ),
        "export_formats": ["link", "pdf", "ppt"],
        "presentation_options": {
            "title": "Beyond Linear Prompting: Monte Carlo Graph Search as a System-2 Reasoning Framework for LLMs",
            "slide_range": "6-10",
        },
        "text_options": {
            "language": "English (US)",
        },
        "image_options": {
            "include_ai_images": True,
            "include_web_images": False,
            "style": "realistic",
        },
    }

    result = api_request("/generations", api_key, method="POST", data=payload)
    generation_id = result["generation_id"]
    print(f"Generation ID: {generation_id}")
    return generation_id


def poll_status(generation_id: str, api_key: str, max_wait: int = 600):
    print("Waiting for generation to complete...")
    start = time.time()
    poll_interval = 5

    while time.time() - start < max_wait:
        result = api_request(f"/generations/{generation_id}", api_key)
        status = result["status"]
        elapsed = int(time.time() - start)
        print(f"  [{elapsed}s] Status: {status}")

        if status == "completed":
            return result
        elif status == "failed":
            error = result.get("error", "Unknown error")
            raise RuntimeError(f"Generation failed: {error}")

        time.sleep(poll_interval)

    raise TimeoutError(f"Generation did not complete within {max_wait}s")


def download_file(url: str, output_path: str):
    print(f"Downloading to {output_path}...")
    urllib.request.urlretrieve(url, output_path)
    print(f"  Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate slides from SA-MCGS paper")
    parser.add_argument("--api-key", default=os.environ.get("SLIDESAI_API_KEY"),
                        help="SlidesAI (Alai) API key. Or set SLIDESAI_API_KEY env var.")
    args = parser.parse_args()

    if not args.api_key:
        print("Error: API key required.")
        print("  Get one at: https://app.getalai.com (Account Settings)")
        print("  Then run: python scripts/generate_slides.py --api-key YOUR_KEY")
        print("  Or: export SLIDESAI_API_KEY=YOUR_KEY")
        return

    output_dir = os.path.join(os.path.dirname(__file__), "..", "docs", "slides")
    os.makedirs(output_dir, exist_ok=True)

    generation_id = generate_presentation(args.api_key)
    result = poll_status(generation_id, args.api_key)

    print("\nGeneration complete!")
    formats = result.get("formats", {})

    if "link" in formats and formats["link"].get("url"):
        print(f"\nOnline link: {formats['link']['url']}")

    if "pdf" in formats and formats["pdf"].get("url"):
        pdf_path = os.path.join(output_dir, "SA-MCGS_presentation.pdf")
        download_file(formats["pdf"]["url"], pdf_path)

    if "ppt" in formats and formats["ppt"].get("url"):
        ppt_path = os.path.join(output_dir, "SA-MCGS_presentation.pptx")
        download_file(formats["ppt"]["url"], ppt_path)

    print("\nDone! Files saved to docs/slides/")


if __name__ == "__main__":
    main()
