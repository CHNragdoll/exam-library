"""Build editable politics TeX and responsive offline HTM from checked transcription."""
# Shared reader shell: inject before this generator computes the HTML digest.
import sys as _reader_sys
from pathlib import Path as _ReaderPath
_reader_ui = next(p / 'exam-library' for p in _ReaderPath(__file__).resolve().parents if (p / 'exam-library/enhance_readers.py').is_file())
if str(_reader_ui) not in _reader_sys.path: _reader_sys.path.insert(0, str(_reader_ui))
from enhance_readers import write_reader
from pathlib import Path
import argparse,hashlib,html,json,re,shutil,subprocess
import fitz
from lxml import html as lh
from formula_style import display_style
ROOT=Path(__file__).resolve().parent
MATH=re.compile(r'\\\((.*?)\\\)|\\\[(.*?)\\\]',re.S)
CONTINUATION_DISPLAY_RE=re.compile(r'^\s*第\s*\d+\s*题\s*[（(]续[）)]\s*[:：]?\s*')
def visible_question_text(text):
 return CONTINUATION_DISPLAY_RE.sub('',text,count=1).strip()
def continuation_marker(text):
 match=CONTINUATION_DISPLAY_RE.match(text)
 return match.group(0).strip() if match else ''
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def esc(s):return html.escape(str(s),quote=True)
def tex_escape(s):
 s=str(s).replace(chr(92),'BACKSLASHPLACEHOLDER');s=re.sub(r'([&%$#_{}])',r'\\\1',s).replace('~',r'\textasciitilde{}').replace('^',r'\textasciicircum{}')
 s=s.replace('BACKSLASHPLACEHOLDER',r'\textbackslash{}')
 return re.sub('[①-⑳]',lambda m:r'\textcircled{'+str(ord(m[0])-ord('①')+1)+'}',s)
def body_tex(s):
 parts=[];start=0
 for m in MATH.finditer(str(s)):
  t=display_style(m[1] if m[1] is not None else m[2]);t=re.sub(r'(?<!\\),',r',\\allowbreak ',t)
  parts.extend([tex_escape(s[start:m.start()]),r'\('+t+r'\)' if m[1] is not None else r'\[\fitmath{'+t+r'}\]']);start=m.end()
 return ''.join(parts)+tex_escape(s[start:])
def contents(b):
 if b['type']=='code':return []
 if b['type']=='table':return [str(c) for row in ([b['columns']] if b.get('columns') else [])+b['rows'] for c in row]
 return [b.get('text',''),b.get('caption','')]
def cell_tex(s,break_arrows=False):
 # Allow long dotted addresses/prefixes to wrap inside narrow table columns.
 parts=[];start=0;s=str(s)
 def plain(t):
  value=re.sub(r'(?<=\d)([./])(?=\d)',r'\1\\allowbreak{}',tex_escape(t))
  if break_arrows:value=re.sub('([←→])',lambda m:r'\allowbreak{}'+m[1]+r'\allowbreak{}',value)
  return value
 for m in MATH.finditer(s):
  parts.extend([plain(s[start:m.start()]),body_tex(m[0])]);start=m.end()
 return ''.join(parts)+plain(s[start:])
def split_choices(text, printed_duplicate_c=False):
 # The printed 2020 question 1 uses a bare "A 《...》" label; keep its
 # transcription while rendering it as the first option alongside B-D.
 punctuation='[.．、]' if printed_duplicate_c else '[.．]'
 matches=list(re.finditer(r'(?:(?<!\S)|(?<=[。；：]))([ABCDE])(?:'+punctuation+r'|(?=\s+《))\s*',text))
 labels=[m[1] for m in matches]
 # An A option may end the source page while B-D continue on the next.
 single_a=labels==['A'] and re.match(r'^\s*\d{1,2}[.．、]',text)
 printed_labels=labels==['A','B','C','C'] if printed_duplicate_c else False
 if (len(labels)<2 and not single_a) or (len(set(labels))!=len(labels) and not printed_labels) or (''.join(labels) not in 'ABCDE' and not printed_labels):return None
 options=[(m[1],text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)].strip()) for i,m in enumerate(matches)]
 if not all(value for _,value in options):return None
 visible=[re.sub(r'\\[A-Za-z]+|[{}]','',value) for _,value in options]
 longest=max(map(len,visible))
 width=max(sum(.55 if ord(c)<128 else 1 for c in value) for value in visible)
 columns=4 if len(options)==4 and width<=9 else 2 if longest<=100 else 1
 return text[:matches[0].start()].strip(),options,columns
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--partial',action='store_true');ap.add_argument('--years',nargs='+',type=int);args=ap.parse_args()
 specs=json.loads((ROOT/'sources.json').read_text());byid={s['id']:s for s in specs};years=sorted({s['year'] for s in specs},reverse=True)
 papers=[];hashes={}
 for y in years:
  if args.years and y not in args.years:continue
  f=ROOT/f'source/{y}.json'
  if not f.exists():
   assert args.partial,f;continue
  data=f.read_bytes();papers.append(json.loads(data));hashes[str(y)]=hashlib.sha256(data).hexdigest()
 if not args.partial:assert len(papers)==len(years)
 formulas=[];ids={}
 def fid(t,d):
  key=(t,d)
  if key not in ids:
   ids[key]=len(formulas);formulas.append({'id':len(formulas),'tex':display_style(t),'original_tex':t,'display':d})
  return ids[key]
 for paper in papers:
  expected=[(s['id'],p) for s in specs if s['year']==paper['year'] for p in range(1,s['pages']+1)]
  assert [(p['source_id'],p['source_page']) for p in paper['pages']]==expected,paper['year']
  for page in paper['pages']:
   assert page['blocks'] or page.get('blank') or page.get('continuation_only'),(paper['year'],page)
   for b in page['blocks']:
    assert b['type'] in ['heading','paragraph','display','code','table','figure'],b
    if b['type']=='display':fid(b['tex'],True)
    if b['type']=='table':assert b['rows'] and len({len(row) for row in b['rows']})==1,b
    for s in contents(b):
     assert not any(ord(c)<32 and c!='\n' for c in s),(paper['year'],page['source_page'],repr(s))
     # Backslashes present in original prose are escaped as literal text.
     for m in MATH.finditer(s):fid(m[1] if m[1] is not None else m[2],m[2] is not None)
 (ROOT/'work/formulas.json').write_text(json.dumps(formulas,ensure_ascii=False))
 r=subprocess.run(['node','render.cjs'],cwd=ROOT,capture_output=True,text=True);print(r.stdout);assert r.returncode==0,r.stdout+r.stderr
 rendered=json.loads((ROOT/'work/rendered.json').read_text())
 def formula(t,d):
  f=rendered[fid(t,d)];assert not f.get('error');return f'<span class="formula" data-tex="{esc(f["tex"])}" title="点击复制 LaTeX">{f["markup"]}<code class="formula-source">{esc(f["tex"])}</code></span>'
 def prose(s):
  s=str(s);out=[];start=0
  for m in MATH.finditer(s):out.extend([esc(s[start:m.start()]),formula(m[1] if m[1] is not None else m[2],m[2] is not None)]);start=m.end()
  return ''.join(out)+esc(s[start:])
 pdfs={};entries=[];figures=0
 for spec in specs:
  p=Path(spec['path']);assert sha(p)==spec['sha256'];pdfs[spec['id']]=fitz.open(p)
 for paper in papers:
  for spec in [s for s in specs if s['year']==paper['year']]:
   sid=spec['id'];sections=[];texparts=[];anchors=[]
   for page in [p for p in paper['pages'] if p['source_id']==sid]:
    pn=page['source_page'];out=[]
    for bi,b in enumerate(page['blocks']):
     kind=b['type'];text=b.get('text','')
     if kind=='heading':
      anchor=f'p{pn}-b{bi}';anchors.append((anchor,text));out.append(f'<h2 id="{anchor}">{prose(text)}</h2>');texparts.append(r'\subsection*{'+body_tex(text)+'}')
     elif kind=='paragraph':
      cls='paragraph question' if re.match(r'^\s*\d{1,2}[．.、]',text) else 'paragraph'
      paragraphs=b.get('paragraphs')
      if paragraphs:
       assert len(paragraphs)>1 and all(isinstance(part,str) and part.strip() for part in paragraphs),(sid,pn,bi)
       assert re.sub(r'\s+','',text)==re.sub(r'\s+','',''.join(paragraphs)),(sid,pn,bi,'paragraph text mismatch')
       wrapper='paragraph-group question' if 'question' in cls else 'paragraph-group'
       visible_parts=[(continuation_marker(raw),visible_question_text(raw)) for raw in paragraphs]
       out.append(f'<div class="{wrapper}">'+''.join(
        '<p class="paragraph'+(' material-label' if re.fullmatch(r'材料\s*\d+',part) else '')+'"'+(' hidden' if marker and not part else '')+'>'+
        (f'<span class="source-continuation-label" hidden>{prose(marker)}</span>' if marker else '')+prose(part)+'</p>'
        for marker,part in visible_parts)+'</div>')
       texparts.append('\n\n'.join(body_tex(part) for _,part in visible_parts if part))
       continue
      display_text=visible_question_text(text)
      marker=continuation_marker(text)
      hidden_label=f'<span class="source-continuation-label" hidden>{prose(marker)}</span>' if marker else ''
      if not display_text:
       out.append(f'<p class="{cls}" hidden>{hidden_label}</p>')
       continue
      # The 2005 original prints C twice for Q3. Preserve all four printed
      # alternatives and let the structured record remain partial.
      printed_duplicate_c=(sid=='2005-questions' and pn==1 and bi==8 and
                           display_text.startswith('A、认识总是滞后于实战'))
      choices=split_choices(display_text,printed_duplicate_c) if spec['kind']=='questions' else None
      if choices:
       prefix,options,cols=choices
       if hidden_label:out.append(f'<p class="{cls}" hidden>{hidden_label}</p>')
       if prefix:out.append(f'<p class="{cls}">{prose(prefix)}</p>');texparts.append(body_tex(prefix)+'\n')
       separator='、' if printed_duplicate_c else '.'
       out.append(f'<div class="choices choices-{cols}">'+''.join('<div class="choice"><b>'+label+separator+'</b><span>'+prose(value)+'</span></div>' for label,value in options)+'</div>')
       col=r'>{\raggedright\arraybackslash}p{\dimexpr(\linewidth-'+str(2*cols)+r'\tabcolsep)/'+str(cols)+r'\relax}'
       cells=[r'\textbf{'+label+separator+'} '+cell_tex(value) for label,value in options]
       rows=[' & '.join(cells[i:i+cols]+['']*(cols-len(cells[i:i+cols])))+r'\\[.35em]' for i in range(0,len(cells),cols)]
       texparts.append(r'\begin{center}\begin{tabular}{'+col*cols+'}\n'+'\n'.join(rows)+r'\end{tabular}\end{center}')
      else:out.append(f'<p class="{cls}">{hidden_label}{prose(display_text)}</p>');texparts.append(body_tex(display_text)+'\n')
     elif kind=='display':out.append('<div class="display">'+formula(b['tex'],True)+'</div>');texparts.append(r'\[\fitmath{'+display_style(b['tex'])+r'}\]')
     elif kind=='code':
      assert r'\end{Verbatim}' not in text
      out.append('<pre class="code"><code>'+esc(text)+'</code></pre>');texparts.append('\\begin{Verbatim}[breaklines,breakanywhere,fontsize=\\small]\n'+text+'\n\\end{Verbatim}')
     elif kind=='table':
      cols=b.get('columns',[]);rows=b['rows'];n=len(rows[0]);assert not cols or len(cols)==n
      out.append('<div class="table-scroll"><table>'+('<thead><tr>'+''.join('<th>'+prose(c)+'</th>' for c in cols)+'</tr></thead>' if cols else '')+'<tbody>'+''.join('<tr>'+''.join('<td>'+prose(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>')
      texrows=([cols] if cols else [])+rows
      col='c' if n>8 else r'>{\raggedright\arraybackslash}p{\dimexpr(\linewidth-'+str(2*n)+r'\tabcolsep-'+str(n+1)+r'\arrayrulewidth)/'+str(n)+r'\relax}'
      texparts.append(r'\begin{center}\begin{adjustbox}{max width=\linewidth}\begin{tabular}{|'+('|'.join(col for _ in range(n)))+r'|}\hline'+'\n'+'\n'.join(' & '.join(cell_tex(c,break_arrows=True) for c in row)+r'\\\hline' for row in texrows)+r'\end{tabular}\end{adjustbox}\end{center}')
     elif kind=='figure':
      figures+=1;pdf=pdfs[sid];rect=fitz.Rect(b['bbox']);assert rect.is_valid and pdf[pn-1].rect.contains(rect),(sid,pn,b)
      assert rect.get_area()<pdf[pn-1].rect.get_area()*.8,(sid,pn,'figure nearly fills page')
      crop=fitz.open();crop.insert_pdf(pdf,from_page=pn-1,to_page=pn-1);crop[0].set_cropbox(rect)
      stem=f'{sid}-p{pn:03}-b{bi:03}';folder=ROOT/'assets/figures';folder.mkdir(exist_ok=True)
      (folder/f'{stem}.svg').write_text(crop[0].get_svg_image(text_as_path=True));crop[0].get_pixmap(dpi=160).save(folder/f'{stem}.png');crop.save(folder/f'{stem}.pdf');crop.close()
      out.append(f'<figure><img src="../assets/figures/{stem}.svg" alt="{esc(b.get("caption","原卷图形"))}"><figcaption>'+prose(b.get('caption',''))+'</figcaption></figure>')
      texparts.append(r'\begin{center}\includegraphics[width=.65\linewidth,height=.4\textheight,keepaspectratio]{../assets/figures/'+stem+r'.pdf}\end{center}')
    sections.append(f'<section class="source-page" data-source-page="{pn}">'+''.join(out)+'</section>')
   title=spec['title'];notes=paper.get('notes',[]);notes=notes if isinstance(notes,list) else [str(notes)]
   notice='<aside class="notice"><strong>原卷说明</strong>'+''.join('<p>'+esc(n)+'</p>' for n in notes)+'</aside>' if notes else ''
   toc='<details class="toc"><summary>题目与答案目录</summary><nav>'+''.join(f'<a href="#{a}">{prose(t)}</a>' for a,t in anchors)+'</nav></details>' if anchors else ''
   footer='按用户提供的试题卷转录，保留原卷自带的答案。' if paper.get('contains_answers') else '按用户提供的试题卷转录；本文件不含参考答案。' if spec['kind']=='questions' else '按用户提供的原稿转录，保留题目、答案及原有解析；未补写原稿缺失内容。'
   content='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><link rel="stylesheet" href="../mathjax.css"><link rel="stylesheet" href="../style.css"></head><body><header><a href="../../exam-library/politics/index.htm">← 政治双版本目录</a><h1>'+esc(title)+'</h1><p class="intro">正文自适应重排 · 可编辑 LaTeX 源码 · 图表保留</p><nav><a class="pill" href="../../politics-original/papers/'+sid+'.htm">SVG 原版</a><a class="pill" download href="../tex/'+sid+'.tex">下载 LaTeX 源码</a><button data-toggle-source aria-pressed="false">显示公式源码</button></nav>'+notice+toc+'</header><main class="paper">'+''.join(sections)+'</main><footer>'+footer+'</footer><div class="status" role="status"></div><script src="../interaction.js"></script></body></html>'
   target=ROOT/'papers'/f'{sid}.htm';write_reader(target, content)
   texdoc=r'''\documentclass[UTF8,11pt]{ctexart}
\usepackage[a4paper,margin=22mm]{geometry}
\usepackage{amsmath,amssymb,bm,graphicx,adjustbox,fvextra,longtable,array}
\xeCJKDeclareCharClass{CJK}{"2160 -> "217F, "2460 -> "249B, "2200 -> "22FF}
\newcommand{\fitmath}[1]{\begin{adjustbox}{max width=\linewidth}$\displaystyle #1$\end{adjustbox}}
\setlength{\parindent}{0pt}\setlength{\parskip}{.65em}\renewcommand{\arraystretch}{1.3}
\sloppy\allowdisplaybreaks
\begin{document}
\section*{'''+tex_escape(title)+'}\n'+'\n\n'.join(texparts)+'\n\\end{document}\n'
   texpath=ROOT/'tex'/f'{sid}.tex';texpath.write_text(texdoc)
   entries.append({'id':sid,'year':spec['year'],'title':title,'pages':spec['pages'],'htm':str(target.relative_to(ROOT)),'tex':str(texpath.relative_to(ROOT)),'htm_sha256':sha(target),'tex_sha256':sha(texpath)})
 compilefile=ROOT/'assets/verification/latex-compilation.json';compiles=json.loads(compilefile.read_text()) if compilefile.exists() else []
 def compilation_current(c):
  target=ROOT/'tex'/c['file']
  if not target.is_file() or not (ROOT/'work/tex-check'/f'{target.stem}.pdf').is_file() or not c['passed'] or c['warnings'] or c['sha256']!=sha(target):return False
  deps={name:sha((target.parent/name).resolve()) for name in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}',target.read_text())}
  return c.get('dependencies',{})==deps
 compiled=len(compiles)==len(specs) and {c['file'] for c in compiles}=={Path(e['tex']).name for e in entries} and all(compilation_current(c) for c in compiles)
 manifest={'documents':entries,'source_pages':sum(e['pages'] for e in entries),'source_hashes':hashes,'formulas':len(formulas),'figures':figures,'tex_compilation_verified':compiled,'browser_tested':False,'notes':{str(p['year']):p.get('notes',[]) for p in papers}}
 (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 cards=''.join('<article><h2>'+esc(e['title'])+'</h2><p><a href="'+e['htm']+'">阅读重排版</a> · <a download href="'+e['tex']+'">LaTeX 源码</a></p></article>' for e in entries)
 year_label=f'{min(e["year"] for e in entries)}–{max(e["year"] for e in entries)} · 真题'
 (ROOT/'index.htm').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>政治 LaTeX 重排版</title><link rel="stylesheet" href="style.css"></head><body><header><a href="../exam-library/politics/index.htm">← 政治双版本目录</a><h1>考研政治 · 重排版</h1><p>'+year_label+'</p></header><main class="paper">'+cards+'</main></body></html>')
 print('DONE',len(entries),'documents',manifest['source_pages'],'pages',len(formulas),'formulas',figures,'figures')
if __name__=='__main__':main()
