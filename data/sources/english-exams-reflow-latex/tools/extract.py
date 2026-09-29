"""Recover reading paragraphs from native PDF characters, not page screenshots."""
import re,statistics,html
from collections import Counter
import fitz

SITE=re.compile(r'(?:https?://)?(?:zhenti\.)?burningvocabulary\.(?:cn|com)',re.I)
OPTION=re.compile(r'(?<![A-Za-z])(?:\[([A-O])\]|([A-O])[.．)）])\s*')
QUESTION=re.compile(r'^\s*(\d{1,3})\s*[.．)）]\s*')
HEADING=re.compile(r'^(?:Section\s+(?:[IVXⅠⅡⅢⅣⅤ]+|[A-Z])(?=\s|$|[:：])|Part\s+(?:[IVXⅠⅡⅢⅣⅤ]+|[A-Z])(?=\s|$|[:：])|Text\s+\d+|Passage\s+(?:[A-Z\d]+|One|Two|Three)|TEST FOR|TIME LIMIT|Conversation\s+(?:One|Two)|Questions?\s+\d+)',re.I)

def bold_fraction(chars):
    letters=[c for c in chars if c['c'].isalpha()]
    return sum(bool(c.get('b')) for c in letters)/len(letters) if letters else 0

def centered_bold_title(row,page):
    """Recognize a printed reading title from its alignment and typeface."""
    rect=row['rect'];text=row['text'].strip()
    return (4<len(text)<120 and rect.width<page.rect.width*.8
            and abs((rect.x0+rect.x1)/2-(page.rect.x0+page.rect.x1)/2)<page.rect.width*.08
            and bold_fraction(row['chars'])>.75
            and not QUESTION.match(text) and not text.lower().startswith('directions'))

def option_matches(row,base):
    """Keep genuine same-row choices while rejecting initials inside prose."""
    candidates=list(OPTION.finditer(row['text']))
    if not candidates:return []
    accepted=[candidates[0]]
    for candidate in candidates[1:]:
        previous=accepted[-1]
        label=candidate[1] or candidate[2]
        previous_label=previous[1] or previous[2]
        prior=next((c for c in reversed(row['chars'][:candidate.start()])
                    if not c['c'].isspace() and 'x1' in c),None)
        current=row['chars'][candidate.start()]
        gap=current.get('x0',0)-prior['x1'] if prior and 'x0' in current else 0
        mark=lambda match: ')' if ')' in match[0] or '）' in match[0] else '.'
        has_value=bool(row['text'][previous.end():candidate.start()].strip())
        same_style=has_value and mark(candidate)==mark(previous)
        choice_sequence=(label in 'ABCD' and previous_label in 'ABCD'
                         and ord(label)>ord(previous_label))
        sequential=ord(label)==ord(previous_label)+1
        if gap>base*1.15 or same_style and (choice_sequence or sequential):
            accepted.append(candidate)
    return accepted

def plain(chars):return ''.join(c['c'] for c in chars)

def continues_wrapped_line(previous, current, pending, base):
    """A close lower-case/CJK line after unfinished prose is not a paragraph.

    PDF line starts may be indented by their text-map bbox even when the
    printed baseline continues the same paragraph.  Require the preceding
    line to be unfinished and the baselines to have normal line spacing;
    headings, numbered questions and option banks are handled separately.
    """
    if previous is None or not pending:
        return False
    prior = plain(pending).rstrip()
    following = current['text'].lstrip()
    if not prior or not following or re.search(r'[.!?。！？:：;；]\s*$', prior):
        return False
    if not 0 < current['y'] - previous['y'] <= base * 2.25:
        return False
    if not (re.match(r'[a-z]', following) or
            '\u4e00' <= prior[-1] <= '\u9fff' and '\u4e00' <= following[0] <= '\u9fff'):
        return False
    return not (QUESTION.match(following) or HEADING.match(following))

def glyphs_in_short_parentheses(chars):
    """A damaged Chinese gloss can use an inline crop without hiding its English line."""
    marked={i for i,c in enumerate(chars) if c.get('glyph_box')}
    if not marked:return False
    source=''.join(c.get('source_c',c['c']) for c in chars)
    stack=[];covered=set()
    for i,char in enumerate(source):
        if char in '(（':stack.append(i)
        elif char in ')）' and stack:
            start=stack.pop()
            if i-start<=35 and any(start<=j<=i for j in marked):
                covered.update(range(start,i+1))
    return marked<=covered

def normalize(chars):
    out=[]
    for c in chars:
        c=dict(c)
        if c['c'].isspace():
            c['c']=' '
            if not out or out[-1]['c']==' ':continue
        out.append(c)
    while out and out[-1]['c']==' ':out.pop()
    return out
def runs(chars):
    result=[]
    for c in normalize(chars):
        if c.get('glyph_box'):
            box=fitz.Rect(c['glyph_box']).normalize()
            if result and result[-1].get('glyph_box'):
                prior=fitz.Rect(result[-1]['glyph_box'])
                if abs(prior.y0-box.y0)<3 and -2<=box.x0-prior.x1<=2 and (prior|box).width <= c.get('glyph_font_size',12)*3:
                    result[-1]['glyph_box']=list(prior|box);result[-1]['text']+=c['c'];continue
            result.append({'text':c['c'],'flags':(False,False,False),'glyph_box':list(box),'glyph_font_size':c.get('glyph_font_size',12),'glyph_origin_y':c.get('glyph_origin_y',box.y1-2)});continue
        flags=(c.get('b',False),c.get('u',False),c.get('i',False))
        if result and not result[-1].get('glyph_box') and result[-1]['flags']==flags:result[-1]['text']+=c['c']
        else:result.append({'text':c['c'],'flags':flags})
    return result
def markup(r):
    result=[]
    for run in r:
        text=html.escape(run['text']);b,u,i=run['flags']
        if u:text='<u>'+text+'</u>'
        if i:text='<em>'+text+'</em>'
        if b:text='<strong>'+text+'</strong>'
        result.append(text)
    return ''.join(result)

def line_rects(page):
    under=[];draws=page.get_drawings()
    for d in draws:
        if d.get('fill') and min(d['fill'])>.95:continue
        for item in d['items']:
            if item[0]=='re':
                r=item[1]
                if r.height<=2 and r.width>2:under.append(r)
            elif item[0]=='l':
                a,b=item[1:3]
                if abs(a.y-b.y)<1.2 and abs(a.x-b.x)>2:under.append(fitz.Rect(min(a.x,b.x),min(a.y,b.y),max(a.x,b.x),max(a.y,b.y)+.7))
    return under,draws

def figures(page,draws):
    page_area=page.rect.get_area()
    text_lines=[]
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            text=''.join(span['text'] for span in line['spans']).strip()
            if text:text_lines.append((fitz.Rect(line['bbox']),text))

    def contained_text(rect):
        return [(box,text) for box,text in text_lines
                if (box & rect).get_area()>.5*box.get_area()]

    # White knockouts and page backgrounds often connect unrelated text and
    # graphics into one drawing cluster. They remain present in the final crop.
    ink=[]
    for drawing in draws:
        rect=drawing['rect'];fill=drawing.get('fill')
        if fill is not None and min(fill)>.94:continue
        if rect.get_area()>.7*page_area:continue
        ink.append(drawing)
    clusters=list(page.cluster_drawings(drawings=ink,x_tolerance=3,y_tolerance=3)) if ink else []
    shapes=[];small_boxes=[]
    for cluster in clusters:
        rect=fitz.Rect(cluster)
        if rect.width<8 or rect.height<8 or rect.get_area()>.65*page_area:continue
        members=[d for d in ink if (d['rect'] & rect).get_area()>.5*d['rect'].get_area()
                 or rect.contains(d['rect'])]
        words=contained_text(rect)
        char_count=sum(len(text) for _,text in words)
        rect_ops=sum(item[0]=='re' for d in members for item in d['items'])
        curves=any(item[0] in ('c','qu') for d in members for item in d['items'])
        diagonals=sum(item[0]=='l' and abs(item[1].x-item[2].x)>4
                      and abs(item[1].y-item[2].y)>4
                      for d in members for item in d['items'])
        shaded=any(d.get('fill') is not None and min(d['fill'])<.9
                   and any(item[0]!='re' or item[1].width>6 and item[1].height>6
                           for item in d['items']) for d in members)
        horizontal={round(d['rect'].y0/2)*2 for d in members
                    if d['rect'].width>rect.width*.45 and d['rect'].height<2}
        vertical={round(d['rect'].x0/2)*2 for d in members
                  if d['rect'].height>15 and d['rect'].width<2}
        grid=len(horizontal)>=3 and len(vertical)>=2 and rect_ops>=6
        diagram=(rect_ops>=2 and len(members)>=3 and char_count<160
                 and any(item[0] not in ('re','l') for d in members for item in d['items']))
        if 18<=rect.width<=60 and 10<=rect.height<=35 and rect_ops>=1:
            small_boxes.append(rect)
        elif rect.width>=55 and rect.height>=30 and (curves or diagonals>=2 or shaded or grid or diagram):
            # A single frame around a letter or an option bank is body text.
            if len(members)<=2 and char_count>120:continue
            shapes.append(rect)

    # Ordering questions use several separate small boxes linked by text
    # arrows. Keep the entire row as one figure so its sequence survives.
    groups=[]
    for rect in sorted(small_boxes,key=lambda r:(r.y0,r.x0)):
        group=next((g for g in groups if abs(rect.y0-g[0].y0)<12
                    and 0<=rect.x0-g[-1].x1<75),None)
        if group is None:groups.append([rect])
        else:group.append(rect)
    for group in groups:
        if len(group)<3:continue
        row=fitz.Rect(group[0])
        for rect in group[1:]:row|=rect
        for box,text in text_lines:
            if abs(box.y0-row.y0)<12 and box.x1>=row.x0-45 and box.x0<=row.x1+15:
                row|=box
        shapes.append(row)

    # Page scans and OCR text slices are not independent illustrations. Use
    # display instances, rather than xref counts, because one image may repeat.
    for image in page.get_image_info():
        rect=fitz.Rect(image['bbox'])
        if rect.width<30 or rect.height<25 or rect.get_area()<.005*page_area:continue
        if rect.get_area()>.65*page_area or rect.width>page.rect.width*.92 and rect.height>page.rect.height*.6:continue
        # OCR lines may cross the bitmap edge, so line-containment misses
        # text slices. Clipped text sees the fragments inside the image.
        chars=len(page.get_text(clip=rect).strip())
        if chars>40 and chars/rect.get_area()>.004:continue
        shapes.append(rect)

    # Combine chart panels on the same row, including the 2026 English I pie
    # and bars, before collecting labels that sit outside the drawn bounds.
    merged=[]
    for rect in sorted(shapes,key=lambda r:(r.y0,r.x0)):
        found=False
        for i,other in enumerate(merged):
            gap=max(0,rect.x0-other.x1,other.x0-rect.x1)
            overlap=max(0,min(rect.y1,other.y1)-max(rect.y0,other.y0))
            same_row=(overlap>.55*min(rect.height,other.height) and gap<page.rect.width*.11
                      and (rect|other).width<page.rect.width*.85)
            duplicate=(rect & other).get_area()>.6*min(rect.get_area(),other.get_area())
            if same_row or duplicate:
                merged[i]=rect|other;found=True;break
        if not found:merged.append(fitz.Rect(rect))

    result=[]
    for rect in merged:
        original=fitz.Rect(rect)
        nearby=fitz.Rect(rect.x0-24,rect.y0-24,rect.x1+24,rect.y1+24)&page.rect
        for box,text in text_lines:
            if not (box & nearby).get_area() or len(text)>40:continue
            if re.match(r'^\s*\d{1,3}[.)）]\s*[A-Za-z\u3400-\u9fff]',text) or HEADING.match(text):continue
            if box.y0>original.y1+4 and (box.width>original.width*.55 or len(text)>12):continue
            if box.x1<original.x0-20 or box.x0>original.x1+20:continue
            rect|=box
        rect=fitz.Rect(rect.x0-3,rect.y0-3,rect.x1+3,rect.y1+3)&page.rect
        if not any((rect & other).get_area()>.7*rect.get_area() for other in result):
            result.append(rect)
    return result

def extract(page,font_maps=None,unknown_glyphs=None,broad_source_blocks=True):
    font_maps=font_maps or {};under,draws=line_rects(page);figure_boxes=figures(page,draws)
    unknown={(round(g['origin'][0],3),round(g['origin'][1],3)):g for g in (unknown_glyphs or [])}
    entries=[];removed=[];uncertain=[];source_chars=[];figure_text=[]
    for block_id,block in enumerate(page.get_text('rawdict')['blocks']):
        for line in block.get('lines',[]):
            chars=[]
            for s in line['spans']:
                gaps=[b['bbox'][0]-a['bbox'][2] for a,b in zip(s['chars'],s['chars'][1:]) if a['c'].isascii() and b['c'].isascii() and a['c'].isalnum() and b['c'].isalnum()]
                space_gap=max(.6,(statistics.median(gaps) if gaps else 0)+s['size']*.12)
                for c in s['chars']:
                    letter=font_maps.get(s['font'],{}).get(c['c'],c['c']);rect=fitz.Rect(c['bbox']);x=(rect.x0+rect.x1)/2
                    is_unknown=(round(c['origin'][0],3),round(c['origin'][1],3)) in unknown
                    if is_unknown:letter='\ufffd'
                    glyph_rect=rect if rect.width>.1 else fitz.Rect(unknown.get((round(c['origin'][0],3),round(c['origin'][1],3)),{}).get('bbox',rect))
                    u=any(a.x0-.8<=x<=a.x1+.8 and rect.y1-4<=a.y0<=rect.y1+2 for a in under)
                    if any(ord(v)<32 and not v.isspace() or 0x80<=ord(v)<=0x9f or v=='\ufffd' for v in letter):uncertain.append({'text':letter,'font':s['font'],'bbox':list(rect)})
                    if chars and not is_unknown and letter[:1].isascii() and letter[:1].isalnum() and chars[-1]['c'].isascii() and not chars[-1]['c'].isspace() and rect.x0-chars[-1].get('x1',rect.x0)>space_gap:
                        chars.append({'c':' ','x1':rect.x0})
                    chars.extend({'c':v,'b':bool(s['flags']&16),'i':bool(s['flags']&2),'u':u,'x0':rect.x0,'x1':rect.x1,**({'glyph_box':list(glyph_rect),'glyph_font_size':s['size'],'glyph_origin_y':c['origin'][1],'source_c':c['c']} if is_unknown else {})} for v in letter)
            chars=normalize(chars);text=plain(chars)
            if not text:continue
            rect=fitz.Rect(line['bbox']);source_chars.append(text)
            if SITE.search(text) or rect.y1<page.rect.height*.027 or rect.y0>page.rect.height*.953:
                removed.append(text);continue
            if any((rect & f).get_area()>.75*rect.get_area() for f in figure_boxes):figure_text.append(text);continue
            entries.append({'block_id':block_id,'chars':chars,'rect':rect,'y':statistics.median(s['origin'][1] for s in line['spans']),'size':max(s['size'] for s in line['spans'])})
    unreliable_blocks=({entry['block_id'] for entry in entries
                        if any(c.get('glyph_box') for c in entry['chars'])}
                       if broad_source_blocks else set())
    rows=[]
    for line in sorted(entries,key=lambda x:(x['y'],x['rect'].x0)):
        if rows and abs(line['y']-rows[-1]['y'])<max(2,min(line['size'],rows[-1]['size'])*.27):
            row=rows[-1];row['parts'].append(line);row['rect']|=line['rect'];row['size']=max(row['size'],line['size'])
        else:rows.append({**line,'parts':[line]})
    for row in rows:
        parts=sorted(row['parts'],key=lambda x:x['rect'].x0);chars=[];last=None
        for part in parts:
            if chars and last is not None and part['rect'].x0-last>.8:chars.append({'c':' '})
            chars.extend(part['chars']);last=part['rect'].x1
        row['chars']=normalize(chars);row['text']=plain(row['chars'])
    left=Counter(round(r['rect'].x0/3)*3 for r in rows if len(r['text'])>50).most_common(1)
    margin=left[0][0] if left else 0
    sizes=[r['size'] for r in rows];base=statistics.median(sizes) if sizes else 12
    blocks=[];pending=[];pending_first=None;prev=None;question_row=None;options=[];option_content_x=None
    def flush_options():
        nonlocal options,option_content_x
        if options:
            # A-O labels also identify full reading paragraphs. A long,
            # wrapped lettered passage must stay a paragraph rather than a
            # two-column answer bank.
            if any(len(plain(cs))>150 for _,cs in options):
                for label,cs in options:
                    blocks.append({'type':'paragraph','runs':runs([{'c':label},{'c':')'},{'c':' '},*cs])})
            else:
                blocks.append({'type':'options','items':[{'label':a,'runs':runs(cs)} for a,cs in sorted(options,key=lambda x:x[0])]})
            options=[];option_content_x=None
    def flush():
        nonlocal pending,pending_first
        if pending:
            continuation=plain(pending).lstrip()
            prior=''.join(run['text'] for run in blocks[-1]['runs']) if blocks and blocks[-1]['type']=='question' else ''
            wrapped=(question_row is not None and pending_first is not None and
                     len(prior)>25 and not re.search(r'[.!?。！？:：;；]\s*$',prior) and
                     bool(re.match(r'[a-z]',continuation)) and
                     not re.search(r'\b[1-5]\s+[0-9]\s*[.．]',continuation) and
                     not re.search(r'\b(?:Section\s+[A-C]\b|Directions:)',continuation) and
                     0<pending_first['y']-question_row['y']<=base*2.1 and
                     -base*4<=pending_first['rect'].x0-question_row['rect'].x0<=base*4)
            if wrapped:
                if not prior.endswith('-'):blocks[-1]['runs'].append({'text':' ','flags':(False,False,False)})
                blocks[-1]['runs'].extend(runs(pending))
            else:blocks.append({'type':'paragraph','runs':runs(pending)})
            pending=[];pending_first=None
    events=sorted([(r['rect'].y0,'row',r) for r in rows]+[(r.y0,'figure',r) for r in figure_boxes],key=lambda x:x[0])
    for y,kind,row in events:
        if kind=='figure':flush();flush_options();blocks.append({'type':'figure','bbox':list(row)});prev=None;continue
        text=row['text'];cs=row['chars']
        if (any(part['block_id'] in unreliable_blocks for part in row['parts'])
                or any(c.get('glyph_box') for c in cs) and not glyphs_in_short_parentheses(cs)):
            flush();flush_options();blocks.append({'type':'source_line','bbox':list((row['rect']+(-1,-1,1,1))&page.rect),'font_size':row['size'],'runs':runs(cs)});prev=None;continue
        caption_prefix=re.match(r'^\s*(?:Directions\b|Part\s*[ⅠⅡⅢⅣⅤIVX0-9]|Section\b|注意|注[：:])',text,re.I)
        is_caption=(len(plain(pending))<70 and not options and blocks and blocks[-1]['type'] in ('figure','caption')
            and any(0<=row['rect'].y0-f.y1<=35 and abs((row['rect'].x0+row['rect'].x1-f.x0-f.x1)/2)<max(25,f.width*.3) for f in figure_boxes)
            and len(text)<180 and not QUESTION.match(text) and not HEADING.match(text) and not caption_prefix)
        if is_caption:
            flush();flush_options();blocks.append({'type':'caption','runs':runs(cs)});prev=None;continue
        q=QUESTION.match(text);matches=option_matches(row,base)
        # A question/option label must be at the row start, not A/B/C in prose.
        valid_options=bool(matches and (matches[0].start()==0 or q and matches[0].start()<=q.end()+2))
        # A wrapped enumeration in prose (A, B, C or / D.) is not an answer bank.
        if pending and re.search(r'(?:[A-D],\s*){2,}[A-D]\s*(?:or|and)?\s*$',plain(pending)):
            valid_options=False
        if valid_options:
            flush()
            if q:
                flush_options();blocks.append({'type':'question','runs':runs(cs[:matches[0].start()])})
            for i,m in enumerate(matches):
                label=m[1] or m[2];end=matches[i+1].start() if i+1<len(matches) else len(cs)
                if any(a==label for a,_ in options):flush_options()
                options.append((label,cs[m.end():end]))
                option_content_x=(cs[m.end()]['x0'] if m.end()<end else cs[m.start()]['x0']+base*1.5)
            prev=row;continue
        if options:
            # Wrapped answers and A-O reading paragraphs begin at the answer
            # text indent, typically 1-2 em to the right of their label.
            # Keep them with the preceding item while their baseline spacing
            # and indent agree; a new heading/question or left-margin prose
            # ends the group.
            close=prev is not None and 0<row['y']-prev['y']<=max(base*2.1,prev['size']*2.1)
            aligned=(option_content_x is not None and
                     option_content_x-max(base*1.25,4)<=row['rect'].x0<=option_content_x+max(base*3,20))
            if close and aligned and not q and not HEADING.match(text):
                item_chars=options[-1][1]
                if item_chars and plain(item_chars)[-1:]!='-' and text[:1] and not (
                    '\u4e00'<=plain(item_chars)[-1:]<='\u9fff' and '\u4e00'<=text[:1]<='\u9fff'
                ):item_chars.append({'c':' '})
                item_chars.extend(cs);prev=row;continue
            flush_options()
        heading=bool(HEADING.match(text) or centered_bold_title(row,page)
                     or row['size']>base*1.28 and (bold_fraction(cs)>.5 or q)
                     or len(text)<90 and text.rstrip(':：').lower()=='directions')
        if heading:
            flush();blocks.append({'type':'heading' if not text.lower().startswith('questions') else 'instruction','runs':runs(cs)});prev=None;continue
        if q:
            flush();blocks.append({'type':'question','runs':runs(cs)});question_row=row;prev=row;continue
        new=(prev is None or row['y']-prev['y']>base*2.25
             or margin+base*.9<row['rect'].x0<margin+base*5
             or prev is not None and base*.85<row['rect'].x0-prev['rect'].x0<base*5)
        if new and not continues_wrapped_line(prev,row,pending,base):flush()
        if pending:
            before=plain(pending)[-1:];after=text[:1]
            if before!='-' and not ('\u4e00'<=before<='\u9fff' and '\u4e00'<=after<='\u9fff'):pending.append({'c':' '})
        if not pending:pending_first=row
        pending.extend(cs);prev=row
    flush();flush_options()
    consolidated=[]
    for block in blocks:
        if block['type']=='source_line' and consolidated and consolidated[-1]['type']=='source_line':
            prior=consolidated[-1]
            if block['bbox'][1]-prior['bbox'][3]<base*2.5:
                prior['bbox']=list(fitz.Rect(prior['bbox'])|fitz.Rect(block['bbox']));prior['runs'].extend(block['runs']);continue
        consolidated.append(block)
    blocks=consolidated
    before=Counter(c for r in rows for c in r['text'] if c.isalnum())
    after=Counter()
    for b in blocks:
        for r in b.get('runs',[]):after.update(c for c in r['text'] if c.isalnum())
        for item in b.get('items',[]):
            after.update(item['label'])
            for r in item['runs']:after.update(c for c in r['text'] if c.isalnum())
    assert before==after,{'missing':dict(before-after),'extra':dict(after-before)}
    return {'blocks':blocks,'removed_marginal_text':removed,'figure_text':figure_text,'encoding_uncertain':uncertain,'source_text':'\n'.join(source_chars),'body_chars':sum(len(x['text']) for x in rows),'body_character_conservation':True,'figures':len(figure_boxes)}
