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
INK = '#232528'
GRAY = '#72777C'
LIGHT = '#B9BDC1'
FAINT = '#EDEEEF'
BLUE = '#3D6685'
BLUE_FILL = '#EDF2F5'
RUST = '#9C513D'
RUST_FILL = '#F4EDEA'
plt.rcParams.update({
    'font.family':'sans-serif', 'font.sans-serif':['Arial','DejaVu Sans'],
    'font.size':7.2, 'mathtext.fontset':'stix',
    'svg.fonttype':'none', 'pdf.fonttype':42, 'ps.fonttype':42,
    'axes.linewidth':0.7, 'savefig.facecolor':'white',
})

def canvas(height=96):
    fig=plt.figure(figsize=(7.08661417323,height/25.4))
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
    art=FancyBboxPatch((x,y),w,h,boxstyle=f'round,pad=0,rounding_size={radius}',
                      facecolor=fill,edgecolor=color,lw=lw,linestyle=ls,zorder=1)
    ax.add_patch(art); return art

def node(ax,x,y,label='',r=1.7,color=GRAY,fill='white',lw=.75,size=6.6,ring=False):
    if ring: ax.add_patch(Circle((x,y),r+.65,facecolor='none',edgecolor=BLUE,lw=.65,zorder=4))
    art=Circle((x,y),r,facecolor=fill,edgecolor=color,lw=lw,zorder=5);ax.add_patch(art)
    if label:text(ax,x,y,label,size,color,ha='center',zorder=8)
    return art

def edge(ax,a,b,r=1.7,color=GRAY,lw=.7,rad=0,ls='-',head=4.6):
    dx=b[0]-a[0];dy=b[1]-a[1];d=math.hypot(dx,dy)
    start=(a[0]+dx/d*(r+.25),a[1]+dy/d*(r+.25))
    end=(b[0]-dx/d*(r+.45),b[1]-dy/d*(r+.45))
    return arrow(ax,start,end,color,lw,rad,ls,head)

def pair(ax,a,b,r=1.7,color=RUST,lw=1.0):
    dx=b[0]-a[0];dy=b[1]-a[1];d=math.hypot(dx,dy)
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
        node(ax,*p,k if labels else '',r=r,color=RUST if k in focus else GRAY,
             fill=RUST_FILL if k in focus else 'white',ring=k in oc)
    return coords

def panel_title(ax,x,y,letter,label,color=INK,size=8.2):
    text(ax,x,y,letter,9,color,weight='bold')
    text(ax,x+4.2,y,label,size,color,weight='bold')

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
    qa={'canvas_mm':[180,round(fig.get_figheight()*25.4,3)],'text':records,
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


"""SA-MCGS: bounded local evaluation, object memory, and terminal readouts."""


def framework():
    fig,ax=canvas(96)
    panel_title(ax,2,92,'a','Localize the SCC',size=8)
    panel_title(ax,40,92,'b','Accumulate evidence during search',size=8)
    panel_title(ax,132,92,'c','Read out at $T$',size=8)
    line(ax,[(2,87.5),(35,87.5)],LIGHT,.65)
    line(ax,[(40,87.5),(126,87.5)],LIGHT,.65)
    line(ax,[(132,87.5),(178,87.5)],LIGHT,.65)
    line(ax,[(37.5,8),(37.5,86)],LIGHT,.65,(0,(2,3)))
    line(ax,[(129,8),(129,86)],GRAY,.65,(0,(2,3)))

    # Input graph. No risk endpoints are known a priori.
    hull=[(17.0,77),(32.7,67),(29,42.3),(8,42.3),(1.8,64)]
    ax.add_patch(Polygon(hull,closed=True,facecolor='none',edgecolor=GRAY,
                         linewidth=.7,linestyle=(0,(3,2))))
    coords=graph(ax,5,47,24,25,r=1.75)
    node(ax,5,81,r=1.35)
    edge(ax,(5,81),coords['A'],r=1.75)
    node(ax,29,35,r=1.35)
    edge(ax,coords['D'],(29,35),r=1.75)
    text(ax,17,31,r'$S=(V_S,E_S)$',9,ha='center')
    text(ax,17,26.5,'Tarjan decomposition',6.8,GRAY,ha='center')
    flow(ax,[(32.8,65),(41.0,65)])

    # A bounded induced window, with a cache-aware evaluation interface.
    text(ax,56,82,'Adaptive window',7.4,weight='bold',ha='center')
    text(ax,57,78.6,'UCB + scheduled probes',6.5,GRAY,ha='center')
    box(ax,44,57.4,27,19.5,LIGHT,radius=.9)
    box(ax,42.5,56,27,19.5,INK,radius=.9)
    w={'A':(48,71),'B':(63.5,71),'C':(63.5,60.5),'D':(48,60.5)}
    rel=[(u,v) for u,v in EDGES if u in w and v in w]
    for u,v in rel:edge(ax,w[u],w[v],r=1.5,rad=.18 if (v,u) in rel else 0,lw=.65,head=4.1)
    for k,p in w.items():node(ax,*p,k,r=1.5,size=6.7)
    text(ax,56,51.8,r'$W_t\subseteq V_S,\quad |W_t|\leq w$',8.5,ha='center')
    flow(ax,[(72,66),(78.5,66)])
    box(ax,80,59,19,15,INK,radius=1.5,lw=.85)
    text(ax,89.5,68.2,'Local LLM',7.6,weight='bold',ha='center')
    text(ax,89.5,63.5,'shared rubric',6.6,ha='center')
    text(ax,89.5,79,'Evaluate / reuse',7.0,ha='center')
    text(ax,89.5,54.4,'Eligible cache hit',6.5,GRAY,ha='center')
    # Evaluator outputs scores and relations; OC is computed farther downstream.
    flow(ax,[(99.7,66),(115,66),(115,45.7)])
    text(ax,116,76.4,r'$y_t(v)$',9,ha='center')
    text(ax,116,72.0,r'$z_t(u,v),\ h_t$',9,ha='center')
    flow(ax,[(115,48),(61,48),(61,45.7)],GRAY,.75)

    # Distinct memory channels, with symbolic records rather than fake values.
    box(ax,41.5,19.5,39,25.5,GRAY,lw=.7,radius=1.4)
    box(ax,85,19.5,41,25.5,GRAY,lw=.7,radius=1.4)
    text(ax,61,41.7,'Node evidence',7.5,weight='bold',ha='center')
    text(ax,105.5,41.7,'Pair memory',7.5,weight='bold',ha='center')
    text(ax,61,37.8,r'Normalized support $e_t(v)$',8,ha='center')
    text(ax,61,33.3,r'$\bar q_t(v)=\mathrm{mean}\,\mathcal{Y}_t(v)$',9,ha='center')
    text(ax,61,29.2,'Risk-score histories',6.6,GRAY,ha='center')
    arrow(ax,(61,27.5),(61,26.1),BLUE,.75,head=4)
    text(ax,61,24.6,'Program-computed OC',6.6,BLUE,ha='center')
    text(ax,61,21.3,'Two-of-three tests → $O_t$',7.4,BLUE,ha='center')
    node(ax,94,34.5,'A',r=1.8,color=RUST,fill=RUST_FILL)
    node(ax,117,34.5,'D',r=1.8,color=RUST,fill=RUST_FILL)
    pair(ax,(94,34.5),(117,34.5),r=1.8)
    text(ax,105.5,28.8,r'$p=\{u,v\},\quad m_t(p)$',9,ha='center')
    text(ax,105.5,24.4,'Support • reasons',6.7,GRAY,ha='center')
    text(ax,105.5,21.0,'Critical-pair ledger',6.7,GRAY,ha='center')

    # Feedback is from accumulated memory, not from the returned core.
    line(ax,[(61,19.5),(61,16),(105.5,16),(105.5,19.5)],BLUE,.9)
    flow(ax,[(83,16),(83,10.5),(40,10.5),(40,74.5),(42.2,74.5)],BLUE,.9)
    text(ax,85,6.4,'Shared node / edge statistics + pair ledger',6.8,BLUE,ha='center')
    text(ax,84,2.5,r'Memory guides the next window; $t=1,\ldots,T$',8.0,ha='center')
    # A final readout crosses the temporal boundary only after T.
    flow(ax,[(105.5,16),(127.4,16),(127.4,83.4),(132.0,83.4)],INK,.8)

    text(ax,155,82,'Core priority',7.6,weight='bold',ha='center')
    text(ax,155,76.8,r'$s_T(v)=e_T(v)+\alpha b_T(v)$',9,ha='center')
    text(ax,155,72.0,r'$+\,\gamma\mathbf{1}[v\in O_T]$',9,ha='center')
    text(ax,155,67.0,r'$b_T(v)=\max\ r_T(p)$',9,ha='center')
    text(ax,155,62.4,r'$p\in\mathcal{R}_T(v)$',8.2,ha='center')
    text(ax,155,57.6,'Normalized evidence + pair + OC',6.6,GRAY,ha='center')
    arrow(ax,(155,55.1),(155,52.7),INK,.8,head=5)
    text(ax,155,50.4,'Seed pairs → scan → close pairs',6.7,ha='center')
    # Returned core is a subset of the same SCC; original graph edges remain directed.
    h={'A':(142,44.5),'B':(168,44.5),'D':(155,31.8)}
    for u,v in [('A','B'),('B','D')]:edge(ax,h[u],h[v],r=1.8)
    for k,p in h.items():node(ax,*p,k,r=1.8,color=RUST if k in ['A','D'] else GRAY,
                            fill=RUST_FILL if k in ['A','D'] else 'white')
    # A-D illustrates an observed pair with no original graph edge in either direction.
    pair(ax,h['A'],h['D'],r=1.8,lw=.9)
    text(ax,155,26.4,r'$H_T\subseteq S,\quad |H_T|\leq B(S)$',9,ha='center')
    line(ax,[(133,22),(177,22)],LIGHT,.65)
    text(ax,155,18.1,'Separate risk ranking',7.2,weight='bold',ha='center')
    text(ax,155,13,r'$\mathrm{rank}(\bar q_T(v))$',9,ha='center')
    text(ax,155,7.3,'Mean observed risk',6.7,GRAY,ha='center')

    # Compact legend sits in the otherwise empty input column.
    edge(ax,(3.5,18.7),(11.3,18.7),r=.2,lw=.75)
    text(ax,13,18.7,'Directed edge',6.5)
    line(ax,[(3.5,13.2),(11,13.2)],RUST,.95,(0,(3,2)))
    text(ax,13,13.2,'Observed pair',6.5)
    text(ax,3.5,8.2,'Pairs need not be edges.',6.4,GRAY)
    text(ax,3.5,3.2,'Illustrative topology',6.4,GRAY)
    for item in fig.findobj(match=matplotlib.text.Text):
        if item.get_text() and item.get_fontsize()<7:
            item.set_fontsize(7)
    return save(fig,'fig01_framework_mechanism')



"""Four mechanism views of one SCC; all topologies are illustrative, not data."""



def induced(ax, coords, focus=(), r=1.6):
    """Render every physical edge whose two endpoints are in the window."""
    rel = [(u, v) for u, v in EDGES if u in coords and v in coords]
    for u, v in rel:
        edge(ax, coords[u], coords[v], r=r,
             rad=.15 if (v, u) in rel else 0, lw=.7)
    for v, p in coords.items():
        node(ax, *p, v, r=r, size=7,
             color=BLUE if v in focus else GRAY,
             fill=BLUE_FILL if v in focus else 'white')
    return rel


def branch_tree(ax):
    # Each link is a legal transition in the physical SCC, not an invented edge.
    pos = {'A':(111,57), 'AB':(101,49), 'AE':(121,49),
           'ABC':(97,39), 'ABD':(106,39),
           'AEA':(117,39), 'AEB':(127,39)}
    links=[('A','AB'),('A','AE'),('AB','ABC'),('AB','ABD'),
           ('AE','AEA'),('AE','AEB')]
    for a, b in links:
        assert (a[-1], b[-1]) in EDGES
        edge(ax,pos[a],pos[b],r=1.75)
    for key,p in pos.items():
        node(ax,*p,key[-1],r=1.75,size=7,
             color=BLUE if key[-1] in ['A','B'] else GRAY,
             fill=BLUE_FILL if key[-1] in ['A','B'] else 'white')
    for key in ['ABC','ABD','AEA','AEB']:
        x,y=pos[key]
        arrow(ax,(x,y-2.1),(x,y-5.5),color=GRAY,lw=.65,ls=(0,(2,2)),head=4)


def draw():
    fig, ax=canvas(96)
    # One common physical input. Colours carry mechanism roles, not risk scores.
    graph(ax,8,77,19,14,r=1.5)
    box(ax,4.5,74,26,19.7,color=LIGHT,fill='none',ls=(0,(3,3)),radius=.8)
    text(ax,33,88,'One cyclic component',size=8.5,weight='bold')
    text(ax,33,82,r'$S=(V_S,E_S)$',size=10)
    text(ax,77,88,'Four evidence pathways',size=8.5,weight='bold')
    text(ax,77,82,'Same record identities and directed topology',size=7.2)
    node(ax,79,76,'',r=1.2,color=BLUE,fill=BLUE_FILL)
    text(ax,82,76,'anchor / revisited record',size=7)
    line(ax,[(129,76),(135,76)],color=RUST,ls=(0,(3,2)),lw=.85)
    text(ax,137,76,'evidence relation',size=7)
    line(ax,[(4,71.5),(176,71.5)],color=INK,lw=.65)

    for x in [45,90,135]:
        line(ax,[(x,7),(x,68)],color=LIGHT,lw=.55,ls=(0,(2,3)))
    panel_title(ax,4,67,'a','Full-SCC',size=8.4)
    panel_title(ax,49,67,'b','LEA',size=8.4)
    panel_title(ax,94,67,'c','TreeMCTS',size=8.4)
    panel_title(ax,139,67,'d','SA-MCGS',size=8.4)

    # Full-SCC: every record enters a single evaluation.
    text(ax,24,61,'One-shot context',size=7.2,ha='center')
    graph(ax,11.5,39.5,24,17,r=1.75)
    box(ax,7,36.3,32.5,22.8,color=GRAY,fill='none',lw=.65,ls=(0,(3,2)),radius=1)
    text(ax,38,37.6,r'$S$',size=8.5,ha='right')
    arrow(ax,(23,35.5),(23,30.5),head=5)
    box(ax,10.5,22.8,25,7.3,color=INK,lw=.7,radius=1)
    text(ax,23,26.45,r'$\operatorname{Eval}(S)$',size=10,ha='center')
    flow(ax,[(23,22.5),(23,17.5),(13,17.5),(13,14.5)],head=5)
    flow(ax,[(23,17.5),(33,17.5),(33,14.5)],head=5)
    text(ax,13,11.6,r'$H$',size=10,ha='center')
    text(ax,33,11.6,r'$\operatorname{Rank}$',size=10,ha='center')

    # LEA: examples of fixed anchor windows, both induced from the shared SCC.
    text(ax,67.5,61,'Fixed overlapping windows',size=7,ha='center')
    box(ax,48.5,42.3,18,15.7,color=LIGHT,fill='none',lw=.6,radius=1)
    box(ax,69,42.3,18,15.7,color=LIGHT,fill='none',lw=.6,radius=1)
    # With fixed SCC order A,B,C,D,E these are exactly the anchor-first
    # neighbour windows at the illustrated capacity (the caption generalizes w).
    induced(ax,{'A':(51.5,54.5),'B':(63.5,54.5),'C':(63.5,45.8),'E':(51.5,45.8)},focus=('A',))
    induced(ax,{'A':(72,54.5),'B':(84,54.5),'C':(84,45.8),'D':(72,45.8)},focus=('B',))
    text(ax,57.5,39.4,r'$W_A$',size=9,ha='center')
    text(ax,78,39.4,r'$W_B$',size=9,ha='center')
    text(ax,86.3,39.4,r'$\cdots$',size=9,ha='center')
    arrow(ax,(57.5,36.8),(62.3,32.1),head=5)
    arrow(ax,(78,36.8),(73,32.1),head=5)
    box(ax,54,24.2,27,7.7,color=INK,lw=.7,radius=1)
    text(ax,67.5,28.05,r'$\operatorname{Eval}(W_v)$',size=10,ha='center')
    arrow(ax,(67.5,23.8),(67.5,20.4),head=4.8)
    text(ax,67.5,17.8,'Mean risk + evidence count',size=7,ha='center')
    text(ax,67.5,11.6,r'$H\,,\quad\operatorname{Rank}(\bar q)$',size=10,ha='center')

    # TreeMCTS: two paths can end at A or B but retain separate search states.
    text(ax,112.5,61,'Path-indexed states',size=7.2,ha='center')
    branch_tree(ax)
    text(ax,112.5,28.2,r'$s_\pi=(v_0,\ldots,v_\ell)$',size=9.3,ha='center')
    text(ax,112.5,21.2,r'$Q_\pi\,,\ N_\pi$',size=10,ha='center')
    text(ax,112.5,13.2,'Same record, separate states',size=7,ha='center')

    # SA-MCGS: state is attached to graph objects; only accumulated evidence
    # feeds selection. H is computed once after T and has no return arrow.
    text(ax,157.5,61,'Shared evidence memory',size=7.2,ha='center')
    text(ax,156.5,55.6,r'$W_t=\operatorname{Select}(M_{t-1})$',size=9.2,ha='center')
    coords={'A':(149,48.8),'B':(162,48.8),'C':(162,39.8),'D':(149,39.8)}
    induced(ax,coords,focus=('A',))
    pair(ax,coords['A'],coords['D'],r=1.6,lw=.85)
    arrow(ax,(155.5,38),(155.5,34.7),head=4.8)
    text(ax,155.5,32,r'$\operatorname{Eval}(W_t)\ /\ \operatorname{Cache}$',size=9.2,ha='center')
    arrow(ax,(155.5,29.9),(155.5,26.9),head=4.8)
    text(ax,155.5,24,r'$M_t=\operatorname{Update}(M_{t-1},\mathcal{E}_t)$',size=8.8,ha='center')
    flow(ax,[(173,24),(177,24),(177,55.6),(172,55.6)],color=BLUE,lw=.85,head=5)
    line(ax,[(139,18.7),(175,18.7)],color=LIGHT,lw=.6,ls=(0,(2,2)))
    arrow(ax,(155.5,21.8),(155.5,14.2),head=4.8)
    text(ax,173,16.8,r'$t=T$',size=8.5,ha='right')
    text(ax,156.5,11.6,r'$H=\operatorname{Core}(M_T,B(S))$',size=9,ha='center')

    line(ax,[(4,6.2),(176,6.2)],color=LIGHT,lw=.55)
    text(ax,4,3.1,r'$W$: window   $M$: accumulated evidence   $H$: returned subgraph   $B(S)$: core-size cap',size=7)
    text(ax,176,3.1,'Schematic only',size=7,color=GRAY,ha='right')
    # Shared graph() uses compact labels by default; at manuscript scale keep
    # all letters at the same readable seven-point floor as the body labels.
    for item in fig.findobj(match=matplotlib.text.Text):
        if item.get_text() and item.get_fontsize()<7:
            item.set_fontsize(7)
    qa=save(fig,'fig02_mechanism_comparison')
    print({'figure':'fig02_mechanism_comparison','overlaps':qa['text_overlap_candidates'],
           'clipped':qa['clipped'],'smallest_pt':qa['smallest_parent_pt']})



if __name__ == '__main__':
    framework()
    draw()
