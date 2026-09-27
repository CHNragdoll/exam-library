"""Semantic presentation for short choices and vector ordering diagrams."""
import re
import fitz

def content(runs):return ''.join(r['text'] for r in runs)
def prepare(blocks,page):
    output=[];i=0
    while i<len(blocks):
        b=blocks[i]
        if b['type']=='question' and re.fullmatch(r'\s*\d+[.)）]\s*',content(b['runs'])) and i+1<len(blocks):
            nxt=blocks[i+1]
            if nxt['type']=='options' and [x['label'] for x in nxt['items']]==list('ABCD'):
                values=[content(x['runs']) for x in nxt['items']]
                if all(len(t)<=28 and max(map(len,t.split()),default=0)<=18 for t in values) and sum(map(len,values))<=96:
                    output.append({'type':'choice_row','runs':b['runs'],'items':nxt['items']});i+=2;continue
        if b['type']=='figure':
            box=fitz.Rect(b['bbox']);text=page.get_text(clip=box).strip()
            tokens=re.findall(r'\d+\.|[A-Z]',text)
            residue=re.sub(r'\d+\.|[A-Z]|[→➔⇒\s]','',text)
            if box.height<65 and not residue and '→' in text and sum(t[0].isdigit() for t in tokens)>=3:
                b={**b,'type':'flowchart','tokens':tokens}
        output.append(b);i+=1
    return output

def copy_flowchart(page,box,dest):
    """Keep original box proportions, labels and vector artwork."""
    clip=fitz.Rect(box)&page.rect
    doc=fitz.open();out=doc.new_page(width=clip.width,height=clip.height)
    out.show_pdf_page(out.rect,page.parent,page.number,clip=clip)
    dest.with_suffix('.svg').write_text(out.get_svg_image(text_as_path=True))
    doc.save(dest.with_suffix('.pdf'))
    out.get_pixmap(dpi=180).save(dest.with_suffix('.png'));doc.close()

def continues_paragraph(previous,current):
    """Join only unambiguous mid-sentence prose across a source page edge."""
    if previous.get('type')!='paragraph' or current.get('type')!='paragraph':return False
    a=content(previous['runs']).rstrip();b=content(current['runs']).lstrip()
    return len(a)>60 and bool(re.search(r'[A-Za-z,;—-]$',a)) and bool(re.match(r'[a-z]',b))
