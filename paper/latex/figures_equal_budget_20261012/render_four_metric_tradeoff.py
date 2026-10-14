#!/usr/bin/env python3
"""Render all 60 confirmed measurements as five directly labelled panels."""
from pathlib import Path
import itertools
import json
import math
import subprocess
import sys

import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
MODELS = ('gpt4o', 'qwen25', 'llama', 'qwen35', 'kimi')
MODEL_LABELS = ('GPT-4o', 'Qwen2.5-72B', 'Llama 3.1-8B', 'Qwen3.5-9B', 'Kimi-VL-A3B')
METHOD_LABELS = {'sa-mcgs': 'SA-MCGS', 'lea': 'LEA', 'full-scc': 'Full-SCC'}
METHODS = ('sa-mcgs', 'lea', 'full-scc')


def bubble_area(percent):
    """Shared zero-origin linear radius; marker area has the squared mapping."""
    assert 0 <= percent <= 100
    return 84.0 * (percent / 100.0) ** 2


def main():
    subprocess.run([sys.executable, str(ROOT/'build_source_data.py')], check=True)
    rows = json.loads((ROOT/'figure_source_data.json').read_text())
    points = {(r['model'], r['method']): r for r in rows}
    assert len(rows) == 15
    assert bubble_area(0) == 0
    assert all(bubble_area(i) < bubble_area(i+1) for i in range(100))
    mpl.rcParams.update({
        'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
        'font.size': 7.0, 'axes.labelsize': 7.0,
        'xtick.labelsize': 6.2, 'ytick.labelsize': 6.2,
        'text.color': '#25333E', 'axes.labelcolor': '#435462',
        'xtick.color': '#78828A', 'ytick.color': '#78828A',
        'axes.spines.top': False, 'axes.spines.right': False,
        'axes.linewidth': 0.5, 'axes.edgecolor': '#B2BCC3',
        'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none',
        'figure.facecolor': 'white', 'savefig.facecolor': 'white',
    })
    cmap = LinearSegmentedColormap.from_list('RootQuality',
        ['#E8F0F4', '#C8DDE8', '#91BED4', '#418EAF', '#124F78'])
    norm = Normalize(vmin=0, vmax=100)
    fig = plt.figure(figsize=(6.2992125984, 2.9527559055), dpi=300)  # 160 × 75 mm.
    coordinates = [(0.078,0.592),(0.390,0.592),(0.702,0.592),
                   (0.078,0.139),(0.390,0.139)]
    offsets = {
        'gpt4o': {'sa-mcgs': (0,10,'center'), 'lea': (-10,0,'right'), 'full-scc': (-9,-6,'right')},
        'qwen25': {'sa-mcgs': (0,10,'center'), 'lea': (10,5,'left'), 'full-scc': (-11,-5,'right')},
        'llama': {'sa-mcgs': (0,12,'center'), 'lea': (10,0,'left'), 'full-scc': (-10,-5,'right')},
        'qwen35': {'sa-mcgs': (0,12,'center'), 'lea': (-10,-5,'right'), 'full-scc': (-10,0,'right')},
        'kimi': {'sa-mcgs': (11,0,'left'), 'lea': (11,0,'left'), 'full-scc': (10,0,'left')},
    }
    axes, labels, geometry, circles = [], [], [], []
    for index, (model, title) in enumerate(zip(MODELS, MODEL_LABELS)):
        x0, y0 = coordinates[index]
        ax = fig.add_axes([x0,y0,0.266,0.322])
        axes.append(ax)
        ax.set_xlim(0,80); ax.set_ylim(0,90)
        ax.set_xticks([0,20,40,60,80]); ax.set_yticks([0,25,50,75])
        ax.tick_params(length=2, width=0.5, pad=3)
        ax.grid(False)
        if index >= 3:
            ax.set_xlabel('Compression (%)', labelpad=5)
        if index in (0,3):
            ax.set_ylabel('Risk-all (%)', labelpad=5)
        else:
            ax.tick_params(labelleft=False)
        ax.text(0,1.105,chr(97+index),transform=ax.transAxes,
                weight='bold',fontsize=8.5,va='center')
        ax.text(0.57,1.105,title,transform=ax.transAxes,
                weight='bold',fontsize=7.6,ha='center',va='center')
        for method in ('full-scc','lea','sa-mcgs'):
            data = points[(model,method)]
            x,y = data['compression_percent'], data['risk_all_percent']
            root, risk_any = data['root_at_3_percent'], data['risk_any_percent']
            assert norm.vmin <= root <= norm.vmax
            area = bubble_area(risk_any)
            linewidth = 1.0 if method == 'sa-mcgs' else 0.7
            ax.scatter([x],[y],s=[area],c=[cmap(norm(root))],
                       edgecolors='#006BA6' if method=='sa-mcgs' else '#81919E',
                       linewidths=linewidth,zorder=3)
            dx,dy,align = offsets[model][method]
            annotation = ax.annotate(METHOD_LABELS[method], (x,y), xytext=(dx,dy),
                textcoords='offset points',ha=align,va='center',fontsize=6.7,
                weight='bold' if method=='sa-mcgs' else 'normal',
                color='#006BA6' if method=='sa-mcgs' else '#536472')
            labels.append((model,method,annotation))
            geometry.append({'panel':chr(97+index),'model':model,'method':method,
                'compression':x,'risk_all':y,'root_at_3':root,'risk_any':risk_any,
                'area_pt2':area,'linewidth_pt':linewidth})
    # The unused grid cell holds the common metric keys.
    fig.text(0.710,0.445,'Root@3 (%)',ha='left',va='center',fontsize=7.0,color='#435462')
    cax=fig.add_axes([0.710,0.394,0.245,0.020])
    cb=fig.colorbar(mpl.cm.ScalarMappable(norm=norm,cmap=cmap),cax=cax,
                    orientation='horizontal',ticks=[0,25,50,75,100])
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=0,pad=3,labelsize=6.0)
    fig.text(0.710,0.285,'Risk-any (%)',ha='left',va='center',fontsize=7.0,color='#435462')
    lax=fig.add_axes([0.709,0.215,0.255,0.052])
    lax.set_xlim(0,1);lax.set_ylim(0,1);lax.axis('off')
    for x,value in zip([0.085,0.410,0.770],[55,75,100]):
        lax.scatter([x],[0.5],s=[bubble_area(value)],facecolors='#EFF3F6',
                    edgecolors='#8293A0',linewidths=0.7,clip_on=False)
        lax.text(x+0.08,0.5,str(value),ha='left',va='center',fontsize=6.0,color='#78828A')
    fig.text(0.710,0.178,'Radius proportional to Risk-any',ha='left',va='center',
             fontsize=6.0,color='#78828A')
    fig.text(0.710,0.131,'Blue outline: SA-MCGS',ha='left',va='center',fontsize=6.3,color='#006BA6')
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    texts=[t for t in fig.findobj(mpl.text.Text) if t.get_visible() and t.get_text().strip()]
    assert min(t.get_fontsize() for t in texts) >= 5
    for text in texts:
        box=text.get_window_extent(renderer)
        assert box.x0>=0 and box.y0>=0 and box.x1<=fig.bbox.x1 and box.y1<=fig.bbox.y1,text.get_text()
    for a,b in itertools.combinations(labels,2):
        assert not a[2].get_window_extent(renderer).overlaps(b[2].get_window_extent(renderer)),(a[:2],b[:2])
    for row in geometry:
        ax=axes[MODELS.index(row['model'])]
        cx,cy=ax.transData.transform((row['compression'],row['risk_all']))
        radius=(math.sqrt(row['area_pt2'])/2+row['linewidth_pt']/2)*fig.dpi/72
        assert ax.bbox.x0<=cx-radius and cx+radius<=ax.bbox.x1,(row,'x clipping')
        assert ax.bbox.y0<=cy-radius and cy+radius<=ax.bbox.y1,(row,'y clipping')
        circles.append((row['model'],row['method'],cx,cy,radius))
    for a,b in itertools.combinations(circles,2):
        if a[0]==b[0]:
            assert math.hypot(a[2]-b[2],a[3]-b[3])>a[4]+b[4],(a[:2],b[:2],'bubble overlap')
    for model,method,label in labels:
        box=label.get_window_extent(renderer)
        for circle in circles:
            if circle[0]!=model:
                continue
            dx=max(box.x0-circle[2],0,circle[2]-box.x1)
            dy=max(box.y0-circle[3],0,circle[3]-box.y1)
            assert math.hypot(dx,dy)>circle[4],(model,method,circle[1],'label touches bubble')
    fig.savefig(ROOT/'equal_budget_tradeoff.pdf')
    fig.savefig(ROOT/'equal_budget_tradeoff.svg')
    fig.savefig(ROOT/'equal_budget_tradeoff.png',dpi=600)
    qa=ROOT/'qa'; qa.mkdir(exist_ok=True)
    with Image.open(ROOT/'equal_budget_tradeoff.png') as image:
        scale=image.width/fig.bbox.width
        for index,ax in enumerate(axes):
            bbox=ax.get_tightbbox(renderer).expanded(1.025,1.025)
            crop=(max(0,round(bbox.x0*scale)),max(0,round(image.height-bbox.y1*scale)),
                  min(image.width,round(bbox.x1*scale)),min(image.height,round(image.height-bbox.y0*scale)))
            panel=image.crop(crop)
            panel.resize((round(panel.width/2),round(panel.height/2)),Image.Resampling.LANCZOS).save(qa/f'panel_{chr(97+index)}.png')
        image.resize((1280,600),Image.Resampling.LANCZOS).save(qa/'screen.png')
        ImageOps.grayscale(image).save(qa/'grayscale.png')
    (qa/'geometry.json').write_text(json.dumps(geometry,indent=2)+'\n')
    audit={'size_mm':[160,75],'data_rows':15,'metric_values':60,
        'source_validation_passed':True,'minimum_source_font_pt':min(t.get_fontsize() for t in texts),
        'all_labels_within_canvas':True,'label_collisions':0,'bubble_collisions':0,
        'label_bubble_collisions':0,'clipped_bubbles':0,
        'color_scale':[0,100],'bubble_mapping':'area_pt2 = 84 * (Risk-any percent / 100)^2',
        'uncertainty_display':'omitted as requested; unchanged aggregation retained internally',
        'exports':['PDF','SVG with editable text','600 dpi PNG']}
    (qa/'render_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    plt.close(fig)
    print('Figure rendered and geometry checks passed.')


if __name__ == '__main__':
    main()
