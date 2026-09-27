"""Exact reviewed promotion areas, applied only to in-memory reading copies.

No keyword-based deletion of exam prose. Input PDF files are never saved.
"""
import fitz

def clean_document(doc, collection, document_id=None):
    records=[]
    for i,page in enumerate(doc):
        rectangles=[]
        if collection=='math3-2009-2019':
            assert '数学领课' in page.get_text() and page.rect.height<665
            rectangles=[fitz.Rect(71,643,186,655.5),fitz.Rect(253,643,389,655.5)]
        elif collection=='cs408' and document_id=='2018-answers' and i==3:
            assert '淘宝店铺：光速考研工作室' in page.get_text()
            rectangles=[fitz.Rect(54,35,178,53.5),fitz.Rect(180.13,35.39,227.42,41.17)]
        elif collection=='cs408' and document_id=='2019-answers' and i==11:
            # Scanned pink diagonal shop promotion in the empty lower-right
            # margin, verified against the page image and independent OCR.
            assert abs(page.rect.width-470.16)<.1 and page.rect.height==708
            rectangles=[fitz.Rect(335,515,469,642)]
        if rectangles:
            for rect in rectangles:page.add_redact_annot(rect,fill=(1,1,1))
            # For the full-page scan, preserve its original image encoding:
            # an opaque vector margin mask avoids resampling all answer text.
            images=fitz.PDF_REDACT_IMAGE_NONE if document_id=='2019-answers' else fitz.PDF_REDACT_IMAGE_PIXELS
            page.apply_redactions(images=images,graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,text=fitz.PDF_REDACT_TEXT_REMOVE)
            records.append({'source_page':i+1,'rectangles':[list(r) for r in rectangles]})
    return records
