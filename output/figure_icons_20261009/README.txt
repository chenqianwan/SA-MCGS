SA-MCGS main figures — subtle color and generated mnemonic icons, 9 October 2026.

Regenerate with Python, matplotlib and Pillow: python draw_figures.py
Source canvas: 180 x 84 mm; manuscript width: 160 mm.
PDF/SVG retain editable vector labels, formulas, graphs and arrows. Only the four tiny icons are raster assets, embedded at 600 dpi. PNG previews are 360 dpi.

Method colors remain Full-SCC/One-shot #737373, LEA #D55E00, SA-MCGS #0072B2, and neutral TreeMCTS. Light blue, orange and gray fills group related modules without encoding numeric values. Observed pairs remain dashed neutral gray and need not coincide with original directed edges.

Four original transparent icons were generated using the built-in image_gen route: full_context (stacked documents), local_window (overlapping windows and magnifier), search_branch (branching nodes), and shared_memory (memory store with connected records). The full prompts are in icons/generation_prompts.json; original PNG files are retained alongside it. Four types appear in the comparison headers, and shared_memory is reused in Figure 1. Icons are generic visual cues, not generated scientific evidence.

Scientific text, equations, topology and method definitions are identical to the preceding aligned-color version. Full-SCC is the existing one-shot baseline. LEA uses fixed overlapping node-anchored windows; TreeMCTS stores path-prefix states. SA-MCGS updates shared memory, computes OC from histories, and selects the core only after T. Risk ranking remains a separate readout.

Symbols: S=(V_S,E_S) is the cyclic component; W_t is a bounded local window; M_t is accumulated evidence memory; H_T is the returned terminal subgraph; B(S) is its size cap. e_t(v) denotes normalized evidence, qbar_t(v) mean observed risk, m_t(p) unordered-pair support, and O_t the accumulated OC-flagged set. Operation names such as Select, Eval, Update, Core and rank are schematic.

Both clean and marked manuscripts are compiled and synchronized separately with the existing 29-file Overleaf package. Original generated icon assets and all source-generation/QA files remain outside that upload package. Figure dimensions and all manuscript text are unchanged.

QA: color and grayscale previews plus manuscript pages 3–4 inspected; no clipping or text/icon overlaps. Actual source minimum glyph sizes are 5.74/5.95 pt (5.10/5.29 pt at manuscript scale). Static preflight warnings are resolved as follows: TIFF is not needed for this PDF-based manuscript; its width parser misreads 180/25.4 (actual PDF media box verified); words mean/seed describe algorithm operations, not empirical aggregates requiring uncertainty bars. PNG previews are not submission rasters.
