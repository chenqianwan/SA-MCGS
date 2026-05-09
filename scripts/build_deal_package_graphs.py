"""Build graph-grpo-lex fullgraphs for cross-contract deal packages.

Wraps replicate_grpo_lex.py to process specific contract groups.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.replicate_grpo_lex import run_pipeline  # noqa: E402

DEAL_PACKAGES = {
    "NETGEAR": [
        "NETGEAR,INC_04_21_2003-EX-10.16-DISTRIBUTOR AGREEMENT.txt",
        "NETGEAR,INC_04_21_2003-EX-10.16-AMENDMENT TO THE DISTRIBUTOR AGREEMENT BETWEEN INGRAM MICRO AND NETGEAR.txt",
        "NETGEAR,INC_04_21_2003-EX-10.16- AMENDMENT #2 TO THE DISTRIBUTION AGREEMENT.txt",
    ],
    "GpaqAcquisition": [
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.8_11951679_EX-10.8_Service Agreement.txt",
    ],
    "Reynolds": [
        "ReynoldsConsumerProductsInc_20191115_S-1_EX-10.18_11896469_EX-10.18_Supply Agreement.txt",
        "ReynoldsConsumerProductsInc_20200121_S-1A_EX-10.22_11948918_EX-10.22_Service Agreement.txt",
    ],
    "BellringBrands": [
        "BellringBrandsInc_20190920_S-1_EX-10.12_11817081_EX-10.12_Manufacturing Agreement1.txt",
        "BellringBrandsInc_20190920_S-1_EX-10.12_11817081_EX-10.12_Manufacturing Agreement2.txt",
        "BellringBrandsInc_20190920_S-1_EX-10.12_11817081_EX-10.12_Manufacturing Agreement3.txt",
        "BellringBrandsInc_20190920_S-1_EX-10.12_11817081_EX-10.12_Manufacturing Agreement4.txt",
    ],
    "BioAmber": [
        "BIOAMBERINC_04_10_2013-EX-10.34-DEVELOPMENT AGREEMENT (1).txt",
        "BIOAMBERINC_04_10_2013-EX-10.34-DEVELOPMENT AGREEMENT - First Amendment.txt",
    ],
}

TXT_DIR = "data/cuad/CUAD_v1/CUAD_v1/full_contract_txt"
OUTPUT_DIR = "data/cuad/grpo_lex_replicated"


async def main():
    api_key = os.environ.get("XHUB_API_KEY", "")
    if not api_key:
        print("ERROR: set XHUB_API_KEY")
        sys.exit(1)

    all_files = []
    for group, files in DEAL_PACKAGES.items():
        for f in files:
            fp = Path(TXT_DIR) / f
            if fp.exists():
                all_files.append(f)
            else:
                print(f"MISSING: {f}")

    print(f"Total contracts to build: {len(all_files)}")

    # Temporarily override DEFAULT_CONTRACTS in replicate_grpo_lex
    import scripts.replicate_grpo_lex as rgl
    rgl.DEFAULT_CONTRACTS = all_files

    await run_pipeline(
        txt_dir=TXT_DIR,
        output_dir=OUTPUT_DIR,
        model="deepseek-chat",
        temperature=0.0,
        max_tokens=4096,
        concurrency=4,
        rpm_limit=30,
        num_contracts=len(all_files),
        skip_llm=False,
        api_key=api_key,
        base_url="https://api3.xhub.chat/v1",
    )


if __name__ == "__main__":
    asyncio.run(main())
