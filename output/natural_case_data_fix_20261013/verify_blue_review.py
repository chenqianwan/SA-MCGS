from pathlib import Path
from pypdf import PdfReader
import pdfplumber, json, subprocess, hashlib
from PIL import Image, ImageDraw

ROOT = Path('/Users/chenlong/WorkSpace/MCGS_Law')
BASE = ROOT / 'paper/latex/acl_latex_clean.pdf'
BLUE = ROOT / 'output/pdf/SA_MCGS_natural_case_update_blue.pdf'
OUT = ROOT / 'output/natural_case_data_fix_20261013/blue_qa'
OUT.mkdir(exist_ok=True)
a, b = PdfReader(BASE), PdfReader(BLUE)
assert len(a.pages) == len(b.pages) == 32
norm = lambda t: ''.join(t.split())
text_match = [norm(x.extract_text()) == norm(y.extract_text()) for x, y in zip(a.pages, b.pages)]
assert all(text_match), [i+1 for i, v in enumerate(text_match) if not v]
report = {'pages': 32, 'page_text_matches_clean': text_match, 'new_blue_pages': {},
          'canonical_pdf_sha256': hashlib.sha256(BASE.read_bytes()).hexdigest(),
          'blue_pdf_sha256': hashlib.sha256(BLUE.read_bytes()).hexdigest()}
max_shift = 0
def rgb(color):
    if isinstance(color, (int, float)):
        return (color,) * 3
    if len(color) == 1:
        return color * 3
    return tuple(color)
with pdfplumber.open(BASE) as ca, pdfplumber.open(BLUE) as cb:
    for i, (pa, pb) in enumerate(zip(ca.pages, cb.pages), 1):
        assert len(pa.chars) == len(pb.chars), (i, len(pa.chars), len(pb.chars))
        additions = []
        for x, y in zip(pa.chars, pb.chars):
            assert x['text'] == y['text']
            shift = max(abs(x[k]-y[k]) for k in ['x0', 'x1', 'top', 'bottom'])
            max_shift = max(max_shift, shift)
            assert shift < 0.2, (i, shift, x['text'])
            if rgb(x['non_stroking_color']) != rgb(y['non_stroking_color']):
                assert rgb(y['non_stroking_color']) == (0.0, 0.0, 1.0), (i, y['non_stroking_color'])
                additions.append(y['text'])
        if additions:
            report['new_blue_pages'][i] = ''.join(additions)
assert set(report['new_blue_pages']) == {8, 13, 15, 16}, report['new_blue_pages'].keys()
report['max_character_position_difference_points'] = max_shift
report['all_characters_and_line_breaks_match_clean'] = True
for page in report['new_blue_pages']:
    subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-r', '110', '-singlefile', '-png',
                    str(BLUE), str(OUT / f'page_{page}')], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
thumbs = []
for page in report['new_blue_pages']:
    im = Image.open(OUT / f'page_{page}.png').convert('RGB')
    im.thumbnail((655, 940))
    tile = Image.new('RGB', (680, 985), '#eeeeee')
    tile.paste(im, ((680-im.width)//2, 35))
    ImageDraw.Draw(tile).text((20, 12), f'Page {page}', fill='black')
    thumbs.append(tile)
montage = Image.new('RGB', (1360, 1970), 'white')
for i, im in enumerate(thumbs):
    montage.paste(im, ((i % 2)*680, (i // 2)*985))
montage.save(OUT / 'blue_changes.png')
(OUT / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
