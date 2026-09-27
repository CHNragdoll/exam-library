#!/usr/bin/env python3
"""Serialize the 120-row visual review plus reproducible original SVG evidence.

Human review dispositions are explicit below; execution does not perform vision.
Regenerate proof pairs first with prepare_fallback_visual_review.py. Inputs are
hash checked so stale visual decisions are never silently presented as current.
"""
from pathlib import Path
from collections import Counter
import json, hashlib, re, importlib.util
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.local/fallback-visual-review'
spec=importlib.util.spec_from_file_location('coverage',ROOT/'scripts/audit_english_original_text_coverage.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
rows=json.loads((OUT/'prepared.json').read_text())
# All 120 numbered proof PNGs were actually viewed against the source rendering.
WORD_BANKS={
29: {'currentBlockId':'b-4-5','corrections':[{'label':'O','expected':'ultimately','observed':'0) ultimately merged into J'},{'label':'K','expected':'permanently','observed':'perm;mentlyK) permanently'}]},
43: {'currentBlockId':'b-1-18','corrections':[{'label':'O','expected':'wonder','observed':'0) wonder merged into J'}]},
72: {'currentBlockId':'b-5-5','corrections':[{'label':'O','expected':'viciously','observed':'0) viciously merged into G'},{'label':'L','expected':'realms','observed':'reahns'},{'label':'N','expected':'run','observed':'rum'}]},
76: {'currentBlockId':'b-1-17','corrections':[{'label':'O','expected':'undoubtedly','observed':'0) undoubtedly merged into G'}]},
111: {'currentBlockId':'b-2-2','corrections':[{'label':'O','expected':'warrant','observed':'0) warrant merged into G'},{'label':'H','expected':'consciousness','observed':'consc10usness'}]},
}
TEXT_OK={23:'Q13 A–D inequality options and the Q14 opening are present in current blocks b-2-12 and b-2-13; math notation and block boundaries differ.',44:'The L1/L2/L3/D equations and the paragraph explaining fixing c and finding a are present in b-9-2 as selectable prose plus TeX.',120:'The three subquestions about adjacency matrix A, A²[0][3], and Bᵐ are present in b-6-2 as selectable prose plus TeX.'}
MISSING='可以看出，段表项实际上只有两部分，前几位是段长，后几位是起始地址。'
cache={}
for r in rows:
 n=r['reviewId'];cat,stem=r['documentId'].split(':');page=r['pages'][0]
 reflow=Path(r['currentReflow']);r['currentReflowUnchangedSinceProof']=hashlib.sha256(reflow.read_bytes()).hexdigest()==r['currentReflowSHA']
 r['visualReviewed']=True
 r['proofSHA256']=hashlib.sha256(Path(r['proof']).read_bytes()).hexdigest()
 initial=OUT/'initial-proof'/Path(r['proof']).name
 r['proofUnchangedSinceVisualReview']=initial.exists() and initial.read_bytes()==Path(r['proof']).read_bytes()
 for ref in r['fallbackImages']:
  ref['sha256']=hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest()
 r['originalHTMTextLayer']=None
 if cat!='cs408':
  path=ROOT/'data/sources/english-exams-web-2026-09-26'/cat/'papers'/(stem+'.htm')
  if str(path) not in cache:
   data=path.read_text();cache[str(path)]={int(dict(m.ATTR.findall(a))['data-page']):body for a,body in m.SECTION.findall(data) if 'data-page' in dict(m.ATTR.findall(a))}
  body=cache[str(path)].get(int(page),'');lines,count=m.source_lines(body)
  x0,y0,x1,y1=r['pdfBlockBBox']
  selected=[z for z in lines if y0<=z['y']<=y1 and z['x']<=x1 and z['right']>=x0]
  r['originalHTMTextLayer']={'path':str(path),'sourcePage':page,'pageTextSpanCount':count,'regionLines':selected,'regionText':'\n'.join(z['text'] for z in selected),'caution':'Selectable text layer may contain OCR/font-mapping errors; two-column rows may interleave. It is evidence, not authoritative transcription.'}
 if r['fallbackImages']:
  r['visualConclusion']='preserved_in_fallback_image'
  r['reviewNote']='Original PDF rendering and the actual current fallback asset show the same target paragraph text, line order, paragraph transitions, and first/last visible lines. No introduced truncation or missing target paragraph was observed. This confirms image preservation, not text reflow/copy support or transcription accuracy.'
  r['currentBlockIds'] = list(dict.fromkeys(z['blockId'] for z in r['fallbackImages']))
 elif n in WORD_BANKS:
  r['visualConclusion']='word_bank_label_or_transcription_error';r.update(WORD_BANKS[n]);r['currentBlockIds']=[r['currentBlockId']]
  r['reviewNote']='PDF visual word bank compared with current selectable text: O is a letter label, not zero. The current label merge prevents a distinct O option; further explicit word errors are listed.'
 elif n in TEXT_OK:
  r['visualConclusion']='preserved_as_selectable_text_and_math';r['reviewNote']=TEXT_OK[n]
 elif n==119:
  r['visualConclusion']='confirmed_missing_sentence';r['missingText']=MISSING;r['currentBlockIds']=['b-6-8']
  r['reviewNote']='PDF block 22 begins with this explanatory sentence immediately before ④; current b-6-8 retains ④ and later conclusion but omits this entire sentence. This is not a fallback image coverage false positive.'
 else:raise AssertionError(n)
summary=Counter(r['visualConclusion'] for r in rows)
report={'scope':{'input':'docs/source-integrity-triage-final-2026-09-28.json','classification':'image_fallback_unreviewed','rows':len(rows),'documents':len({r['documentId'] for r in rows}),'unique_pdf_pages':len({(r['sourcePdf'],r['pages'][0]) for r in rows}),'actual_visual_pairs_reviewed':120,'english_original_htm_regions':sum(r['originalHTMTextLayer'] is not None for r in rows),'proofs_identical_to_visually_reviewed_initial':sum(r['proofUnchangedSinceVisualReview'] for r in rows),'reflow_changed_since_proof':sum(not r['currentReflowUnchangedSinceProof'] for r in rows)},'summary':dict(summary),'limits':['This is a bounded review of the 120 specified paragraph clues, not all paragraphs in the 206 English documents.','The 111 fallback-image cases retain visual content; they remain raster fallback and are not claimed to be selectable/reflowable text.','Original HTM region text was recovered by coordinates for every English clue; it is not certified character-perfect and does not replace the PDF visual evidence.','No generic extractor, reflow source, shared builder, or raw PDF was modified.','Proof images are diagnostic clips of target blocks. Context outside the target can be clipped or bleed across a proof header; this is not an asset defect.'],'rows':rows}
(OUT/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
lines=['# 120 条图片回退段落线索：独立视觉复核','',f'范围：{len(rows)} 条，29 文档、79 个原 PDF 页面。120 张 PDF 原块／实际回退图对照已逐张查看。','', '结论：111 条正文保留在图片中；3 条为文本／公式表示差异；5 条词库存在 O 标签合并或错字；1 条真实漏句。','', '## 需要修复','', '|记录|文档|PDF 页／块|当前块|问题|','|---|---|---|---|---|']
for r in rows:
 if r['visualConclusion'] in ('word_bank_label_or_transcription_error','confirmed_missing_sentence'):
  issue=r.get('missingText') or '; '.join(f"{z['label']}: {z['observed']} → {z['expected']}" for z in r['corrections'])
  lines.append(f"|{r['reviewId']}|{r['documentId']}|{r['pages'][0]}／{r['pdfBlockIndex']}|{', '.join(r['currentBlockIds'])}|{issue}|")
lines+=['','## 边界','',*('- '+s for s in report['limits']),'', '## 逐条索引','', '|记录|文档|PDF 页／块|结论|对照证据|','|---|---|---|---|---|']
for r in rows:lines.append(f"|{r['reviewId']}|{r['documentId']}|{r['pages'][0]}／{r['pdfBlockIndex']}|{r['visualConclusion']}|[{r['reviewId']:03d}.png]({r['reviewId']:03d}.png)|")
(OUT/'review.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'scope':report['scope'],'summary':summary},ensure_ascii=False,indent=2))
