"""SA-MCGS: bounded local evaluation, object memory, and terminal readouts."""
from figure_style import *

def window_corners(ax,x,y,w,h,color=BLUE):
    """Corner marks delineate the selected graph, with no panel fill."""
    for pts in [[(x,y+3),(x,y),(x+3,y)],[(x+w-3,y),(x+w,y),(x+w,y+3)],
                [(x,y+h-3),(x,y+h),(x+3,y+h)],[(x+w-3,y+h),(x+w,y+h),(x+w,y+h-3)]]:
        line(ax,pts,color,.85)

def evaluator_chip(ax,x,y,w,h):
    """A processor outline is the evaluation operator in the actual flow."""
    processor(ax,x+w/2,y+h/2,w,h,BLUE,all_sides=True)

def history_records(ax):
    """Symbolic observations for one physical node; no values or time counts."""
    node(ax,47.5,40.5,'v',r=1.6,color=BLUE,fill=BLUE_FILL,size=7)
    arrow(ax,(49.5,40.5),(53.5,40.5),BLUE,.65,head=4)
    for x in [54.5,58.7,68.3,72.5]:
        ax.add_patch(Rectangle((x,38.7),3.0,3.6,facecolor=BLUE_FILL,
                              edgecolor=BLUE,lw=.55,zorder=1))
    for x in [63.4,64.6,65.8]:node(ax,x,40.5,r=.16,color=GRAY,fill=GRAY,lw=.2)

def framework():
    fig,ax=canvas(96)
    panel_title(ax,2,92,'a','Localize the SCC',size=8.2)
    panel_title(ax,40,92,'b','Accumulate evidence during search',size=8.2)
    panel_title(ax,132,92,'c','Read out at $T$',size=8.2)
    line(ax,[(2,87.5),(35,87.5)],LIGHT,.65)
    line(ax,[(40,87.5),(126,87.5)],LIGHT,.65)
    line(ax,[(132,87.5),(178,87.5)],LIGHT,.65)
    line(ax,[(37.5,8),(37.5,86)],LIGHT,.55,(0,(2,3)))
    line(ax,[(129,8),(129,86)],LIGHT,.55,(0,(2,3)))

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
    flow(ax,[(32.8,65),(41.0,65)])

    # A bounded induced window, with a cache-aware evaluation interface.
    text(ax,56,82,'Adaptive window',7.6,weight='bold',ha='center')
    text(ax,56,78.6,'UCB + scheduled probes',7,GRAY,ha='center')
    window_corners(ax,42.5,56,27,19.5)
    w={'A':(48,71),'B':(63.5,71),'C':(63.5,60.5),'D':(48,60.5)}
    rel=[(u,v) for u,v in EDGES if u in w and v in w]
    for u,v in rel:edge(ax,w[u],w[v],r=1.5,rad=.18 if (v,u) in rel else 0,lw=.65,head=4.1)
    for k,p in w.items():
        node(ax,*p,'' if k=='A' else k,r=1.5,size=7,
             color=BLUE if k=='A' else GRAY,fill=BLUE if k=='A' else 'white')
        if k=='A':text(ax,*p,k,size=7,color='white',ha='center')
    text(ax,56,52.6,r'$W_t\subseteq V_S,\quad |W_t|\leq w$',8.5,ha='center')
    flow(ax,[(72,66.5),(78.5,66.5)],head=5)
    evaluator_chip(ax,80,59,19,15)
    text(ax,89.5,66.5,'Local LLM',7.6,weight='bold',ha='center')
    text(ax,89.5,79,'Evaluate / reuse',7.0,ha='center')
    # Evaluator outputs scores and relations; OC is computed farther downstream.
    flow(ax,[(100.8,66.5),(115,66.5),(115,49.5),(105.5,49.5),(105.5,48.2)],head=5)
    text(ax,113.8,74.0,r'$y_t(v)$',9,ha='center')
    text(ax,113.8,69.7,r'$z_t(u,v),\ h_t$',9,ha='center')
    flow(ax,[(105.5,49.5),(61,49.5),(61,48.2)],GRAY,.75,head=5)

    # Distinct memory channels, with symbolic records rather than fake values.
    text(ax,61,46,'Node evidence',7.6,weight='bold',ha='center')
    text(ax,105.5,46,'Pair memory',7.6,weight='bold',ha='center')
    history_records(ax)
    text(ax,61,36.3,'Risk-score histories',6.6,GRAY,ha='center')
    text(ax,61,31.9,r'$\bar q_t(v)=\mathrm{mean}\,\mathcal{Y}_t(v)$',9,ha='center')
    # Multi-channel evidence and history-based OC are parallel stored quantities.
    # Do not imply that the mean alone determines either quantity.
    text(ax,61,27.5,r'Normalized support $e_t(v)$',8.2,ha='center')
    text(ax,61,23.5,'Program-computed OC',6.6,BLUE,ha='center')
    text(ax,61,20.0,'Two-of-three tests → $O_t$',8.2,BLUE,ha='center')
    # Layered observations resolve to one shared unordered-pair record.
    # Only the front page contains a pair, so no duplicate pair states appear.
    line(ax,[(91,42.8),(122.5,42.8),(122.5,34.5)],LIGHT,.6)
    line(ax,[(90,41.8),(121.5,41.8),(121.5,33.5)],GRAY,.6)
    box(ax,88.5,31.9,31.5,8.9,GRAY,fill='white',lw=.6,radius=.3)
    node(ax,94,36.4,'A',r=1.8,color=BLUE,fill=BLUE_FILL)
    node(ax,115,36.4,'D',r=1.8,color=BLUE,fill=BLUE_FILL)
    pair(ax,(94,36.4),(115,36.4),r=1.8)
    text(ax,105.5,28.8,r'$p=\{u,v\},\quad m_t(p)$',9,ha='center')
    text(ax,105.5,21.0,'Critical-pair ledger',6.7,GRAY,ha='center')

    # Feedback is from accumulated memory, not from the returned core.
    line(ax,[(61,17.5),(61,16),(105.5,16),(105.5,18.3)],BLUE,.9)
    # The return arrow enters below the SCC input, avoiding a false junction.
    flow(ax,[(83,16),(83,10.5),(40,10.5),(40,57),(42.2,57)],BLUE,1.05)
    text(ax,84,5.0,r'Memory feedback; $t=1,\ldots,T$',8.0,ha='center')
    # A final readout crosses the temporal boundary only after T.
    flow(ax,[(105.5,16),(127.4,16),(127.4,83.4),(132.0,83.4)],INK,.8)
    text(ax,117,12.6,r'$M_T$',8.5,GRAY,ha='center')
    # Mean-risk ranking is a second readout of memory, not a derivative of core.
    flow(ax,[(127.4,16),(132,16),(132,13),(145.3,13)],INK,.8,head=5)

    text(ax,155,82,'Core priority',7.6,weight='bold',ha='center')
    text(ax,155,76.8,r'$s_T(v)=e_T(v)+\alpha b_T(v)$',9,ha='center')
    text(ax,155,72.0,r'$+\,\gamma\mathbf{1}[v\in O_T]$',9,ha='center')
    text(ax,155,67.0,r'$b_T(v)=\max\ r_T(p)$',9,ha='center')
    text(ax,155,63.3,r'$p\in\mathcal{R}_T(v)$',8.2,ha='center')
    arrow(ax,(155,60.2),(155,52.7),INK,.8,head=5)
    text(ax,155,50.4,'Seed pairs → scan → close pairs',6.7,ha='center')
    # Returned core is a subset of the same SCC; original graph edges remain directed.
    h={'A':(142,44.5),'B':(168,44.5),'D':(155,31.8)}
    for u,v in [('A','B'),('B','D')]:edge(ax,h[u],h[v],r=1.8)
    for k,p in h.items():node(ax,*p,k,r=1.8,color=BLUE if k in ['A','D'] else GRAY,
                            fill=BLUE_FILL if k in ['A','D'] else 'white')
    # A-D illustrates an observed pair with no original graph edge in either direction.
    pair(ax,h['A'],h['D'],r=1.8,lw=.9)
    text(ax,155,26.4,r'$H_T\subseteq S,\quad |H_T|\leq B(S)$',9,ha='center')
    line(ax,[(133,22),(177,22)],LIGHT,.65)
    text(ax,155,18.1,'Separate risk ranking',7.6,weight='bold',ha='center')
    text(ax,155,13,r'$\mathrm{rank}(\bar q_T(v))$',9,ha='center')

    # Compact legend sits in the otherwise empty input column.
    edge(ax,(3.5,18.7),(11.3,18.7),r=.2,lw=.75)
    text(ax,13,18.7,'Directed edge',6.5)
    line(ax,[(3.5,13.2),(11,13.2)],PAIR,.85,(0,(3,2)))
    text(ax,13,13.2,'Observed pair',6.5)
    text(ax,3.5,8.2,'Pairs need not be edges.',6.4,GRAY)
    for item in fig.findobj(match=matplotlib.text.Text):
        if item.get_text() and item.get_fontsize()<7:
            item.set_fontsize(7)
    return save(fig,'fig01_framework_mechanism')

if __name__=='__main__':
    qa=framework()
    print('Figure 1 geometry:',qa['text_overlap_candidates'])
