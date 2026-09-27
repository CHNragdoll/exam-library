"""Exact line geometry for the user-approved 2025 Q38 TCP figure.

Device artwork is retained in two clipped image regions. Timelines, arrows,
labels, time markers and shared endpoints are native SVG geometry/text.
"""
import base64
import math
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'data/sources/exam-library/assets/redrawn'
SOURCE = ASSETS / 'cs408-2025-questions-p005-b001.png'
OUTPUT = ASSETS / 'cs408-2025-questions-p005-b001-precise.svg'
SEGMENTS = {
    'time-left': (158, 276, 158, 1110),
    'time-right': (1270, 294, 1270, 1110),
    'seq-2001': (158, 338, 1270, 620),
    'seq-3001': (158, 438, 830, 608),
    'return-ack': (1270, 620, 158, 950),
    'next-message': (158, 950, 344, 1005),
}

def build():
    encoded = base64.b64encode(SOURCE.read_bytes()).decode()
    arrows = '\n'.join(f'<line id="{name}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" marker-end="url(#arrow)"/>' for name,(x1,y1,x2,y2) in SEGMENTS.items())
    angle_send=math.degrees(math.atan2(620-338,1270-158))
    angle_return=math.degrees(math.atan2(620-950,1270-158))
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1380" height="1140" viewBox="0 0 1380 1140" role="img" aria-labelledby="title description">
<title id="title">2025年408第38题 TCP报文交互图：精确SVG</title>
<desc id="description">甲乙两条时间轴。seq=2001的报文到达乙，seq=3001的报文中途结束。乙返回seq=4001, ack_seq=3001, rcvwnd=4000 B至甲t1。保留原题端点，所有线段均为SVG直线。</desc>
<defs>
<marker id="arrow" viewBox="0 0 10 10" markerWidth="34" markerHeight="34" refX="10" refY="5" orient="auto" markerUnits="userSpaceOnUse"><path d="M 0 0 L 10 5 L 0 10 L 2.5 5 Z" fill="#000"/></marker>
<image id="device-artwork" width="1381" height="1139" xlink:href="data:image/png;base64,{encoded}"/>
<clipPath id="left-icon"><rect x="5" y="68" width="260" height="208"/><rect x="5" y="276" width="140" height="28"/></clipPath>
<clipPath id="right-icon"><rect x="1186" y="76" width="180" height="223"/></clipPath>
</defs>
<rect width="1380" height="1140" fill="#fff"/>
<g clip-path="url(#left-icon)"><use xlink:href="#device-artwork"/></g>
<g clip-path="url(#right-icon)"><use xlink:href="#device-artwork"/></g>
<g fill="none" stroke="#000" stroke-width="5" stroke-linecap="butt">{arrows}</g>
<g fill="#000"><circle cx="158" cy="338" r="14"/><circle cx="158" cy="950" r="14"/></g>
<g font-family="'Times New Roman', 'Songti SC', 'Noto Serif CJK SC', serif" fill="#000" font-size="44">
<text x="160" y="48" text-anchor="middle">甲</text><text x="1285" y="58" text-anchor="middle">乙</text>
<text x="112" y="350" text-anchor="end" font-style="italic">t<tspan baseline-shift="sub" font-size="28">0</tspan></text>
<text x="112" y="962" text-anchor="end" font-style="italic">t<tspan baseline-shift="sub" font-size="28">1</tspan></text>
<text x="36" y="1110">时间</text>
<text x="236" y="316" transform="rotate({angle_send:.8f} 236 316)">seq = 2001, 1000 B数据</text>
<text x="236" y="416" transform="rotate({angle_send:.8f} 236 416)">seq = 3001, 1000 B数据</text>
<text x="245" y="898" transform="rotate({angle_return:.8f} 245 898)">seq = 4001, ack_seq = 3001, rcvwnd = 4000 B</text>
</g></svg>'''
    OUTPUT.write_text(svg)
    verify()
    print(OUTPUT)

def verify():
    tree=ET.parse(OUTPUT);ns={'s':'http://www.w3.org/2000/svg'}
    lines={el.attrib['id']:el.attrib for el in tree.findall('.//s:line',ns)}
    assert len(lines)==6
    for name,coords in SEGMENTS.items():
        assert tuple(float(lines[name][k]) for k in ('x1','y1','x2','y2'))==coords
    assert (lines['seq-2001']['x2'],lines['seq-2001']['y2'])==(lines['return-ack']['x1'],lines['return-ack']['y1'])
    assert float(lines['seq-3001']['x2']) < float(lines['time-right']['x1'])
    text=''.join(tree.getroot().itertext())
    for field in ('seq = 2001, 1000 B数据','seq = 3001, 1000 B数据','seq = 4001, ack_seq = 3001, rcvwnd = 4000 B'):assert field in text

if __name__=='__main__':build()
