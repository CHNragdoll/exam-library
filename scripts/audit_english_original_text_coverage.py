#!/usr/bin/env python3
"""Read-only English original SVG-text/reflow/structured coverage triage.

Outputs candidates, never repairs sources. Run with the repository's Python:
 .venv/bin/python scripts/audit_english_original_text_coverage.py
Only the named report directory is written. No browser/PDF visual claim is made.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / 'data/sources'
ORIGINAL = SOURCES / 'english-exams-web-2026-09-26'
REFLOW = SOURCES / 'english-exams-reflow-latex'
STRUCTURED = SOURCES / 'exam-library/structured/papers'
SECTION = re.compile(r'<section\b([^>]*)>(.*?)</section>', re.S)
TEXT = re.compile(r'<text\b([^>]*)>(.*?)</text>', re.S)
ATTR = re.compile(r'([\w:-]+)=["\']([^"\']*)["\']')
QUESTION = re.compile(r'^\s*(\d(?:\s?\d){0,2})\s*[.)．]\s*(.*)$', re.S)
OPTION = re.compile(r'(?:^|\s)([A-D])\s*[)）.．]\s*(.*?)(?=(?:\s+[A-D]\s*[)）.．])|$)', re.S)

def plain(s):
    s = re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)>', '', s, flags=re.S)
    return html.unescape(re.sub(r'<[^>]+>', '', s))

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKC', s).lower() if c.isalnum())

def gramset(s, n=5):
    return {s[i:i+n] for i in range(max(0, len(s)-n+1))}

def similarity(s, target, grams):
    if not s:
        return 1.0
    if s in target:
        return 1.0
    gs = gramset(s)
    return round(len(gs & grams) / max(1, len(gs)), 3)

def read(path):
    raw = path.read_bytes()
    return raw.decode('utf-8'), hashlib.sha256(raw).hexdigest()

def source_lines(section):
    spans = []
    for at, body in TEXT.findall(section):
        a = dict(ATTR.findall(at)); t = plain(body)
        if not t.strip(): continue
        spans.append({'x': float(a.get('x', 0)), 'y': float(a.get('y', 0)),
                      'w': float(a.get('textLength', 0)), 'size': float(a.get('font-size', 12)), 'text': t})
    rows = []
    for s in sorted(spans, key=lambda z: (z['y'], z['x'])):
        row = next((r for r in rows[-3:] if abs(r['y']-s['y']) <= min(3, s['size']*.22)), None)
        if row is None:
            row = {'y': s['y'], 'spans': []}; rows.append(row)
        row['spans'].append(s)
    lines = []
    for row in rows:
        current = None
        for s in sorted(row['spans'], key=lambda z:z['x']):
            gap = s['x'] - (current['right'] if current else s['x'])
            # Wide horizontal whitespace usually separates columns/options.
            if current is None or gap > max(24, s['size']*2.4):
                current={'x':s['x'],'y':row['y'],'right':s['x']+s['w'],'text':s['text']};lines.append(current)
            else:
                separator = ' ' if gap > max(.9, s['size']*.15) and not current['text'].endswith(' ') and not s['text'].startswith(' ') else ''
                current['text'] += separator+s['text'];current['right']=max(current['right'],s['x']+s['w'])
    return lines, len(spans)

def audit(out):
    manifest=json.loads((REFLOW/'manifest.json').read_text())
    documents=[]; candidates=[]; page_stats=[]; totals=Counter()
    for row in manifest['papers']:
        rel=Path(row['file']);cat=row['category'];stem=rel.stem
        original=ORIGINAL/rel;reflow=REFLOW/rel;structured=STRUCTURED/cat/(stem+'.json')
        missing=[str(p.relative_to(ROOT)) for p in (original,reflow,structured) if not p.exists()]
        if missing:
            documents.append({'id':f'{cat}:{stem}','missing_files':missing});continue
        orig,osh=read(original);rf,rsh=read(reflow);sj,ssh=read(structured);bank=json.loads(sj)
        rfmain=re.search(r'<main\b[^>]*>(.*?)</main>',rf,re.S)
        rtext=norm(plain(rfmain.group(1) if rfmain else rf));rgrams=gramset(rtext)
        qtext=norm(' '.join(q.get('stem','')+' '+' '.join(o.get('text','') for o in q.get('options',[])) for q in bank['questions']))
        qgrams=gramset(qtext);qnums={str(q['number']).strip() for q in bank['questions']}
        blocktext=norm(' '.join(b.get('text','') for b in bank['blocks']))
        bgrams=gramset(blocktext)
        rfpages={dict(ATTR.findall(a)).get('data-source-page'):body for a,body in SECTION.findall(rf) if 'data-source-page' in a}
        records=[]
        for at,body in SECTION.findall(orig):
            a=dict(ATTR.findall(at));page=a.get('data-page')
            if not page:continue
            lines,nspans=source_lines(body);totals['original_pages']+=1;totals['svg_text_spans']+=nspans
            totals['original_pages_with_text']+=bool(nspans)
            view=re.search(r'class="text-overlay"[^>]*viewBox="([^"]+)"',body)
            width=float(view.group(1).split()[2]) if view else 595
            pdf=(SOURCES/'kaoyan-web-2026-09-26'/'.firecrawl'/(stem+'.pdf')) if cat=='kaoyan' else ORIGINAL/'.firecrawl'/cat/(stem+'.pdf')
            common={'document':f'{cat}:{stem}','category':cat,'paper':stem,'page':int(page),
                    'original_html':str(original.relative_to(ROOT)),
                    'original_pdf':str(pdf.relative_to(ROOT)),'pdf_exists':pdf.exists()}
            image_only=len(norm(plain(rfpages.get(page,''))))<50 and '<img' in rfpages.get(page,'')
            evaluated=[];anchors=[]
            for ln in lines:
                t=ln['text'].strip();n=norm(t);words=re.findall(r'[A-Za-z]{2,}',t)
                # Exclude page footers/URLs, but not exam questions ABOUT advertising.
                if 'burningvocabulary' in t or 'https://' in t: continue
                m=QUESTION.match(t)
                if m and ln['x']<width*.28 and 0<int(re.sub(r'\s','',m[1]))<=100:
                    num=str(int(re.sub(r'\s','',m[1])));tail=m[2]
                    # 1) writing instructions remain low confidence; nearby sequence is reported.
                    anchors.append((ln,num,tail))
                if len(words)>=6 and len(n)>=28:
                    rs=similarity(n,rtext,rgrams);bs=similarity(n,blocktext,bgrams)
                    evaluated.append((ln,rs,bs))
            for ln,num,tail in anchors:
                totals['source_question_anchors']+=1
                # Cloze blank numbers embedded in passage are not line anchors with prose/option tails.
                if num not in qnums:
                    sequential=any(abs(int(other)-int(num))==1 for _,other,_ in anchors)
                    obvious=bool(re.match(r'[A-D]\s*[).]',tail)) or (len(re.findall(r'[A-Za-z]+',tail))>=5 and sequential)
                    candidates.append({**common,'kind':'question_number_absent','confidence':'candidate_high' if obvious else 'ambiguous_anchor',
                        'number':num,'y':round(ln['y'],2),'text':ln['text'],'reflow_match':similarity(norm(tail),rtext,rgrams),
                        'reason':'Original line-start number absent from all structured question records; subitems/OCR can be false positives.'})
            for ln,rs,bs in evaluated:
                totals['evaluated_text_segments']+=1
                if rs>=.9:totals['segments_reflow_covered']+=1
                if bs>=.9:totals['segments_structured_blocks_covered']+=1
                if rs<.55:
                    records.append({**common,'kind':'text_segment_absent','confidence':'image_fallback' if image_only else 'candidate',
                        'y':round(ln['y'],2),'text':ln['text'],'reflow_match':rs,'structured_blocks_match':bs})
                for om in OPTION.finditer(ln['text']):
                    label,ot=om.groups();on=norm(ot)
                    if len(re.findall(r'[A-Za-z]{2,}',ot))<4 or len(on)<18:continue
                    totals['source_option_segments']+=1
                    qs=similarity(on,qtext,qgrams)
                    if qs>=.84:totals['option_segments_question_covered']+=1;continue
                    prev=[(l,n) for l,n,_ in anchors if l['y']<=ln['y']+3]
                    nearest=max(prev,key=lambda z:z[0]['y'])[1] if prev else None
                    candidates.append({**common,'kind':'option_text_absent_from_questions','confidence':'candidate' if rs>=.84 else 'ocr_or_image_candidate',
                        'nearest_preceding_number':nearest,'label':label,'y':round(ln['y'],2),'text':ot,'question_text_match':qs,'reflow_line_match':rs,
                        'reason':'Coordinate-nearest question is a hint, not guaranteed under columns/page continuations.'})
            # Consecutive low-match lines are stronger than an isolated corrupted OCR word.
            runs=[];cur=[]
            lowys={id(l) for l,rs,_ in evaluated if rs<.55}
            for l,rs,bs in evaluated:
                if rs<.55:cur.append((l,rs,bs))
                elif cur:runs.append(cur);cur=[]
            if cur:runs.append(cur)
            for run in runs:
                if len(run)<3 or sum(len(re.findall(r'[A-Za-z]{2,}',l['text'])) for l,_,_ in run)<28:continue
                candidates.append({**common,'kind':'consecutive_text_run_absent','confidence':'image_fallback' if image_only else 'candidate_high',
                    'line_count':len(run),'y_start':round(run[0][0]['y'],2),'y_end':round(run[-1][0]['y'],2),
                    'text':' '.join(l['text'] for l,_,_ in run),'mean_reflow_match':round(sum(r for _,r,_ in run)/len(run),3),
                    'reason':'At least 3 low-match English segments, >=28 words. Inspect original PDF; OCR can affect whole lines.'})
            page_stats.append({**common,'spans':nspans,'evaluated_segments':len(evaluated),'low_match_segments':len(records),
                               'reflow_image_only':image_only,'source_question_anchors':[n for _,n,_ in anchors]})
            records=[]
        documents.append({'id':f'{cat}:{stem}','original_sha256':osh,'reflow_sha256':rsh,'structured_sha256':ssh,
                          'original_file':str(original.relative_to(ROOT)),'reflow_file':str(reflow.relative_to(ROOT)),
                          'structured_file':str(structured.relative_to(ROOT)),'structured_question_count':len(bank['questions'])})
        totals['documents']+=1
        if totals['documents']%25==0:print(f"audited {totals['documents']}/{len(manifest['papers'])}",flush=True)
    result={'created_at':datetime.now(timezone.utc).isoformat(),'method':'English alphanumeric 5-gram inclusion; coordinate-joined SVG text segments; >=0.90 covered, <0.55 low-match; candidate report only',
            'limits':['SVG text is a selectable text layer but may contain OCR/font-mapping errors; no automated claim of semantic accuracy.',
                      'English only: Chinese translation, formula glyphs, diagrams, audio, page-image text and source text absent from original SVG are not certified.',
                      'Short options (<4 English words) and segments (<6 words) are excluded from content comparison.',
                      'Question anchors can be numbered instructions; option mapping across columns/page breaks needs human verification.',
                      'No full PDF visual review in this automated pass; prior 18-page visual QA is separate.',
                      'Inputs may be concurrently rebuilt; per-file hashes identify this snapshot.'],
            'totals':dict(totals),'documents':documents,'pages':page_stats,'candidates':candidates,
            'candidate_counts':dict(Counter(c['kind'] for c in candidates))}
    # Focused deterministic handoff: anchored numbers absent from independent cards.
    # Do not call image text or cloze word blanks lost reading-comprehension cards.
    focused=[]
    for c in candidates:
        if c['kind']!='question_number_absent': continue
        qpath=STRUCTURED/c['category']/(c['paper']+'.json')
        qs=json.loads(qpath.read_text())['questions']
        m=QUESTION.match(c['text']);tail=m[2] if m else ''
        if re.match(r'^\d+(?:\.\d+)?%',tail):
            classification='excluded_chart_axis_number'
        elif c['category'] in ('cet4','cet6') and 26<=int(c['number'])<=35:
            classification='excluded_cloze_blank_anchor'
        elif '→' in c['text']:
            classification='diagram_matching_slots_no_independent_cards'
        elif c['category']=='kaoyan' and int(c['number']) in range(41,46):
            classification='matching_table_question_no_independent_card'
        else:
            classification='independent_question_no_card'
        probe=norm(re.sub(r'^[A-D]\s*[).]\s*','',tail))[:65]
        contained=[]
        if len(probe)>=15:
            for q in qs:
                body=norm(q.get('stem','')+' '+' '.join(o.get('text','') for o in q.get('options',[])))
                if probe in body:contained.append(q['id'])
        focused.append({**c,'classification':classification,'content_contained_in_other_cards':contained,
                        'coordinate_evidence':'Original inline SVG baseline in y field; question marker left of 28% page width.',
                        'evidence_type':'original_HTM_coordinate_and_structured_JSON_presence_check'})
    result['focused_question_counts']=dict(Counter(c['classification'] for c in focused))
    result['focused_questions']=focused
    out.mkdir(parents=True,exist_ok=True)
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    lines=['# English original SVG-text coverage audit','',f"Generated: {result['created_at']}",'',json.dumps(result['totals'],ensure_ascii=False),'',str(result['candidate_counts']),'','## Limits','']
    lines += ['- '+x for x in result['limits']]
    lines+=['','## Candidate list (not confirmed defects)','']
    for c in candidates:
        lines += [f"- **{c['document']} p{c['page']} {c['kind']} [{c['confidence']}]** " + str(c.get('number',c.get('nearest_preceding_number',''))) + ': '+c['text'][:600].replace('\n',' ') ]
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    focused_result={'created_at':result['created_at'],'counts':result['focused_question_counts'],
        'scope':'206 original HTMs audited; only recognizable line-start numeric anchors audited here. Not a complete count of every blank/diagram question.',
        'findings':focused,'document_input_hashes':documents}
    (out/'missing-question-candidates.json').write_text(json.dumps(focused_result,ensure_ascii=False,indent=2)+'\n')
    rows=['# Original-HTM anchored missing-card handoff','',str(focused_result['counts']),'',focused_result['scope'],'',
          'Original HTM coordinates and current JSON question-number presence were checked; no new PDF visual claim.','']
    grouped=defaultdict(list)
    for c in focused:grouped[(c['classification'],c['document'],c['page'])].append(c['number'])
    for (cl,doc,pg),nums in sorted(grouped.items()):rows.append(f'- {cl}: {doc} p{pg}: Q'+', Q'.join(nums))
    (out/'missing-question-candidates.md').write_text('\n'.join(rows)+'\n')
    print(json.dumps({'totals':result['totals'],'candidates':result['candidate_counts'],'report':str(out/'report.json')},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'.local/english-original-text-coverage');args=p.parse_args();audit(args.output)
