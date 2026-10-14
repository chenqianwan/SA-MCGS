"""Render all observed pilot metrics; no inference, sampling, or API calls."""
from pathlib import Path
import json
import hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / 'metrics.json').read_text())
GROUPS = DATA['groups']
ROWS = DATA['rows']
IDS = ['sa-mcgs:final', 'lea:first', 'lea:final', 'full-scc:first', 'full-scc:final']
LABELS = ['SA-MCGS', 'LEA 首次', 'LEA 选优', 'Full-SCC 首次', 'Full-SCC 选优']
DOMAINS = ['debian', 'sec_ex21', 'bgb', 'cuad']
DOMAIN_LABELS = ['Debian', 'SEC', 'BGB', 'CUAD']
COLORS = ['#17677A', '#96B4CC', '#366E9A', '#C4B3CE', '#855E96']
INK = '#233641'
GRAY = '#647580'
CMAP = LinearSegmentedColormap.from_list('Coverage', ['#F2F5F7', '#C5DFE4', '#6AA9B6', '#21687A'])
assert [g['id'] for g in GROUPS] == IDS
assert DATA['n_cases'] == 4 and len(ROWS) == 20
LOOKUP = {(r['group_id'], r['domain']): r for r in ROWS}
assert len(LOOKUP) == 20

plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial Unicode MS', 'DejaVu Sans'],
    'font.size': 10, 'axes.labelsize': 9, 'xtick.labelsize': 8.5,
    'ytick.labelsize': 9, 'axes.titlesize': 11,
    'axes.spines.right': False, 'axes.spines.top': False,
    'axes.linewidth': .6, 'axes.edgecolor': '#BBC7CE',
    'text.color': INK, 'axes.labelcolor': GRAY,
    'xtick.color': GRAY, 'ytick.color': INK,
    'axes.unicode_minus': False,
    'legend.frameon': False, 'pdf.fonttype': 42,
    'svg.fonttype': 'none', 'savefig.facecolor': 'white',
})


def top_text(fig, title, subtitle):
    fig.text(.045, .963, title, fontsize=17, fontweight='bold', va='top')
    fig.text(.045, .913, subtitle, fontsize=9.5, color=GRAY, va='top')


def panel_title(fig, x, y, letter, title):
    fig.text(x, y, letter, fontsize=12, fontweight='bold', va='bottom')
    fig.text(x + .026, y, title, fontsize=11, fontweight='bold', va='bottom')


def matrix(ax, values, annotations, column_labels, row_labels=True, top=True):
    values = np.asarray(values, dtype=float)
    assert values.shape[0] == 5 and np.isfinite(values).all()
    assert ((values >= 0) & (values <= 1)).all()
    ax.imshow(values, cmap=CMAP, vmin=0, vmax=1, aspect='auto')
    ax.set_xticks(range(values.shape[1]), column_labels)
    ax.set_yticks(range(5), LABELS if row_labels else [''] * 5)
    ax.tick_params(axis='both', length=0, pad=8)
    if top:
        ax.xaxis.tick_top()
    for y in range(5):
        for x in range(values.shape[1]):
            ax.text(x, y, annotations[y][x], ha='center', va='center',
                    color='white' if values[y, x] >= .8 else INK,
                    fontsize=9, linespacing=1.3)
    for x in np.arange(-.5, values.shape[1], 1):
        ax.axvline(x, color='white', lw=1.5)
    for y in np.arange(-.5, 5, 1):
        ax.axhline(y, color='white', lw=1.5)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for text, color in zip(ax.get_yticklabels(), COLORS):
        text.set_color(color)
    return ax


def effectiveness():
    fig = plt.figure(figsize=(220 / 25.4, 193 / 25.4))
    top_text(fig, '风险端点覆盖与完整证据覆盖，给出不同的排序',
             'GPT-4o · 四领域各 1 个注入案例 · 首次与选优按相同案例配对 · 深色表示更高覆盖 / 更靠前排名')
    keys = ['root_at_1', 'root_at_3', 'risk_any', 'risk_all', 'endpoint_recall', 'evidence_all']
    headers = ['根因第 1 名\nRoot@1', '根因前 3 名\nRoot@3', '任一风险端点\nRisk-any',
               '全部风险端点\nRisk-all', '风险端点召回\n每例均值', '全部预设证据*\n含桥接节点']
    values = [[g[k] for k in keys] for g in GROUPS]
    annotations = []
    for g in GROUPS:
        annotations.append([f'{g[k] * 100:g}%' if k == 'endpoint_recall'
                            else f'{round(g[k] * 4)}/4\n{g[k] * 100:g}%' for k in keys])
    panel_title(fig, .045, .847, 'a', '命中与覆盖：每个方法均保留全部 4 例')
    matrix(fig.add_axes([.22, .493, .74, .286]), values, annotations, headers)

    panel_title(fig, .045, .388, 'b', '根因的实际排名（越小越好）')
    ranks = [[LOOKUP[(gid, d)]['root_rank'] for d in DOMAINS] for gid in IDS]
    assert all(isinstance(rank, int) and rank >= 1 for row in ranks for rank in row)
    matrix(fig.add_axes([.22, .145, .34, .19]),
           [[1 / r for r in row] for row in ranks],
           [[str(r) for r in row] for row in ranks], DOMAIN_LABELS)
    panel_title(fig, .603, .388, 'c', '预设证据节点：保留数 / 总数')
    kept = [[LOOKUP[(gid, d)]['evidence_kept'] for d in DOMAINS] for gid in IDS]
    totals = [[LOOKUP[(gid, d)]['evidence_total'] for d in DOMAINS] for gid in IDS]
    matrix(fig.add_axes([.62, .145, .34, .19]),
           [[a / b for a, b in zip(aa, bb)] for aa, bb in zip(kept, totals)],
           [[f'{a}/{b}' for a, b in zip(aa, bb)] for aa, bb in zip(kept, totals)],
           DOMAIN_LABELS, row_labels=False)
    fig.text(.045, .079, '* 新增离线诊断：SEC、BGB 各含 1 个预设桥接节点；节点齐全不代表关系或论证正确。',
             fontsize=8.5, color=GRAY)
    fig.text(.045, .047, '仅描述这 4 例；无显著性推断。其他节点未全量标负，因此不将其直接算作误报。',
             fontsize=8.5, color=GRAY)
    return fig


def row_axis(ax, show_labels=True):
    ax.set_yticks(range(5), LABELS if show_labels else [''] * 5)
    ax.set_ylim(4.65, -.65)
    ax.tick_params(axis='y', length=0, pad=8)
    ax.spines['left'].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis='x', color='#E7EDF0', lw=.65)
    for text, color in zip(ax.get_yticklabels(), COLORS):
        text.set_color(color)


def resources():
    fig = plt.figure(figsize=(220 / 25.4, 202 / 25.4))
    top_text(fig, '重试消耗更多；实际 token 预算仍未拉齐',
             '首次行是完整选优流程的子集，费用不可重复相加 · 四个面板采用相同行序')
    axa = fig.add_axes([.22, .57, .32, .25])
    axb = fig.add_axes([.65, .57, .31, .25])
    axc = fig.add_axes([.22, .185, .32, .25])
    axd = fig.add_axes([.65, .185, .31, .25])
    panel_title(fig, .045, .86, 'a', '总输入 / 输出 token')
    panel_title(fig, .605, .86, 'b', '费用估值与 API 调用数')
    panel_title(fig, .045, .48, 'c', '每例 API 请求时间跨度')
    panel_title(fig, .605, .48, 'd', '节点压缩率与平均输出大小')
    y = np.arange(5)
    prompt = np.array([g['prompt_tokens'] for g in GROUPS]) / 10000
    completion = np.array([g['completion_tokens'] for g in GROUPS]) / 10000
    total = prompt + completion
    assert np.allclose(total * 10000, [g['total_tokens'] for g in GROUPS])
    axa.barh(y, prompt, height=.55, color='#B5D1DC', label='输入')
    axa.barh(y, completion, left=prompt, height=.55, color='#397C91', label='输出')
    for i, value in enumerate(total):
        axa.text(value + 1, i, f'{value:.1f}', va='center', fontsize=9)
    axa.set_xlim(0, 63)
    axa.set_xticks([0, 20, 40, 60])
    axa.set_xlabel('总 token（万）')
    axa.legend(loc='upper left', bbox_to_anchor=(-.03, 1.12), ncol=2,
               handlelength=1, handletextpad=.35, columnspacing=1, fontsize=8.5)
    row_axis(axa)

    costs = np.array([g['cost_usd'] for g in GROUPS])
    axb.barh(y, costs, color=COLORS, height=.55)
    for i, g in enumerate(GROUPS):
        axb.text(g['cost_usd'] + .07, i, f"${g['cost_usd']:.2f}  /  {g['calls']} 次",
                 va='center', fontsize=8.5)
    axb.set_xlim(0, 4.15)
    axb.set_xticks([0, 1, 2, 3, 4])
    axb.set_xlabel('费用（USD） / 标签含调用数')
    row_axis(axb, False)

    elapsed_values = [[LOOKUP[(gid, d)]['elapsed_sec'] / 60 for d in DOMAINS] for gid in IDS]
    max_elapsed = max(max(row) for row in elapsed_values)
    limit = max_elapsed * 1.27
    offset = np.array([-.15, -.05, .05, .15])
    for i, values in enumerate(elapsed_values):
        axc.scatter(values, i + offset, color='#AAB8C0', s=14, zorder=3)
        avg = GROUPS[i]['mean_elapsed_sec'] / 60
        assert np.isclose(avg, np.mean(values))
        axc.scatter([avg], [i], color=COLORS[i], s=42, marker='D', zorder=4)
        axc.text(limit * .985, i, f'{avg:.2f}', ha='right', va='center', fontsize=9)
    axc.set_xlim(0, limit)
    axc.set_xlabel('分钟；右侧数字为 4 例均值')
    row_axis(axc)

    for i, gid in enumerate(IDS):
        values = [LOOKUP[(gid, d)]['compression'] * 100 for d in DOMAINS]
        avg = GROUPS[i]['compression'] * 100
        axd.scatter(values, i + offset, color='#AAB8C0', s=14, zorder=3)
        axd.scatter([avg], [i], color=COLORS[i], s=42, marker='D', zorder=4)
        axd.text(137, i, f"{avg:.1f}%\nH={GROUPS[i]['mean_output_n']:.2f}",
                 ha='right', va='center', fontsize=8.5, linespacing=1.15)
    axd.set_xlim(0, 139)
    axd.set_xticks([0, 25, 50, 75, 100])
    axd.set_xlabel('压缩率（%）；H 为保留节点数')
    row_axis(axd, False)
    fig.text(.045, .112, '灰点 = 全部 4 个案例；菱形 = 每例均值。压缩率高表示输出更小，须与证据保留一起看。',
             fontsize=8.5, color=GRAY)
    fig.text(.045, .078, '每例每路上限 16 万 token；CUAD LEA 只生成 1 个候选。费用含评选及可见重试。',
             fontsize=8.5, color=GRAY)
    fig.text(.045, .044, '时间按首次请求到最后响应计，各方法并发；首次耗时是完整流程子集，不能相加作为总时长。',
             fontsize=8.5, color=GRAY)
    return fig


def main():
    figures = [('fig01_core_outcomes', effectiveness()), ('fig02_cost_and_output', resources())]
    with PdfPages(ROOT / 'core_metrics_charts.pdf') as document:
        for name, fig in figures:
            fig.savefig(ROOT / (name + '.png'), dpi=300)
            fig.savefig(ROOT / (name + '.pdf'))
            fig.savefig(ROOT / (name + '.svg'))
            document.savefig(fig)
    geometry = []
    for name, fig in figures:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        bounds = fig.bbox
        clipped = []
        for artist in fig.findobj(matplotlib.text.Text):
            if not artist.get_visible() or not artist.get_text():
                continue
            box = artist.get_window_extent(renderer)
            if box.x0 < -1 or box.y0 < -1 or box.x1 > bounds.x1 + 1 or box.y1 > bounds.y1 + 1:
                clipped.append(artist.get_text())
        geometry.append({'figure': name, 'outside_canvas_text': clipped})
        assert not clipped, (name, clipped)
        plt.close(fig)
    manifest = {
        'metrics_sha256': hashlib.sha256((ROOT / 'metrics.json').read_bytes()).hexdigest(),
        'plot_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'case_rows': len(ROWS), 'case_exclusions': 0,
        'geometry': geometry,
        'uncertainty': 'All four selected cases shown; descriptive pilot, no inferential error bars.',
    }
    (ROOT / 'plot_checks.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'figures': [name for name, _ in figures], 'case_rows': len(ROWS)}))


if __name__ == '__main__':
    main()
