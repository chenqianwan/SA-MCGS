"""Shared vector primitives for original, mechanism-only manuscript diagrams."""
from pathlib import Path
import json
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, FancyBboxPatch, FancyArrowPatch, Polygon
from matplotlib.colors import to_rgba

OUT = Path(__file__).resolve().parent
Y_SCALE = 84 / 96  # Compress spacing only; point sizes stay physically fixed.
INK = '#242424'
GRAY = '#737373'
LIGHT = '#C4C4C4'
FAINT = '#E7E7E7'
BLUE = '#0072B2'
BLUE_FILL = '#CFE4F0'
ORANGE = '#D55E00'
ORANGE_FILL = '#F4DCC7'
PAIR = '#444444'
METHOD_COLORS = {'full-scc': GRAY, 'lea': ORANGE, 'treemcts': INK, 'sa-mcgs': BLUE}
plt.rcParams.update({
    'font.family':'sans-serif', 'font.sans-serif':['Arial','Helvetica','DejaVu Sans'],
    'font.size':7.2, 'mathtext.fontset':'stix',
    'svg.fonttype':'none', 'pdf.fonttype':42, 'ps.fonttype':42,
    'axes.linewidth':0.55, 'savefig.facecolor':'white',
    'text.color':INK, 'axes.edgecolor':INK,
})

def canvas(height=96):
    fig=plt.figure(figsize=(180/25.4,height*Y_SCALE/25.4))
    ax=fig.add_axes([0,0,1,1]); ax.set(xlim=(0,180),ylim=(0,height)); ax.set_axis_off()
    return fig,ax

def text(ax,x,y,s,size=7.2,color=INK,weight='normal',ha='left',va='center',**kwargs):
    kwargs.setdefault('zorder',8)
    return ax.text(x,y,s,fontsize=size,color=color,weight=weight,ha=ha,va=va,
                   linespacing=1.15,**kwargs)

def line(ax,pts,color=GRAY,lw=.75,ls='-',z=2):
    return ax.plot([p[0] for p in pts],[p[1] for p in pts],color=color,lw=lw,
                   ls=ls,solid_capstyle='round',zorder=z)[0]

def arrow(ax,a,b,color=INK,lw=.9,rad=0,ls='-',head=6,shrinkA=0,shrinkB=0):
    art=FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=head,
        connectionstyle=f'arc3,rad={rad}',color=color,lw=lw,linestyle=ls,
        shrinkA=shrinkA,shrinkB=shrinkB,zorder=3)
    ax.add_patch(art); return art

def flow(ax,pts,color=INK,lw=.9,ls='-',head=6):
    if len(pts)>2: line(ax,pts[:-1],color,lw,ls)
    return arrow(ax,pts[-2],pts[-1],color,lw,ls=ls,head=head)

def box(ax,x,y,w,h,color=INK,fill='white',lw=.7,ls='-',radius=1.2):
    radius=min(radius,.55)
    art=FancyBboxPatch((x,y),w,h,boxstyle=f'round,pad=0,rounding_size={radius}',
                      facecolor=fill,edgecolor=color,lw=lw,linestyle=ls,zorder=1)
    ax.add_patch(art); return art

def node(ax,x,y,label='',r=1.7,color=GRAY,fill='white',lw=.75,size=6.6,ring=False):
    if ring:
        halo=Circle((x,y),r+.65,facecolor='none',edgecolor=BLUE,lw=.65,zorder=4)
        halo.set_height(2*(r+.65)/Y_SCALE)
        ax.add_patch(halo)
    art=Circle((x,y),r,facecolor=fill,edgecolor=color,lw=lw,zorder=5)
    art.set_height(2*r/Y_SCALE)
    ax.add_patch(art)
    if label:text(ax,x,y,label,size,color,ha='center',zorder=8)
    return art

def edge(ax,a,b,r=1.7,color=GRAY,lw=.7,rad=0,ls='-',head=4.6):
    dx=b[0]-a[0];dy=b[1]-a[1];d=math.hypot(dx,dy*Y_SCALE)
    start=(a[0]+dx/d*(r+.25),a[1]+dy/d*(r+.25))
    end=(b[0]-dx/d*(r+.45),b[1]-dy/d*(r+.45))
    return arrow(ax,start,end,color,lw,rad,ls,head)

def pair(ax,a,b,r=1.7,color=PAIR,lw=.85):
    dx=b[0]-a[0];dy=b[1]-a[1];d=math.hypot(dx,dy*Y_SCALE)
    p=(a[0]+dx/d*(r+.15),a[1]+dy/d*(r+.15))
    q=(b[0]-dx/d*(r+.15),b[1]-dy/d*(r+.15))
    return line(ax,[p,q],color,lw,(0,(3,2)),z=4)

# The identical physical topology is reused wherever a complete SCC appears.
EDGES=[('A','B'),('A','E'),('B','C'),('B','D'),('C','D'),('C','A'),('D','E'),('E','A'),('E','B')]
UNIT={'A':(.5,1),'B':(1,.62),'C':(.81,0),'D':(.19,0),'E':(0,.62)}

def graph(ax,x,y,w=22,h=23,focus=(),labels=True,edges=None,r=1.7,oc=()):
    coords={k:(x+u*w,y+v*h) for k,(u,v) in UNIT.items()}
    rel=EDGES if edges is None else edges
    for u,v in rel:edge(ax,coords[u],coords[v],r,rad=.14 if (v,u) in rel else 0)
    for k,p in coords.items():
        node(ax,*p,k if labels else '',r=r,color=BLUE if k in focus else GRAY,
             fill=BLUE_FILL if k in focus else 'white',ring=k in oc)
    return coords

def panel_title(ax,x,y,letter,label,color=INK,size=8.2):
    text(ax,x,y,letter,9,INK,weight='bold')
    text(ax,x+4.2,y,label,size,color,weight='normal')

def save(fig,stem):
    (OUT/'qa').mkdir(exist_ok=True)
    fig.canvas.draw();renderer=fig.canvas.get_renderer();frame=fig.bbox
    records=[];clipped=[]
    texts=[t for t in fig.findobj(match=matplotlib.text.Text) if t.get_visible() and t.get_text()]
    for t in texts:
        b=t.get_window_extent(renderer)
        records.append({'text':t.get_text(),'parent_pt':t.get_fontsize(),
                        'bbox_mm':[round(q*25.4/fig.dpi,3) for q in (b.x0,b.y0,b.x1,b.y1)]})
        if b.x0<frame.x0 or b.x1>frame.x1 or b.y0<frame.y0 or b.y1>frame.y1:clipped.append(t.get_text())
    if clipped:raise ValueError(f'Text outside canvas: {clipped}')
    collisions=[]
    for i,a in enumerate(records):
        ax0,ay0,ax1,ay1=a['bbox_mm']
        for b in records[i+1:]:
            bx0,by0,bx1,by1=b['bbox_mm']
            if min(ax1,bx1)-max(ax0,bx0)>.2 and min(ay1,by1)-max(ay0,by0)>.2:
                collisions.append([a['text'],b['text']])
    fig.savefig(OUT/f'{stem}.svg')
    fig.savefig(OUT/f'{stem}.pdf')
    fig.savefig(OUT/f'{stem}.png',dpi=360)
    circles=[]
    for art in fig.findobj(match=Circle):
        bounds=art.get_window_extent(renderer)
        circles.append({'center':list(art.center), 'width_mm':round(bounds.width*25.4/fig.dpi,6),
                        'height_mm':round(bounds.height*25.4/fig.dpi,6),
                        'aspect_ratio':round(bounds.width/bounds.height,8)})
    qa={'canvas_mm':[180,round(fig.get_figheight()*25.4,3)],'text':records,
        'circular_nodes':circles,'vertical_spacing_scale':Y_SCALE,
        'clipped':clipped,'text_overlap_candidates':collisions,
        'smallest_parent_pt':min(t['parent_pt'] for t in records)}
    (OUT/'qa'/f'{stem}_geometry.json').write_text(json.dumps(qa,indent=2))
    # Grayscale preserves the exact geometry and is rendered by the same backend.
    for art in fig.findobj():
        for getter,setter in [('get_color','set_color'),('get_facecolor','set_facecolor'),('get_edgecolor','set_edgecolor')]:
            if hasattr(art,getter) and hasattr(art,setter):
                try:
                    r,g,b,a=to_rgba(getattr(art,getter)());lum=.2126*r+.7152*g+.0722*b
                    getattr(art,setter)((lum,lum,lum,a))
                except (ValueError,TypeError):pass
    fig.savefig(OUT/'qa'/f'{stem}_grayscale.png',dpi=300)
    plt.close(fig)
    return qa
