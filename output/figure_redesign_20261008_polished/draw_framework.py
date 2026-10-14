"""SA-MCGS: bounded local evaluation, object memory, and terminal readouts."""
from figure_style import *

def framework():
    fig,ax=canvas(96)
    panel_title(ax,2,92,'a','Localize the SCC',size=8.2)
    panel_title(ax,40,92,'b','Accumulate evidence during search',size=8.2)
    panel_title(ax,132,92,'c','Read out at $T$',size=8.2)
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
    text(ax,56,82,'Adaptive window',7.6,weight='bold',ha='center')
    text(ax,56,78.6,'UCB + scheduled probes',7,GRAY,ha='center')
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
    box(ax,41.5,18.3,39,26.7,GRAY,lw=.7,radius=1.4)
    box(ax,85,18.3,41,26.7,GRAY,lw=.7,radius=1.4)
    text(ax,61,41.7,'Node evidence',7.6,weight='bold',ha='center')
    text(ax,105.5,41.7,'Pair memory',7.6,weight='bold',ha='center')
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
    line(ax,[(61,18.3),(61,16),(105.5,16),(105.5,18.3)],BLUE,.9)
    # The return arrow enters below the SCC input, avoiding a false junction.
    flow(ax,[(83,16),(83,10.5),(40,10.5),(40,57),(42.2,57)],BLUE,.9)
    text(ax,85,6.4,'Shared node / edge statistics + pair ledger',6.8,BLUE,ha='center')
    text(ax,84,2.5,r'Memory guides the next window; $t=1,\ldots,T$',8.0,ha='center')
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
    text(ax,155,18.1,'Separate risk ranking',7.6,weight='bold',ha='center')
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

if __name__=='__main__':
    qa=framework()
    print('Figure 1 geometry:',qa['text_overlap_candidates'])
