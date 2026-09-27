"""Compile all source documents and raster-check generated formula SVGs."""
from pathlib import Path
import json,re,subprocess,concurrent.futures,hashlib
from lxml import etree
import fitz
ROOT=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=ROOT/'work/tex-check';out.mkdir(parents=True,exist_ok=True)
    def compile(p):
        r=subprocess.run(['xelatex','-interaction=nonstopmode','-halt-on-error',f'-output-directory={out}',p.name],cwd=ROOT/'tex',capture_output=True,text=True)
        log=r.stdout+r.stderr
        return {'file':p.name,'sha256':digest(p),'passed':r.returncode==0,'warnings':[x for x in log.splitlines() if 'Overfull' in x or 'Missing character' in x],'error_tail':log[-1400:] if r.returncode else ''}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(compile,sorted((ROOT/'tex').glob('*.tex'))))
    (ROOT/'assets/verification/latex-compilation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    assert len(results)==22 and all(r['passed'] and not r['warnings'] for r in results),[r for r in results if not r['passed'] or r['warnings']]
    formulas=json.loads((ROOT/'work/rendered.json').read_text())
    from formula_style import display_style
    assert all(x['tex'].startswith(r'\displaystyle ') for x in formulas)
    assert display_style(r'\frac1{\frac{a}{b}}').count(r'\dfrac')==2
    assert r'\dfrac{\displaystyle 1}{\displaystyle 2}' in display_style(r'\frac12')
    assert display_style(r'\frac{\sum_{i=1}^n x_i}{n}').count(r'\displaystyle')>=3
    # A contact sheet of actual generated SVGs, not source-page outlines.
    patterns=[r'\\begin\{pmatrix\}',r'\\begin\{cases\}',r'\\sum',r'\\int',r'\\lim',r'\\begin\{array\}',r'\\prime',r'\\(?:d|t)?frac',r'\\overline',r'\\partial']
    chosen=[]
    for pattern in patterns:
        item=next(x for x in formulas if re.search(pattern,x['tex']) and len(x['tex'])>30 and x['id']not in {c['id'] for c in chosen})
        chosen.append(item)
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="1800"><rect width="1100" height="1800" fill="white"/>']
    parts.append('<style>'+(ROOT/'mathjax.css').read_text()+'</style>')
    for i,item in enumerate(chosen):
        container=etree.fromstring(item['markup'].encode());svg=next(x for x in container if etree.QName(x).localname=='svg')
        _,_,w,h=map(float,svg.get('viewBox').split());scale=min(950/w,108/h,.04)
        svg.set('width',str(w*scale));svg.set('height',str(h*scale));svg.set('x','40');svg.set('y',str(i*180+44));svg.set('style','color:black')
        parts.append(f'<text x="40" y="{i*180+26}" font-family="sans-serif" font-size="16" fill="#667384">Formula {item["id"]}</text>')
        parts.append(etree.tostring(svg,encoding='unicode'))
    parts.append('</svg>');sheet=ROOT/'assets/verification/formula-samples.svg';sheet.write_text(''.join(parts))
    subprocess.run(['rsvg-convert','-o',str(sheet.with_suffix('.png')),str(sheet)],check=True)
    # All formulas must remain independent, valid SVG fragments.
    for item in formulas:
        root=etree.fromstring(item['markup'].encode());assert not root.xpath('.//*[@data-mml-node="merror"]')
        assert not root.xpath('.//*[local-name()="image" or local-name()="script"]')
    for year in [2019,2015,2009]:
        for kind in ['questions','answers']:
            doc=fitz.open(out/f'{year}-{kind}.pdf');doc[0].get_pixmap(dpi=120).save(ROOT/f'assets/verification/tex-{year}-{kind}.png')
    pages=[]
    for file in sorted((ROOT/'source').glob('20??.json')):
        paper=json.loads(file.read_text());pages.extend(p['source_page'] for p in paper['pages'])
        for kind in ['questions','answers']:
            text='\n'.join(b.get('text','') for p in paper['pages'] if p['kind']==kind for b in p['blocks'])
            numbers=set(map(int,re.findall(r'[（(](\d{1,2})[）)]',text)))
            assert set(range(1,24))<=numbers,(file,kind,numbers)
    assert sorted(pages)==list(range(1,56))
    report={'source_pages_covered_once':55,'years':11,'questions':253,'reference_answers':253,'tex_documents_compiled':22,'tex_compile_errors':0,'tex_overflow_or_missing_glyph_warnings':0,'unique_formula_svg_count':len(formulas),'svg_xml_valid':True,'mathjax_errors':0,'browser_interaction_tested':False,'source_hashes':{str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/'source').glob('20??.json'))}}
    (ROOT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
