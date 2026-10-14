"""Four mechanism views of one SCC; all topologies are illustrative, not data."""
from figure_style import *


def comparison_corners(ax,x,y,w,h,color=GRAY,lw=.7,length=2.6,layer=False):
    """Open crop marks denote a context extent, not another processing block."""
    if layer:
        comparison_corners(ax,x+.7,y+.7,w,h,LIGHT,.45,length,False)
    for pts in [[(x,y+length),(x,y),(x+length,y)],
                [(x+w-length,y),(x+w,y),(x+w,y+length)],
                [(x,y+h-length),(x,y+h),(x+length,y+h)],
                [(x+w-length,y+h),(x+w,y+h),(x+w,y+h-length)]]:
        line(ax,pts,color,lw,z=1)


def comparison_processor(ax,cx,cy,w,h,accent=GRAY):
    """A small vector operator with input/output terminals and no colour panel."""
    processor(ax,cx,cy,w,h,accent)


def comparison_slot(ax,cx,cy,w=6.4,h=3.6):
    """An unfilled pair of Q/N storage slots, with no values encoded."""
    x=cx-w/2;y=cy-h/2
    line(ax,[(x,y+h),(x,y),(x+w,y),(x+w,y+h)],GRAY,.55)
    line(ax,[(cx,y),(cx,y+h)],LIGHT,.55)
    text(ax,cx-w/4,cy,'Q',size=7.4,color=INK,ha='center')
    text(ax,cx+w/4,cy,'N',size=7.4,color=INK,ha='center')


def induced(ax, coords, focus=(), r=1.6, accent=BLUE, tint=BLUE_FILL):
    """Render every physical edge whose two endpoints are in the window."""
    rel = [(u, v) for u, v in EDGES if u in coords and v in coords]
    for u, v in rel:
        edge(ax, coords[u], coords[v], r=r,
             rad=.15 if (v, u) in rel else 0, lw=.7)
    for v, p in coords.items():
        active=v in focus
        node(ax, *p, '', r=r, size=7,
             color=accent if active else GRAY,
             fill=accent if active else 'white')
        text(ax,*p,v,size=7,color='white' if active else INK,ha='center')
    return rel


def branch_tree(ax):
    # Each link is a legal transition in the physical SCC, not an invented edge.
    pos = {'A':(112.5,57), 'AB':(102,49), 'AE':(123,49),
           'ABC':(97,39), 'ABD':(107,39),
           'AEA':(118,39), 'AEB':(128,39)}
    links=[('A','AB'),('A','AE'),('AB','ABC'),('AB','ABD'),
           ('AE','AEA'),('AE','AEB')]
    for a, b in links:
        assert (a[-1], b[-1]) in EDGES
        edge(ax,pos[a],pos[b],r=1.75)
    for key,p in pos.items():
        node(ax,*p,key[-1],r=1.75,size=7,
             color=INK if key[-1] in ['A','B'] else GRAY,
             fill=FAINT if key[-1] in ['A','B'] else 'white')
    for key in ['ABC','ABD','AEA','AEB']:
        x,y=pos[key]
        # Every path state has a distinct pair of statistic slots.  The shared
        # Q_pi/N_pi notation below names their contents; no value is pictured.
        arrow(ax,(x,y-2.2),(x,33.7),color=GRAY,lw=.65,head=4)
        comparison_slot(ax,x,31.5)


def draw():
    fig, ax=canvas(96)
    # One common physical input. Colours carry mechanism roles, not risk scores.
    graph(ax,8,77,19,14,r=1.5)
    comparison_corners(ax,4.5,74,26,19.7,LIGHT,.6,length=3)
    text(ax,33,88,'One cyclic component',size=8.5,weight='bold')
    text(ax,33,82,r'$S=(V_S,E_S)$',size=10)
    text(ax,77,88,'Four mechanisms',size=8.5,weight='bold')
    node(ax,79,79,'',r=1.2,color=INK,fill=FAINT)
    text(ax,82,79,'Anchor / revisited record',size=7)
    line(ax,[(129,79),(135,79)],color=PAIR,ls=(0,(3,2)),lw=.85)
    text(ax,137,79,'Observed pair',size=7)
    line(ax,[(4,71.5),(176,71.5)],color=INK,lw=.65)

    for x in [45,90,135]:
        line(ax,[(x,7),(x,68)],color=LIGHT,lw=.55,ls=(0,(2,3)))
    panel_title(ax,4,67,'a','Full-SCC',color=GRAY,size=8.2)
    panel_title(ax,49,67,'b','LEA',color=ORANGE,size=8.2)
    panel_title(ax,94,67,'c','TreeMCTS',size=8.2)
    panel_title(ax,139,67,'d','SA-MCGS',color=BLUE,size=8.2)

    # Full-SCC: every record enters a single evaluation.
    text(ax,23.5,61,'One-shot context',size=7.2,ha='center')
    graph(ax,11.5,39.5,24,17,r=1.75)
    comparison_corners(ax,7,36.3,32.5,22.8,GRAY,.7,length=3.3)
    text(ax,38,37.6,r'$S$',size=8.5,ha='right')
    arrow(ax,(23.5,35.5),(23.5,31.8),head=5)
    comparison_processor(ax,23.5,27.5,25,7.6,GRAY)
    text(ax,23.5,27.5,r'$\operatorname{Eval}(S)$',size=10,ha='center')
    flow(ax,[(23.5,23.2),(23.5,17.5),(13.5,17.5),(13.5,14.5)],head=5)
    flow(ax,[(23.5,17.5),(33.5,17.5),(33.5,14.5)],head=5)
    text(ax,13.5,11.6,r'$H$',size=10,ha='center')
    text(ax,33.5,11.6,r'$\operatorname{rank}$',size=10,ha='center')

    # LEA: examples of fixed anchor windows, both induced from the shared SCC.
    text(ax,67.5,61,'Fixed overlapping windows',size=7,ha='center')
    comparison_corners(ax,48.5,42.3,18,15.7,ORANGE,.65,length=2.4,layer=False)
    comparison_corners(ax,69,42.3,18,15.7,ORANGE,.65,length=2.4,layer=False)
    # With fixed SCC order A,B,C,D,E these are exactly the anchor-first
    # neighbour windows at the illustrated capacity (the caption generalizes w).
    induced(ax,{'A':(51.5,54.5),'B':(63.5,54.5),'C':(63.5,45.8),'E':(51.5,45.8)},focus=('A',),accent=ORANGE,tint=ORANGE_FILL)
    induced(ax,{'A':(72,54.5),'B':(84,54.5),'C':(84,45.8),'D':(72,45.8)},focus=('B',),accent=ORANGE,tint=ORANGE_FILL)
    text(ax,57.5,39.4,r'$W_A$',size=9,ha='center')
    text(ax,78,39.4,r'$W_B$',size=9,ha='center')
    text(ax,86.3,39.4,r'$\cdots$',size=9,ha='center')
    arrow(ax,(57.5,36.8),(62.3,31.8),head=5)
    arrow(ax,(78,36.8),(73,31.8),head=5)
    comparison_processor(ax,67.5,27.5,27,7.6,ORANGE)
    text(ax,67.5,27.5,r'$\operatorname{Eval}(W_v)$',size=10,ha='center')
    arrow(ax,(67.5,23.2),(67.5,20.4),head=5)
    text(ax,67.5,17.8,'Mean risk + evidence counts',size=7,ha='center')
    text(ax,67.5,11.6,r'$H\,,\quad\operatorname{rank}(\bar q)$',size=10,ha='center')

    # TreeMCTS: two paths can end at A or B but retain separate search states.
    text(ax,112.5,61,'Path-indexed states',size=7.2,ha='center')
    branch_tree(ax)
    text(ax,112.5,25.8,r'$s_\pi=(v_0,\ldots,v_\ell)$',size=9.3,ha='center')
    text(ax,112.5,21.2,r'$Q_\pi\,,\ N_\pi$',size=10,ha='center')

    # SA-MCGS: state is attached to graph objects; only accumulated evidence
    # feeds selection. H is computed once after T and has no return arrow.
    text(ax,155.5,61,'Shared evidence memory',size=7.2,ha='center')
    text(ax,155.5,55.6,r'$W_t=\operatorname{Select}(M_{t-1})$',size=9.2,ha='center')
    coords={'A':(149,48.8),'B':(162,48.8),'C':(162,39.8),'D':(149,39.8)}
    induced(ax,coords,focus=('A',))
    pair(ax,coords['A'],coords['D'],r=1.6,lw=.85)
    arrow(ax,(155.5,38),(155.5,35.8),head=4.8)
    text(ax,155.5,33.6,'Evaluate / reuse',size=7.4,ha='center')
    arrow(ax,(155.5,31.5),(155.5,28.8),head=4.2)
    text(ax,159.5,29.9,r'$\mathcal{E}_t$',size=8.5,ha='center')
    # One shared bank of object keys, not five observations or five scores.
    # All slots are empty/white: the schematic does not claim that the current
    # rollout observes every SCC record or populates every memory entry.
    left=140.5;bottom=24.1;cell=6.0;top=28.1
    line(ax,[(left,top),(left,bottom),(left+5*cell,bottom),
             (left+5*cell,top)],GRAY,.65)
    for i,key in enumerate(['A','B','C','D','E']):
        if i:
            line(ax,[(left+i*cell,bottom),(left+i*cell,top)],LIGHT,.55)
        text(ax,left+(i+.5)*cell,26.1,key,size=7.4,color=INK,ha='center')
    text(ax,155.5,20.3,r'$M_t=\operatorname{Update}(M_{t-1},\mathcal{E}_t)$',size=8.8,ha='center')
    flow(ax,[(173,20.3),(177,20.3),(177,55.6),(172,55.6)],color=BLUE,lw=1.05,head=5)
    line(ax,[(139,16.4),(163,16.4)],color=LIGHT,lw=.6,ls=(0,(2,2)))
    arrow(ax,(155.5,18.1),(155.5,14.2),head=4.8)
    text(ax,173,16.4,r'$t=T$',size=8.5,ha='right')
    text(ax,155.5,11.6,r'$H_T=\operatorname{Core}(M_T,B(S))$',size=9,ha='center')

    line(ax,[(4,6.2),(176,6.2)],color=LIGHT,lw=.55)
    text(ax,4,3.1,r'$W$: window   $M$: memory   $H$: subgraph   $B(S)$: size cap',size=7)
    # Shared graph() uses compact labels by default; at manuscript scale keep
    # all letters at the same readable seven-point floor as the body labels.
    for item in fig.findobj(match=matplotlib.text.Text):
        if item.get_text() and item.get_fontsize()<7:
            item.set_fontsize(7)
    qa=save(fig,'fig02_mechanism_comparison')
    print({'figure':'fig02_mechanism_comparison','overlaps':qa['text_overlap_candidates'],
           'clipped':qa['clipped'],'smallest_pt':qa['smallest_parent_pt']})


if __name__ == '__main__':
    draw()
