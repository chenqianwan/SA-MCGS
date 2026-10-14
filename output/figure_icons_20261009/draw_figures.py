"""Regenerate both compact manuscript figures from their editable sources."""
from draw_framework import framework
from draw_comparison import draw

if __name__ == '__main__':
    qa = framework()
    print('Figure 1 geometry:', qa['text_overlap_candidates'])
    draw()
