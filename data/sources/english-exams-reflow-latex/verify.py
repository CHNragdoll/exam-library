"""Check offline output and compile all standalone LaTeX sources."""
from pathlib import Path
import json, hashlib, subprocess, concurrent.futures, re
from lxml import html
from collections import Counter
ROOT=Path(__file__).resolve().parent

def compile_one(entry):
    src=ROOT/entry['file'];tex=src.with_suffix('.tex');out=ROOT/'work/tex-check'/entry['category']/tex.stem;out.mkdir(parents=True,exist_ok=True)
    pdf=out/(tex.stem+'.pdf');logfile=out/(tex.stem+'.log')
    dependencies=[tex]+[tex.parent/s for s in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}',tex.read_text())]
    fresh=pdf.exists() and logfile.exists() and pdf.stat().st_mtime>=max(p.stat().st_mtime for p in dependencies) and 'Output written on' in logfile.read_text(errors='replace')
    if fresh:
        result=subprocess.CompletedProcess([],0,'');log=logfile.read_text(errors='replace')
    else:
        result=subprocess.run(['/Library/TeX/texbin/xelatex','-interaction=nonstopmode','-halt-on-error',f'-output-directory={out}',tex.name],cwd=tex.parent,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=150)
        (out/'console.txt').write_text(result.stdout)
        log=logfile.read_text(errors='replace') if logfile.exists() else result.stdout
    return {'file':entry['file'],'compiled':result.returncode==0,'missing_glyphs':re.findall(r'Missing character:.*',log),'overfull_boxes':len(re.findall('Overfull',log)),'pdf':str((out/(tex.stem+'.pdf')).relative_to(ROOT))}

def main():
    m=json.loads((ROOT/'manifest.json').read_text());assert m['documents']==206 and m['pages']==2020
    links=0;body_pages=0;inline=0
    for entry in m['papers']:
        p=ROOT/entry['file'];tree=html.fromstring(p.read_text());data=json.loads(p.with_suffix('.json').read_text())
        assert hashlib.sha256(p.read_bytes()).hexdigest()==entry['htm_sha256']
        assert len(tree.xpath('//section[@data-source-page]'))==entry['pages']
        assert not tree.xpath('//svg')
        assert not tree.xpath('//*[@class="page-label"]')
        assert '原卷第' not in p.with_suffix('.tex').read_text()
        expected=Counter()
        for page in data['pages']:
            for block in page['blocks']:
                if block['type']=='source_line':continue
                for run in block.get('runs',[]):
                    if not run.get('glyph'):expected.update(c for c in run['text'] if c.isalnum())
                for item in block.get('items',[]):
                    expected.update(item['label'])
                    for run in item['runs']:
                        if not run.get('glyph'):expected.update(c for c in run['text'] if c.isalnum())
        for page in data['pages']:
            for block in page['blocks']:
                if block.get('continues_previous_page'):
                    spans=tree.xpath('//p/span[@data-source-page="'+str(page['source_page'])+'"]')
                    assert len(spans)==1,(p,page['source_page'])
                    assert spans[0].text_content()==''.join(r['text'] for r in block['runs'])
        main=tree.xpath('//main[@class="paper"]')[0]
        for notice in main.xpath('.//*[@class="notice"]'):notice.getparent().remove(notice)
        actual=Counter(c for c in main.text_content() if c.isalnum())
        assert actual==expected,(p,dict(expected-actual),dict(actual-expected))
        for value in tree.xpath('//@href|//@src'):
            assert (p.parent/value).exists(),(p,value)
            links+=1
        for page in data['pages']:
            assert page['body_character_conservation'];body_pages+=1;inline+=page['inline_glyphs']
    assert inline==m['inline_glyphs']
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for r in pool.map(compile_one,m['papers']):
            results.append(r);print(len(results),r['file'],r['compiled'],len(r['missing_glyphs']),flush=True)
    summary={'documents':m['documents'],'source_pages':body_pages,'relative_links_checked':links,'inline_glyphs':inline,'compiled':sum(r['compiled'] for r in results),'missing_glyph_documents':sum(bool(r['missing_glyphs']) for r in results),'browser_tested':False,'compilation':results}
    (ROOT/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    assert summary['compiled']==206
    assert summary['missing_glyph_documents']==0
if __name__=='__main__':main()
