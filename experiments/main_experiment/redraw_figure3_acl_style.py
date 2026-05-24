#!/usr/bin/env python3
"""Regenerate the paper's Figure 3 with the ACL-style compact layout."""
from __future__ import annotations

import build_paper_assets as assets


def main() -> None:
    records = assets.load_current_records()
    assets.create_main_results_composite_figure(records)


if __name__ == "__main__":
    main()
