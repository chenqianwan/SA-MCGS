#!/usr/bin/env python3
"""Redraw manuscript data figures, including the selected paired-case view, from frozen summaries."""
from pathlib import Path
import subprocess
import sys


def main():
    folder = Path(__file__).resolve().parent
    for name in ("redraw_five_model_figures.py", "redraw_scale_gain_heatmaps.py", "redraw_paired_case_outcomes.py", "redraw_budget_case_nature.py"):
        subprocess.run([sys.executable, str(folder / name)], check=True)


if __name__ == "__main__":
    main()
