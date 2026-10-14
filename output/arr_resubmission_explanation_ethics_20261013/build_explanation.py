#!/usr/bin/env python3
"""Build the anonymous, standalone ARR explanation from audited content."""
import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
)


HERE = Path(__file__).resolve().parent
FONTS = Path('/System/Library/Fonts/Supplemental')


def register_fonts():
    for name, filename in [
        ('TimesEmbedded', 'Times New Roman.ttf'),
        ('TimesEmbedded-Bold', 'Times New Roman Bold.ttf'),
        ('TimesEmbedded-Italic', 'Times New Roman Italic.ttf'),
        ('TimesEmbedded-BoldItalic', 'Times New Roman Bold Italic.ttf'),
    ]:
        pdfmetrics.registerFont(TTFont(name, str(FONTS / filename)))
    pdfmetrics.registerFontFamily(
        'TimesEmbedded', normal='TimesEmbedded', bold='TimesEmbedded-Bold',
        italic='TimesEmbedded-Italic', boldItalic='TimesEmbedded-BoldItalic',
    )


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._states = []

    def showPage(self):
        self._states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._states)
        for state in self._states:
            self.__dict__.update(state)
            self.setFont('TimesEmbedded', 9)
            self.setFillColor(colors.HexColor('#555555'))
            self.drawCentredString(A4[0] / 2, 14 * mm, f'{self._pageNumber} / {total}')
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)


def running_header(c, doc):
    if doc.page == 1:
        return
    c.saveState()
    c.setFont('TimesEmbedded-Italic', 9)
    c.setFillColor(colors.HexColor('#555555'))
    c.drawString(doc.leftMargin, A4[1] - 14 * mm, 'Explanation of Revisions')
    c.setStrokeColor(colors.HexColor('#b0b0b0'))
    c.setLineWidth(0.35)
    c.line(doc.leftMargin, A4[1] - 16 * mm,
           A4[0] - doc.rightMargin, A4[1] - 16 * mm)
    c.restoreState()


def build(output):
    register_fonts()
    data = json.loads((HERE / 'explanation_content.json').read_text())
    styles = {
        'title': ParagraphStyle('Title', fontName='TimesEmbedded-Bold', fontSize=17,
                                leading=20, alignment=TA_CENTER, spaceAfter=8),
        'paper': ParagraphStyle('PaperTitle', fontName='TimesEmbedded', fontSize=11.5,
                                leading=14, alignment=TA_CENTER, spaceAfter=14),
        'intro': ParagraphStyle('Intro', fontName='TimesEmbedded', fontSize=10.5,
                                leading=13, alignment=TA_LEFT, spaceAfter=8),
        'note': ParagraphStyle('Note', fontName='TimesEmbedded-Italic', fontSize=9.5,
                               leading=12, textColor=colors.HexColor('#444444'),
                               spaceAfter=12),
        'section': ParagraphStyle('Section', fontName='TimesEmbedded-Bold', fontSize=12.5,
                                  leading=15.5, spaceBefore=2, spaceAfter=10,
                                  keepWithNext=True),
        'concern': ParagraphStyle('Concern', fontName='TimesEmbedded-Bold', fontSize=10.5,
                                  leading=13, spaceAfter=3, keepWithNext=True),
        'response': ParagraphStyle('Response', fontName='TimesEmbedded', fontSize=10.5,
                                   leading=13, spaceAfter=3),
        'location': ParagraphStyle('Location', fontName='TimesEmbedded-Italic', fontSize=9.2,
                                   leading=10.8, textColor=colors.HexColor('#444444')),
    }
    story = [Paragraph(escape(data['title']), styles['title']),
             Paragraph(escape(data['paper_title']), styles['paper']),
             Paragraph(escape(data['intro']), styles['intro']),
             Paragraph(escape(data['note']), styles['note'])]

    def add_items(items):
        for item in items:
            story.append(KeepTogether([
                Paragraph(escape(item['id'] + '. ' + item['concern']), styles['concern']),
                Paragraph(escape(item['response']), styles['response']),
                Paragraph('Revised manuscript: ' + escape(item['locations']), styles['location']),
                Spacer(1, 7),
            ]))

    for page_no, group in enumerate(data['pages']):
        if page_no:
            story.append(PageBreak())
        story.append(Paragraph(escape(group['heading']), styles['section']))
        add_items(group['items'])
        if group.get('second_heading'):
            story.append(Spacer(1, 3))
            story.append(Paragraph(escape(group['second_heading']), styles['section']))
            add_items(group['second_items'])
        if group.get('closing'):
            story.append(KeepTogether([
                Paragraph(escape(group['closing_heading']), styles['concern']),
                Paragraph(escape(group['closing']), styles['response']),
            ]))

    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output), pagesize=A4,
        leftMargin=21 * mm, rightMargin=21 * mm,
        topMargin=22 * mm, bottomMargin=22 * mm,
        title='Explanation of Revisions', author='',
        subject='Anonymous resubmission revision summary and point-by-point responses',
        creator='Anonymous submission',
        allowSplitting=1,
    )
    doc.build(story, onFirstPage=running_header, onLaterPages=running_header,
              canvasmaker=NumberedCanvas)
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build(args.output)
