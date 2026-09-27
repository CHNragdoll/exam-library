"""Offline paper rendering. Keep source glyph outlines and geometry together.

SVG resources are isolated inside data images, avoiding cross-page font IDs.
Selectable text is a separate layer; source text remains available in <pre>.
"""
import base64
import hashlib
import html
import math
import re
from lxml import etree

RENDERER_VERSION = 'outline-svg-2-clean'
from catalog_design import page_without_url
STYLE = '''
*{box-sizing:border-box}html{background:#edf0f4;color:#243044;font:16px/1.6 system-ui,sans-serif}
body{margin:0;min-width:0}header,footer{max-width:940px;margin:28px auto;padding:0 20px;overflow-wrap:anywhere}
h1{font-size:clamp(21px,3vw,28px);line-height:1.4}a{color:#1258a2}header p,footer{color:#526074;font-size:14px}
.page-wrap{max-width:940px;width:100%;margin:26px auto;padding:0 14px;min-width:0}
.page-label{text-align:center;color:#637083;font-size:13px;margin:8px}
.sheet{width:100%;min-width:0;background:#fff;box-shadow:0 2px 12px #0001;border-radius:3px}
.paper-frame{position:relative;width:100%;min-width:0;line-height:0;background:white;overflow:hidden}
.page-art{display:block;width:100%;height:auto;user-select:none;-webkit-user-select:none}
.text-overlay{position:absolute;inset:0;display:block;width:100%;height:100%;overflow:hidden;user-select:text;-webkit-user-select:text}
.text-overlay text{fill:transparent;white-space:pre;cursor:text}.text-overlay text::selection{fill:transparent;background:#8bbbf080}
.page-text{padding:12px 18px;border-top:1px solid #e1e6ed;font:14px/1.65 system-ui,sans-serif}
.page-text summary{cursor:pointer;color:#1258a2;min-height:28px}.page-text pre{font:16px/1.8 system-ui,sans-serif;white-space:pre-wrap;overflow-wrap:anywhere;margin:14px 0}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:pre;border:0}
.source-warning{color:#875a0c;font-size:13px;line-height:1.6}
@media(max-width:600px){header,footer{padding:0 12px}.page-wrap{padding:0 6px;margin:18px auto}.page-text{padding:10px 12px}}
@media print{html{background:white}header,footer,.page-label,.page-text,.sr-only{display:none}.page-wrap{max-width:none;margin:0;padding:0;break-after:page;break-inside:avoid}.sheet{box-shadow:none}.text-overlay{display:none}}
'''

def digest(data):
    return hashlib.sha256(data).hexdigest()

def safe_text(text):
    # XML cannot represent C0 controls. Keep the exact source in the cached JSON;
    # expose a replacement glyph in the copy view instead of silently dropping it.
    text=text.replace('\r\n','\n').replace('\r','\n')
    return ''.join(c if c in '\t\n\r' or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or ord(c) >= 0x10000 else '\ufffd' for c in text)

def validate_svg(root):
    ids = root.xpath('//@id')
    assert len(ids) == len(set(ids)), 'duplicate IDs inside a page'
    ids = set(ids)
    assert not root.xpath('//*[local-name()="script" or local-name()="foreignObject"]')
    for el in root.iter():
        for name, value in el.attrib.items():
            local = etree.QName(name).localname
            assert not local.lower().startswith('on'), 'event handler in SVG'
            if local in ('href', 'src'):
                assert value.startswith(('#', 'data:image/')), 'external SVG resource'
                if value.startswith('#'):
                    assert value[1:] in ids, 'missing SVG resource'
            for ref in re.findall(r'url\((.*?)\)', value):
                assert ref.strip('"\'').startswith('#'), 'external SVG URL'

def render_page(page, number, asset_path=None):
    original_page=page
    page,temporary_doc,removed_urls=page_without_url(page)
    source = page.get_svg_image(text_as_path=True).encode()
    root = etree.fromstring(source)
    validate_svg(root)
    width, height = page.rect.width, page.rect.height
    # Isolated <img> documents allow the original SVG bytes, IDs and glyphs to
    # remain unchanged. No font substitution is involved in the visible page.
    encoded = base64.b64encode(source).decode()
    image_src='data:image/svg+xml;base64,'+encoded
    if asset_path is not None:
        asset_path.parent.mkdir(parents=True,exist_ok=True)
        asset_path.write_bytes(source)
        image_src=asset_path.parent.name+'/'+asset_path.name
    svg_ns = 'http://www.w3.org/2000/svg'
    overlay = etree.Element('{'+svg_ns+'}svg', nsmap={None:svg_ns})
    overlay.set('class', 'text-overlay')
    overlay.set('viewBox', f'0 0 {width} {height}')
    overlay.set('aria-hidden', 'true')
    overlay.set('focusable', 'false')
    for block in page.get_text('rawdict')['blocks']:
        for line in block.get('lines', []):
            angle = math.degrees(math.atan2(line['dir'][1], line['dir'][0]))
            for span in line['spans']:
                chars = span['chars']
                if not chars:
                    continue
                text = safe_text(''.join(c['c'] for c in chars))
                x, y = span['origin']
                el = etree.SubElement(overlay, '{'+svg_ns+'}text')
                el.set('x', str(x)); el.set('y', str(y))
                el.set('font-size', str(span['size']))
                el.set('font-family', 'serif')
                el.set('fill', 'transparent')
                el.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                box = span['bbox']
                length = math.hypot(box[2]-box[0], box[3]-box[1]) if angle else box[2]-box[0]
                if length > 0:
                    el.set('textLength', str(length))
                    el.set('lengthAdjust', 'spacingAndGlyphs')
                if angle:
                    el.set('transform', f'rotate({angle} {x} {y})')
                el.text = text
    text = page.get_text('text')
    warning = any(ord(c) < 32 and c not in '\t\r\n' or 0x80 <= ord(c) <= 0x9f or c == '\ufffd' for c in text)
    note = '<p class="source-warning">本页源文件的文字编码有异常。原卷显示正常；复制文字需对照原卷核查。</p>' if warning else ''
    markup = (f'<div class="paper-frame" style="aspect-ratio:{width}/{height}">'
              f'<img class="page-art" width="{width}" height="{height}" alt="" aria-hidden="true" loading="lazy" decoding="async" src="{image_src}">'
              + etree.tostring(overlay, encoding='unicode') + '</div>'
              + '<div class="sr-only" aria-label="本页文字">'+html.escape(safe_text(text))+'</div>'
              + '<details class="page-text"><summary>查看 / 复制本页文字</summary>'+note
              + '<pre class="source-text">'+html.escape(safe_text(text))+'</pre></details>')
    return markup, {'page':number, 'width':width, 'height':height,
                    'svg_sha256':digest(source), 'text_sha256':digest(original_page.get_text('text').encode()),
                    'display_text_sha256':digest(text.encode()),'removed_url_rectangles':removed_urls,
                    'source_encoding_warning':warning,
                    'embedded_source_images':len(root.xpath('//*[local-name()="image"]')),
                    'visible_text_uses_source_glyph_outlines':True}
