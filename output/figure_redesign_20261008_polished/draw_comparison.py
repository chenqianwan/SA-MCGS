"""Four mechanism views of one SCC; all topologies are illustrative, not data."""
from figure_style import *


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
    text(ax,82,76,'Anchor / revisited record',size=7)
    line(ax,[(129,76),(135,76)],color=RUST,ls=(0,(3,2)),lw=.85)
    text(ax,137,76,'Observed pair',size=7)
    line(ax,[(4,71.5),(176,71.5)],color=INK,lw=.65)

    for x in [45,90,135]:
        line(ax,[(x,7),(x,68)],color=LIGHT,lw=.55,ls=(0,(2,3)))
    panel_title(ax,4,67,'a','Full-SCC',size=8.2)
    panel_title(ax,49,67,'b','LEA',size=8.2)
    panel_title(ax,94,67,'c','TreeMCTS',size=8.2)
    panel_title(ax,139,67,'d','SA-MCGS',size=8.2)

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
    text(ax,33,11.6,r'$\operatorname{rank}$',size=10,ha='center')

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
    text(ax,67.5,17.8,'Mean risk + evidence counts',size=7,ha='center')
    text(ax,67.5,11.6,r'$H\,,\quad\operatorname{rank}(\bar q)$',size=10,ha='center')

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
    text(ax,155.5,32,'Evaluate / reuse',size=7.4,ha='center')
    arrow(ax,(155.5,29.9),(155.5,26.9),head=4.8)
    text(ax,159.4,28.3,r'$\mathcal{E}_t$',size=8.5,ha='center')
    text(ax,155.5,24,r'$M_t=\operatorname{Update}(M_{t-1},\mathcal{E}_t)$',size=8.8,ha='center')
    flow(ax,[(173,24),(177,24),(177,55.6),(172,55.6)],color=BLUE,lw=.85,head=5)
    line(ax,[(139,18.7),(175,18.7)],color=LIGHT,lw=.6,ls=(0,(2,2)))
    arrow(ax,(155.5,21.8),(155.5,14.2),head=4.8)
    text(ax,173,16.8,r'$t=T$',size=8.5,ha='right')
    text(ax,156.5,11.6,r'$H_T=\operatorname{Core}(M_T,B(S))$',size=9,ha='center')

    line(ax,[(4,6.2),(176,6.2)],color=LIGHT,lw=.55)
    text(ax,4,3.1,r'$W$: window   $M$: accumulated evidence   $H$: returned subgraph   $B(S)$: core-size cap',size=7)
    text(ax,176,3.1,'Illustrative topology',size=7,color=GRAY,ha='right')
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
