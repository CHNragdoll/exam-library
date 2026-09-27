"""Build offline HTM with genuine TeX-to-SVG formulas and editable .tex files."""
# Shared reader shell: inject before this generator computes the HTML digest.
import sys as _reader_sys
from pathlib import Path as _ReaderPath
_reader_ui = next(p / 'exam-library' for p in _ReaderPath(__file__).resolve().parents if (p / 'exam-library/enhance_readers.py').is_file())
if str(_reader_ui) not in _reader_sys.path: _reader_sys.path.insert(0, str(_reader_ui))
from enhance_readers import write_reader
from pathlib import Path
import argparse, hashlib, html, json, re, shutil, subprocess, zipfile
import fitz
from formula_style import display_style
from lxml import etree, html as lh

ROOT=Path(__file__).resolve().parent
MATH=re.compile(r'\\\((.*?)\\\)|\\\[(.*?)\\\]',re.S)
OPTION_LABEL=re.compile(r'（([A-D])）|\(([A-D])\)|(?<![A-Za-z])([A-D])[.．]')
def split_options(text):
    """Separate choice labels outside TeX while retaining the source wording."""
    visible=MATH.sub(lambda match:' '*len(match.group()),text)
    labels=list(OPTION_LABEL.finditer(visible))
    sequence=''.join(next(group for group in match.groups() if group) for match in labels)
    if sequence not in {'ABCD','AB','CD','A','B','C','D'}:
        return None
    if len(labels)==1 and text[:labels[0].start()].strip():
        return None
    choices=[]
    for index,match in enumerate(labels):
        end=labels[index+1].start() if index+1<len(labels) else len(text)
        value=text[match.end():end]
        if not re.sub(r'[\s、，。；;:：]', '', MATH.sub('formula',value)):
            return None
        choices.append((text[match.start():match.end()],value))
    return text[:labels[0].start()],choices
def esc(s):return html.escape(s,quote=True)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def tex_escape(s):
    s=re.sub(r'([&%$#_{}])',r'\\\1',s).replace('Ⅰ','I').replace('Ⅱ','II').replace('Ⅲ','III')
    # Circled source labels are outside Latin Modern's repertoire.
    return re.sub('[①-⑳]',lambda m:r'\textcircled{'+str(ord(m[0])-ord('①')+1)+'}',s)
def body_tex(s):
    result=[];start=0
    for m in MATH.finditer(s):
        content=re.sub(r'(?<!\\),',r',\\allowbreak ',display_style(m.group(1) if m.group(1)is not None else m.group(2)))
        rendered=r'\('+content+r'\)' if m.group(1)is not None else r'\[\fitmath{'+content+r'}\]'
        result.extend([tex_escape(s[start:m.start()]),rendered]);start=m.end()
    return ''.join(result)+tex_escape(s[start:])

def styled_prose(text):
    return MATH.sub(lambda m:(r'\('+display_style(m[1])+r'\)') if m[1]is not None else (r'\['+display_style(m[2])+r'\]'),text)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--partial',action='store_true');args=parser.parse_args()
    papers=[json.loads(p.read_text()) for p in sorted((ROOT/'source').glob('[12][09]??.json'),reverse=True)]
    years=[p['year'] for p in papers]
    source_hashes={str(p['year']):digest(ROOT/f"source/{p['year']}.json") for p in papers}
    for paper in papers:
        for page in paper['pages']:
            for block in page['blocks']:
                for key in ['text','tex','caption']:
                    value=block.get(key,'')
                    bad=[ord(c) for c in value if ord(c)<32 and c!='\n']
                    assert not bad,(paper['year'],page['source_page'],key,bad,repr(value))
                    if key!='tex':
                        assert '\\' not in MATH.sub('',value),(paper['year'],page['source_page'],'unmatched math delimiters or TeX outside math',value)

    if not args.partial:assert years==list(range(2008,1986,-1)),years
    page_map=json.loads((ROOT/'work/page-map.json').read_text())
    for p in papers:
        mapping=page_map[str(p['year'])]
        expected=mapping['questions']+mapping['answers']
        assert [page['source_page'] for page in p['pages']]==expected,p['year']
        assert [page['kind'] for page in p['pages']]==['questions']*len(mapping['questions'])+['answers']*len(mapping['answers'])
        assert all(page['blocks'] for page in p['pages']),p['year']
    formula_map={};formulas=[]
    def formula_id(tex,display):
        key=(tex,display)
        if key not in formula_map:
            idx=len(formulas);formula_map[key]=idx;formulas.append({'id':idx,'tex':display_style(tex),'original_tex':tex,'display':display})
        return formula_map[key]
    for paper in papers:
        for page in paper['pages']:
            for block in page['blocks']:
                if block['type']=='display':formula_id(block['tex'],True)
                else:
                    for m in MATH.finditer(block.get('text','')+block.get('caption','')):formula_id(m.group(1) if m.group(1) is not None else m.group(2),m.group(2)is not None)
    (ROOT/'work/formulas.json').write_text(json.dumps(formulas,ensure_ascii=False))
    result=subprocess.run(['node','render.cjs'],cwd=ROOT,capture_output=True,text=True)
    print(result.stdout);assert result.returncode==0,result.stdout+result.stderr
    rendered=json.loads((ROOT/'work/rendered.json').read_text())
    for item in rendered:
        assert 'error' not in item
        tree=lh.fromstring(item['markup']);svgs=tree.xpath('./*[local-name()="svg"]');assert len(svgs)==1
        assert not tree.xpath('.//*[@data-mml-node="merror"]')
        assert not tree.xpath('.//script|.//image')
    def formula(tex,display):
        item=rendered[formula_map[(tex,display)]]
        return f'<span class="formula" data-tex="{esc(item["tex"])}" title="点击复制 LaTeX">{item["markup"]}</span>'
    def prose(text):
        parts=[];start=0
        for m in MATH.finditer(text):
            parts.append(esc(text[start:m.start()]))
            parts.append(formula(m.group(1) if m.group(1)is not None else m.group(2),m.group(2)is not None));start=m.end()
        parts.append(esc(text[start:]));return ''.join(parts)
    meta=json.loads((ROOT/'source-metadata.json').read_text());pdf=fitz.open(meta['path'])
    assert digest(Path(meta['path']))==meta['sha256']
    for name in ['papers','tex','assets/figures','assets/verification']:(ROOT/name).mkdir(parents=True,exist_ok=True)
    entries=[];figure_count=0
    for paper in papers:
        year=paper['year']
        for kind,label in [('questions','真题'),('answers','参考答案')]:
            sections=[];texparts=[];page_numbers=[]
            for page in [p for p in paper['pages'] if p['kind']==kind]:
                number=page['source_page'];page_numbers.append(number);blocks=[]
                for bi,b in enumerate(page['blocks']):
                    typ=b['type'];text=b.get('text','')
                    if typ=='heading':blocks.append('<h2>'+prose(text)+'</h2>');texparts.append(r'\subsection*{'+body_tex(text)+'}')
                    elif typ=='paragraph':
                        split=split_options(text) if kind=='questions' else None
                        if split:
                            prefix,choices=split
                            if prefix.strip():
                                cls='paragraph question' if re.match(r'^\s*[（(]?\d{1,2}[）).．、]',prefix) else 'paragraph'
                                blocks.append(f'<div class="{cls}">'+prose(prefix)+'</div>')
                            blocks.append('<div class="math-options" role="list">'+''.join('<div class="math-option" role="listitem"><span class="math-option-label">'+esc(label)+'</span><span class="math-option-content">'+prose(value)+'</span></div>' for label,value in choices)+'</div>')
                        else:
                            cls='paragraph question' if re.match(r'^\s*[（(]?\d{1,2}[）).．、]',text) else 'paragraph'
                            blocks.append(f'<div class="{cls}">'+prose(text)+'</div>')
                        blocks.append('<pre class="tex-source">'+esc(styled_prose(text))+'</pre>');texparts.append(body_tex(text)+'\n')
                    elif typ=='display':
                        blocks.append('<div class="display">'+formula(b['tex'],True)+'</div><pre class="tex-source">'+esc(display_style(b['tex']))+'</pre>');texparts.append('\\[\\fitmath{'+display_style(b['tex'])+'}\\]\n')
                    elif typ=='figure':
                        figure_count+=1;stem=f'page-{number:03}-{bi:02}';crop=fitz.open();crop.insert_pdf(pdf,from_page=number-1,to_page=number-1)
                        rect=fitz.Rect(b['bbox']);assert rect.is_valid and pdf[number-1].rect.contains(rect)
                        crop[0].set_cropbox(rect)
                        (ROOT/f'assets/figures/{stem}.svg').write_text(crop[0].get_svg_image(text_as_path=True))
                        crop[0].get_pixmap(dpi=200).save(ROOT/f'assets/figures/{stem}.png')
                        crop.save(ROOT/f'assets/figures/{stem}.pdf');crop.close()
                        blocks.append(f'<figure><img src="../assets/figures/{stem}.svg" alt="{esc(b.get("caption","原卷图形"))}"><figcaption>{prose(b.get("caption",""))}</figcaption></figure>')
                        texparts.append(r'\begin{center}\includegraphics[width=.48\linewidth]{../assets/figures/'+stem+r'.pdf}\end{center}')
                    else:raise ValueError(typ)
                sections.append(f'<section class="page" data-source-page="{number}">'+''.join(blocks)+'</section>')
            title=f'{year} 年考研数学三 · {label}'
            texdoc='\\documentclass[UTF8,12pt]{ctexart}\n\\usepackage[a4paper,margin=24mm]{geometry}\n\\usepackage{amsmath,amssymb,bm,graphicx,adjustbox}\n\\newcommand{\\fitmath}[1]{\\begin{adjustbox}{max width=\\linewidth}$\\displaystyle #1$\\end{adjustbox}}\n\\setlength{\\parindent}{0pt}\n\\setlength{\\parskip}{.7em}\n\\sloppy\n\\allowdisplaybreaks\n\\begin{document}\n\\section*{'+title+'}\n'+'\n\n'.join(texparts)+'\n\\end{document}\n'
            (ROOT/f'tex/{year}-{kind}.tex').write_text(texdoc)
            other='answers' if kind=='questions' else 'questions';other_label='查看参考答案' if kind=='questions' else '返回真题'
            notice=''
            if paper.get('notes'):
                notes=paper['notes'] if isinstance(paper['notes'],list) else [str(paper['notes'])]
                notice='<aside class="notice"><strong>原卷说明</strong>'+''.join('<p>'+esc(note)+'</p>' for note in notes)+'</aside>'
            content=f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><link rel="stylesheet" href="../mathjax.css"><link rel="stylesheet" href="../style.css"></head><body><header><a href="../../exam-library/math3/index.htm">← 考研数学三目录</a> · <a href="../index.htm">本册年份</a><h1>{title}</h1><p class="intro">正文重排 · LaTeX 公式矢量显示 · 点击公式复制源码</p><nav><a class="pill" href="{year}-{other}.htm">{other_label}</a><a class="pill" href="../tex/{year}-{kind}.tex" download>下载 LaTeX 源码</a><button data-toggle-source aria-pressed="false">显示 LaTeX</button></nav>{notice}</header><main>'+''.join(sections)+'</main><footer>公式由 LaTeX 编译为 SVG；曲线插图保留原图。参考答案按原稿转录，不补写原稿省略的解答。</footer><div class="status" role="status"></div><script src="../interaction.js"></script></body></html>'
            target=ROOT/f'papers/{year}-{kind}.htm';write_reader(target, content)
            entries.append({'year':year,'kind':kind,'source_pages':page_numbers,'htm':str(target.relative_to(ROOT)),'tex':f'tex/{year}-{kind}.tex','sha256':digest(target)})
    cards=''.join(f'<section class="year-card"><h2>{year}</h2><p>数学三 · 真题及参考答案</p><nav><a class="pill" href="papers/{year}-questions.htm">阅读真题</a><a class="pill" href="papers/{year}-answers.htm">参考答案</a></nav><p><a href="tex/{year}-questions.tex" download>真题 LaTeX</a> · <a href="tex/{year}-answers.tex" download>答案 LaTeX</a></p></section>' for year in years)
    (ROOT/'index.htm').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>考研数学三 · LaTeX 真题库</title><link rel="stylesheet" href="style.css"></head><body><header><h1>考研数学三 · LaTeX 真题库</h1><p class="intro">1987–2008 · 按题阅读 · 公式矢量显示 · 可编辑源码 · 离线使用</p></header><main class="year-grid">'+cards+'</main><footer>数学公式由可编辑 LaTeX 生成，正文随窗口宽度排版。曲线图等独立插图保留原卷图形。</footer></body></html>')
    for file in [ROOT/'index.htm',*(ROOT/'papers').glob('*.htm')]:
        tree=lh.fromstring(file.read_text(),parser=lh.HTMLParser(huge_tree=True))
        for url in tree.xpath('//a/@href|//img/@src|//link/@href|//script/@src'):
            assert not url.startswith(('http:', 'https:', '//'))
            assert (file.parent/url).is_file(),(file,url)
        assert not tree.xpath('.//*[@data-mml-node="merror"]')
        assert '\\(' not in ''.join(tree.xpath('//div[@class="paragraph"]/text()'))
    compile_path=ROOT/'assets/verification/latex-compilation.json'
    compiles=json.loads(compile_path.read_text()) if compile_path.exists() else []
    compiled=len(compiles)==44 and all(r['passed'] and not r['warnings'] and r.get('sha256')==digest(ROOT/'tex'/r['file']) for r in compiles)
    manifest={'source':meta,'source_hashes':source_hashes,'years':years,'documents':entries,'unique_formulas':len(formulas),'formula_errors':0,'source_pages':sum(len(p['pages']) for p in papers),'figures':figure_count,'rendering':'MathJax 3.2.2 TeX -> self-contained SVG; no runtime CDN','browser_interaction_tested':False,'full_tex_document_compilation_tested':compiled,'notes':{str(p['year']):p.get('notes',[]) for p in papers}}
    (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    (ROOT/'README.md').write_text('# 考研数学三 LaTeX / HTM\n\n下载包包含本轮新增的 1987–2008 共 22 年，解压后打开 `index.htm` 阅读；完整 33 年请使用项目总目录。正文为 HTML，公式从 LaTeX 生成独立 SVG；无需联网或安装 MathJax。\n\n`tex/` 为 44 份可编辑 LaTeX 文档（建议 XeLaTeX + ctex）。`source/` 为逐页结构化转录，包括公式源。`assets/figures/` 为原卷函数曲线图等独立插图，HTML 使用矢量 SVG，TeX 使用同源矢量 PDF；PNG 仅用于图形核对。公式均为 TeX。\n\n网页可显示全部 LaTeX 片段，点击公式可复制；复制按钮的浏览器交互尚未实机验证，始终可以下载 `.tex` 源文件。没有运行完整 TeX 文档编译；全部公式经过 MathJax 编译检查。\n\n原卷 126 页、1987–2008 年；保留早期 IV/V 卷及原稿参考答案。答案只转录原稿，不补写“证明略”等缺失内容。请保留全部目录。\n\n## 重建\n\n使用已安装 PyMuPDF、lxml 的 Python；执行 `npm ci --prefix work/render` 安装锁定的公式构建依赖，依次执行 `python build.py`、`python verify.py`、`python build.py`；最后一步将成功验证记录写入 manifest、说明文件和离线包。MathJax 文档：https://docs.mathjax.org/en/v3.2/server/direct.html\n\n原 PDF 与上一版整页 SVG 均未修改。本目录最初以本地试用交付；当前仓库交付状态以根目录 README 为准。转录备注见 manifest.json。\n')
    if compiled:
        readme=ROOT/'README.md';readme.write_text(readme.read_text().replace('没有运行完整 TeX 文档编译；全部公式经过 MathJax 编译检查。','44 份完整 TeX 文档已通过 XeLaTeX 编译，无溢出或缺字警告；全部公式经过 MathJax 编译检查。'))
    license_src=ROOT/'work/render/node_modules/mathjax-full/LICENSE'
    if license_src.exists():shutil.copy2(license_src,ROOT/'MATHJAX-LICENSE')
    if not args.partial:
        archive=ROOT.parent/'考研数学三_1987-2008_LaTeX及HTM.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for f in sorted(ROOT.rglob('*')):
                if not f.is_file() or 'work' in f.relative_to(ROOT).parts or '__pycache__' in f.relative_to(ROOT).parts:continue
                name=str(Path(ROOT.name)/f.relative_to(ROOT))
                if f.suffix=='.htm':
                    # The standalone download returns to its own catalog.
                    z.writestr(name,f.read_text().replace('href="../../exam-library/math3/index.htm"','href="../index.htm"'))
                else:z.write(f,name)
            for name in ['package.json','package-lock.json']:z.write(ROOT/'work/render'/name,str(Path(ROOT.name)/'work/render'/name))
            z.write(ROOT/'work/page-map.json',str(Path(ROOT.name)/'work/page-map.json'))
            for name in ['tokens.css','reader.css','reader.js']:
                z.write(_reader_ui/'ui'/name,str(Path('exam-library/ui')/name))
        with zipfile.ZipFile(archive) as z:
            assert z.testzip()is None
            import posixpath
            from urllib.parse import unquote
            names=set(z.namelist())
            for name in names:
                if not name.endswith('.htm'):continue
                tree=lh.fromstring(z.read(name),parser=lh.HTMLParser(huge_tree=True))
                for url in tree.xpath('//@href|//img/@src|//link/@href|//script/@src'):
                    if url.startswith('#'):continue
                    assert posixpath.normpath(posixpath.join(posixpath.dirname(name),unquote(url))) in names,(name,url)
        print('ZIP',archive,archive.stat().st_size)
    print('DONE',len(papers),'years',len(formulas),'unique formulas',figure_count,'figures')
if __name__=='__main__':main()
