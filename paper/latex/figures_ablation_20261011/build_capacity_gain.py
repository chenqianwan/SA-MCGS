#!/usr/bin/env python3
"""Reproduce all twelve paired Full-minus-Locked capacity comparisons."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Rectangle
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_VALUES = (REPO / '2026NAACL/SA-MCGS/experiments/component_mechanisms_20261010'
                  / 'EXPERIMENT_TABLES_20261011_values.json')
MODELS = [('llama', 'Llama 3.1-8B'), ('qwen35', 'Qwen3.5-9B'), ('kimi', 'Kimi-VL-A3B')]
CAPACITIES = ['0.25', '0.35', '0.45', '0.6']
WIDTH_MM, HEIGHT_MM = 85, 32


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def make_source(values_path):
    original = json.loads(values_path.read_text())
    cells = []
    for model, label in MODELS:
        for cap in CAPACITIES:
            group = original['tables']['capacities'][model][cap]
            assert len(group['case_uids']) == 80 and len(set(group['case_uids'])) == 80
            full, locked = group['rows']['full'], group['rows']['locked-matched-k']
            assert abs(full['compression'] - locked['compression']) < 1e-10
            cells.append({'model': model, 'model_label': label, 'capacity_ratio': float(cap),
                          'n_cases': 80, 'n_source_sccs': 20,
                          'full_risk_all_pct': full['risk_all'],
                          'locked_risk_all_pct': locked['risk_all'],
                          'gain_pp': full['risk_all'] - locked['risk_all'],
                          'matched_compression_pct': full['compression'],
                          'case_uids': group['case_uids']})
    assert len(cells) == 12
    return {'schema_version': 'capacity_gain.source.v1',
            'values_sha256': hashlib.sha256(values_path.read_bytes()).hexdigest(),
            'underlying_case_metrics_sha256': original['source_sha256'],
            'metric': 'Full minus locked-matched-k Risk-all, percentage points',
            'design': 'Shared Full search trajectories, 60 completed rollouts, 80 cases per model; '
                      'each comparison matches the Full endpoint actual core size at that capacity.',
            'sampling': 'One trajectory per model-case; four injected variants per source SCC.',
            'uncertainty': 'Descriptive paired differences; no repeated-run variability or significance claim.',
            'default_capacity_ratio': 0.45, 'color_limits_pp': [0, 30], 'cells': cells}


def luminance(rgb):
    rgb = np.asarray(rgb)
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    return float(np.dot(linear, [.2126, .7152, .0722]))


def render(data):
    # Contract: quantitative grid, all 12 requested values, paired retention
    # gains across capacities; zero anchored scale and no significance encoding.
    plt.rcParams.update({'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
        'font.size': 7, 'axes.labelsize': 7, 'xtick.labelsize': 7,
        'ytick.labelsize': 7, 'pdf.fonttype': 42, 'svg.fonttype': 'none',
        'axes.linewidth': .5, 'savefig.facecolor': 'white',
        'figure.facecolor': 'white', 'text.color': '#222222'})
    values = np.array([c['gain_pp'] for c in data['cells']]).reshape(3, 4)
    assert values.shape == (3, 4) and np.isfinite(values).all()
    assert (values >= 0).all() and (values <= 30).all()
    cmap = LinearSegmentedColormap.from_list('SA_gain_blue',
        [(0, '#ffffff'), (.33, '#d2e6f1'), (.67, '#70afd2'), (1, '#0072b2')])
    norm = Normalize(vmin=0, vmax=30)
    fig = plt.figure(figsize=(WIDTH_MM / 25.4, HEIGHT_MM / 25.4))
    ax = fig.add_axes([.292, .25, .675, .52])
    image = ax.imshow(values, cmap=cmap, norm=norm, aspect='auto', interpolation='none',
                      extent=(0, 4, 3, 0))
    ax.set_xticks(np.arange(4) + .5, ['25%', '35%', '45%', '60%'])
    ax.xaxis.tick_top()
    ax.tick_params(axis='x', length=0, pad=4)
    ax.set_yticks(np.arange(3) + .5, [label for _, label in MODELS])
    ax.tick_params(axis='y', length=0, pad=5)
    ax.get_xticklabels()[2].set_fontweight('bold')
    ax.set_xticks(np.arange(5), minor=True)
    ax.set_yticks(np.arange(4), minor=True)
    ax.grid(which='minor', color='white', linewidth=1.0)
    ax.tick_params(which='minor', length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.text(.63, .957, 'Core capacity', ha='center', va='center', fontsize=7)
    text_checks = []
    for row in range(3):
        for column in range(4):
            value = values[row, column]
            lum = luminance(cmap(norm(value))[:3])
            black_contrast, white_contrast = (lum + .05) / .05, 1.05 / (lum + .05)
            color = '#ffffff' if white_contrast > black_contrast else '#111111'
            artist = ax.text(column + .5, row + .5, f'+{value:.2f}', ha='center',
                             va='center', color=color, fontsize=7.2)
            text_checks.append((row, column, artist))
    # The outline denotes the prespecified default capacity, not significance.
    ax.add_patch(Rectangle((2.025, .025), .95, 2.95, fill=False,
                          edgecolor='#3c5665', linewidth=.65, zorder=5))
    cax = fig.add_axes([.485, .129, .455, .052])
    bar = fig.colorbar(image, cax=cax, orientation='horizontal', ticks=[0, 10, 20, 30])
    bar.outline.set_linewidth(.35)
    bar.outline.set_edgecolor('#8194a0')
    bar.ax.tick_params(labelsize=6, length=2, width=.4, pad=1.5)
    fig.text(.245, .155, 'Risk-all gain (pp)', ha='center', va='center', fontsize=7)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for row, column, artist in text_checks:
        box = artist.get_window_extent(renderer)
        p0 = ax.transData.transform((column, row))
        p1 = ax.transData.transform((column + 1, row + 1))
        assert box.width < abs(p1[0]-p0[0]) - 4
        assert box.height < abs(p1[1]-p0[1]) - 4
    for artist in [*ax.get_xticklabels(), *ax.get_yticklabels(), *fig.texts,
                   *bar.ax.get_xticklabels()]:
        box = artist.get_window_extent(renderer)
        assert box.x0 >= 0 and box.y0 >= 0
        assert box.x1 <= fig.bbox.x1 and box.y1 <= fig.bbox.y1
    # Preserve exact physical dimensions; do not tight-crop exports.
    fig.savefig(HERE/'capacity_gain.pdf', dpi=600)
    fig.savefig(HERE/'capacity_gain.svg', dpi=600)
    fig.savefig(HERE/'capacity_gain.png', dpi=600)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--values', type=Path, default=DEFAULT_VALUES)
    parser.add_argument('--source-data', type=Path,
                        help='Rebuild solely from the supplied portable source_data.json')
    args = parser.parse_args()
    data = json.loads(args.source_data.read_text()) if args.source_data else make_source(args.values)
    write_json(HERE/'source_data.json', data)
    render(data)
    print(json.dumps({'status': 'rendered', 'cells': len(data['cells']),
                      'dimensions_mm': [WIDTH_MM, HEIGHT_MM], 'dpi': 600}))


if __name__ == '__main__':
    main()
