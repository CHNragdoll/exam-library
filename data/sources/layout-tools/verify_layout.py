"""Verify staged or installed HTM against cached source documents, offline."""
import argparse
import base64
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, unquote
import fitz
from lxml import etree, html
from archive_renderer import digest, safe_text, validate_svg, RENDERER_VERSION
from catalog_design import page_without_url,URL_MARK
from repair_archive import SOURCES, COMBINED, LEGACY, STAGE, source_pdf, write_json

def verify(base, visual=True):
    root=base/COMBINED.name
    manifest=json.loads((root/'manifest.json').read_text())
    assert manifest['completed']==206 and not manifest['failures']
    expected={u for c in json.loads((COMBINED/'.firecrawl/catalogs.json').read_text()) for u in c['links']}
    assert expected=={r['source_url'] for r in manifest['papers'] if r['category']!='kaoyan'}
    pages=0; links=0; warning_pages=0; visual_checks=[]
    evidence=root/'assets/layout-repair';evidence.mkdir(parents=True,exist_ok=True)
    # All reported examples, plus other old/new exam types and encoding failures.
    samples={'kaoyan/papers/2026-01.htm':{1,7,8,12,13,14},
             'kaoyan/papers/2000-01.htm':{1}, 'kaoyan/papers/2014-01.htm':{12},
             'cet4/papers/2020-12-01.htm':{5}, 'cet4/papers/2026-06-02.htm':{1},
             'cet6/papers/2020-09-02.htm':{8}, 'cet6/papers/2026-06-03.htm':{1},
             'tem4/papers/2025.htm':{1}, 'tem8/papers/2025.htm':{1}}
    for i,entry in enumerate(manifest['papers'],1):
        f=root/entry['file'];data=f.read_bytes()
        assert digest(data)==entry['htm_sha256'],f
        assert entry['renderer']==RENDERER_VERSION
        doc=html.fromstring(data.decode(),parser=html.HTMLParser(huge_tree=True))
        assert not doc.xpath('//script|//iframe|//link'),f
        ids=doc.xpath('//@id');assert len(set(ids))==len(ids),f
        assert len(doc.xpath('//style'))==1
        style=doc.xpath('//style')[0].text
        assert '.page-art{display:block;width:100%;height:auto;' in style
        assert '.page-wrap{max-width:940px;width:100%;' in style
        sections=doc.xpath('//section[@data-page]');assert len(sections)==entry['pages'],f
        pdf=source_pdf(entry);assert digest(pdf.read_bytes())==entry['source_pdf_sha256']
        with fitz.open(pdf) as original:
            assert len(original)==len(sections)
            for n,(section,meta,page) in enumerate(zip(sections,entry['page_rendering'],original,strict=True),1):
                raw_page=page
                if entry['renderer']=='outline-svg-2-clean':
                    page,temporary_doc,removed=page_without_url(raw_page)
                    assert removed==meta['removed_url_rectangles'],(f,n,'URL bounds')
                    normal=lambda x:re.sub(r'\s+','',x)
                    assert normal(page.get_text())==URL_MARK.sub('',normal(raw_page.get_text())),(f,n,'unrelated text changed')
                assert int(section.get('data-page'))==n
                accessible=section.xpath('.//div[@class="sr-only"]')
                assert len(accessible)==1 and ''.join(accessible[0].itertext())==safe_text(page.get_text())
                pre=section.xpath('.//pre[@class="source-text"]')
                assert len(pre)==1 and ''.join(pre[0].itertext())==safe_text(page.get_text()),(f,n,'copy text')
                assert digest(raw_page.get_text().encode())==meta['text_sha256'],(f,n,'source text')
                images=section.xpath('.//img[@class="page-art"]');assert len(images)==1
                src=images[0].get('src');assert not urlsplit(src).scheme and src==f.stem+f'.assets/page-{n:03}.svg'
                svg=(f.parent/src).read_bytes()
                assert digest(svg)==meta['svg_sha256'],(f,n,'SVG bytes')
                tree=etree.fromstring(svg,parser=etree.XMLParser(huge_tree=True))
                validate_svg(tree)
                box=list(map(float,tree.get('viewBox').split()))
                assert abs(box[2]-page.rect.width)<.001 and abs(box[3]-page.rect.height)<.001
                overlays=section.xpath('.//*[local-name()="svg" and @class="text-overlay"]')
                assert len(overlays)==1 and overlays[0].get('aria-hidden')=='true'
                assert all(t.get('fill')=='transparent' for t in overlays[0].xpath('.//*[local-name()="text"]'))
                warning_pages+=meta['source_encoding_warning']
                if visual and n in samples.get(entry['file'],set()):
                    assert svg==page.get_svg_image(text_as_path=True).encode(),(f,n,'regenerated SVG')
                    stem=entry['category']+'-'+f.stem+f'-p{n}'
                    svg_path=evidence/(stem+'.svg');svg_path.write_bytes(svg)
                    source=page.get_pixmap(dpi=96,alpha=False)
                    source.save(evidence/(stem+'-source.png'))
                    image_path=evidence/(stem+'-fixed.png')
                    subprocess.run(['rsvg-convert','-w',str(source.width),'-h',str(source.height),'-b','white','-o',str(image_path),str(svg_path)],check=True)
                    rendered=fitz.Pixmap(str(image_path))
                    if rendered.alpha:rendered=fitz.Pixmap(rendered,0)
                    assert rendered.width==source.width and rendered.height==source.height and rendered.n==source.n
                    error=sum(abs(a-b) for a,b in zip(source.samples,rendered.samples,strict=True))/len(source.samples)
                    # Independent rasterizers differ at antialiased glyph edges.
                    # A difference triggers manual visual review, not a relaxed pass.
                    needs_review=error>=8
                    visual_checks.append({'file':entry['file'],'page':n,'requires_manual_raster_review':needs_review,'mean_absolute_channel_error_0_to_255':round(error,4),'width':source.width,'height':source.height})
                pages+=1
        print(f'VERIFIED {i}/206 {entry["file"]}',flush=True)
    for f in [root/'index.htm']+list(root.glob('*/index.htm'))+[root/r['file'] for r in manifest['papers']]:
        d=html.fromstring(f.read_text(),parser=html.HTMLParser(huge_tree=True))
        for href in d.xpath('//a/@href'):
            u=urlsplit(href)
            if not u.scheme and u.path:
                assert (f.parent/unquote(u.path)).is_file(),(f,href)
                links+=1
    legacy=json.loads((base/LEGACY.name/'manifest.json').read_text())
    assert legacy['completed']==44 and not legacy['failures']
    assert len(legacy['papers'])==44 and sum(r['pages'] for r in legacy['papers'])==609
    for r in legacy['papers']:
        a=base/LEGACY.name/r['file'];b=root/'kaoyan'/r['file']
        assert a.read_bytes()==b.read_bytes() and digest(a.read_bytes())==r['htm_sha256'],a
        expected_assets={f'page-{n:03}.svg' for n in range(1,r['pages']+1)}
        assert {p.name for p in a.with_suffix('.assets').glob('*.svg')}==expected_assets,a
        for n,meta in enumerate(r['page_rendering'],1):
            asset=a.with_suffix('.assets')/f'page-{n:03}.svg'
            assert asset.is_file() and digest(asset.read_bytes())==meta['svg_sha256'],asset
            assert asset.read_bytes()==(b.with_suffix('.assets')/asset.name).read_bytes(),asset
    assert pages==2020
    report={'renderer':RENDERER_VERSION,'papers':206,'pages':pages,'all_public_catalog_urls_saved':True,
            'source_pdf_hashes_unchanged':True,'embedded_svg_hashes_passed':True,'copy_text_matches_xml_safe_source':True,
            'offline_svg_resources_valid':True,'internal_links_checked':links,'legacy_44_copies_identical':True,
            'source_encoding_warning_pages':warning_pages,'visual_checks':visual_checks,
            'browser_visual_check':False,'browser_limit':'Browser file URL navigation was blocked; no browser workaround used. SVG rendering independently checked with librsvg against source PDF rendering.',
            'responsive_verification':'CSS width constraints and identical viewBox aspect ratios verified; browser interaction not tested.'}
    report_name='verification-latest-check.json' if base==SOURCES else 'verification.json'
    write_json(root/report_name,report)
    legacy_report=dict(report,papers=44,pages=609,visual_checks=[v for v in visual_checks if v['file'].startswith('kaoyan/')])
    write_json(base/LEGACY.name/report_name,legacy_report)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--installed',action='store_true');p.add_argument('--no-visual',action='store_true');args=p.parse_args()
    report=verify(SOURCES if args.installed else STAGE,not args.no_visual)
    print('STRUCTURAL PASS; raster review flags recorded',json.dumps({k:report[k] for k in ('papers','pages','source_encoding_warning_pages')})+f' visual samples: {len(report["visual_checks"])}')
