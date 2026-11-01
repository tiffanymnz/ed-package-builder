"""Complete local COR draft assembly. No network requests or approval decisions."""
import io
import json
import math
import re
import os
import shutil
import tempfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import fitz
from PIL import Image, ImageOps
from ed_builder import volume
from calculator_evidence import screenshot_status

ROLES = {'invoice': 'Vendor Invoice', 'bid': 'Vendor Bid', 'estimate': 'Cost Estimate',
         'work_order': 'Work Order', 'hpir': 'HPIR / Inspection', 'other': 'Supporting Document',
         'approval': 'Official Approval (Transmittal Only)', 'exclude': 'Exclude From Package'}
ORDER = ('invoice', 'bid', 'estimate', 'work_order', 'hpir', 'other')
CENT = Decimal('.01')

def number(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0: raise ValueError()
        return result
    except Exception: raise ValueError('Enter a valid non-negative number.')

def rounded(value): return number(value).quantize(CENT, rounding=ROUND_HALF_UP)
def cash(value): return f'${rounded(value):,.2f}'

def bid_fingerprint(case):
    import hashlib
    def numeric_value(raw):
        try:return str(number(raw).normalize())
        except ValueError:return str(raw or '')
    value={key:case.get(key) for key in ('package_documents','vendor')}
    value['rate_per_cyd']=numeric_value(case.get('rate_per_cyd'))
    value['loads']=[{key:numeric_value(load.get(key,1 if key=='fill_fraction' else 0)) for key in ('length_ft','width_ft','side_height_ft','overage_height_ft','overage_cyd','fill_fraction')} for load in case.get('loads',[])]
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

def financial_fingerprint(case):
    import hashlib
    keys=('rate_per_cyd','invoice_quantity_cyd','invoice_amount_usd','invoice_deduction_usd',
          'invoice_quantity_basis','invoice_deduction_status','first_10_prior_work',
          'verified_first_10_amount','financial_confirmation_note')
    value={key:str(case.get(key,'')) for key in keys}
    value['load_dimensions']=[{key:str(load.get(key,'')) for key in ('length_ft','width_ft','side_height_ft',
        'overage_height_ft','overage_cyd','measured_load_cyd','fill_fraction')} for load in case.get('loads',[])]
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

def totals(case):
    quantity = sum((rounded(volume(load)['total']) for load in case['loads']), Decimal('0')).quantize(CENT)
    rate = number(case.get('rate_per_cyd', ''))
    gross = rounded(quantity*rate)
    allowance = Decimal('0') if case.get('first_10_prior_work') == 'yes' else Decimal('300')
    return dict(quantity=quantity, rate=rate, gross=gross, allowance=allowance,
                request=rounded(max(Decimal('0'), gross-allowance)),
                request_quantity=rounded(max(Decimal('0'), quantity-Decimal('10'))))

def description(case):
    value = totals(case)
    if value['quantity'] < 10 or value['gross'] < value['allowance']:
        raise ValueError('Resolve the quantity and allowance before generating a COR request.')
    if not case.get('bid_review_confirmed') or case.get('bid_confirmation_hash')!=bid_fingerprint(case):
        raise ValueError('Confirm the lowest received bid after reviewing the current documents and measurements.')
    if case.get('first_10_prior_work') == 'yes':
        adjustment = 'The contractual first-10-CYD allowance was handled on the referenced work order; no second deduction is applied.'
    else:
        adjustment = f"Less the contractual first-10-CYD allowance of {cash(value['allowance'])}, the requested amount is {cash(value['request'])}."
    return (f"24 AMC is requesting approval based on the lowest bid received, for a gross amount of {cash(value['gross'])} "
            f"for the removal of {value['quantity']:.2f} CYDs. {adjustment} "
            '(First 10 CYDs at the expense of the FSM).\n'
            f"TOTAL CYDS REMOVED: {value['quantity']:.2f} CYDS {cash(value['gross'])}\n"
            f"FSM EXPENSE 10 CYDS: -{cash(value['allowance'])}\n"
            f"COR APPROVAL REQUEST {value['request_quantity']:.2f} CYDS {cash(value['request'])}")

def parse_pages(value, count):
    if not str(value or '').strip(): return list(range(count))
    result = []
    for part in str(value).split(','):
        match = re.fullmatch(r'\s*(\d+)(?:\s*-\s*(\d+))?\s*', part)
        if not match: raise ValueError('Use page numbers such as 1-3, 5.')
        start, end = int(match[1]), int(match[2] or match[1])
        if start < 1 or end < start or end > count: raise ValueError('Page range is outside this document.')
        for page in range(start-1, end):
            if page in result: raise ValueError('Page ranges overlap.')
            result.append(page)
    return result

def classify_document(text, name=''):
    text = ' '.join(text.upper().split())
    if any(x in text for x in ('REPAIR SUMMARY', 'ESTIMATED TOTAL REPAIRS', 'BLUEBOOK')): return 'estimate'
    if re.search(r'\bINVOICE\b', text[:900]): return 'invoice'
    if re.search(r'\b(BID|PROPOSAL|QUOTATION)\b', text[:900]): return 'bid'
    if 'WORK ORDER' in text[:200]: return 'work_order'
    if 'HPIR' in text[:300]: return 'hpir'
    name = name.lower()
    for token, role in [('invoice','invoice'), ('bid','bid'), ('estimate','estimate'), ('bluebook','estimate'), ('hpir','hpir'), ('workorder','work_order')]:
        if token in name: return role
    return 'other'

def extract_costs(text):
    """Conservative labeled values only. Ambiguous totals remain blank for review."""
    patterns={
        'invoice_amount_usd':r'(?im)^\s*(?:grand\s+total|total|balance\s+due)\s*[:$\s]*(?:USD\s*)?\$?\s*([\d,]+\.\d{2})\s*$',
        'invoice_quantity_cyd':r'(?i)\bremoved(?:\s+and\s+(?:properly\s+)?disposed)?\s*:?\s*(\d+(?:\.\d+)?)\s*(?:CYD|cubic\s+yards)',
        'rate_per_cyd':r'(?i)(?:@|at)\s*\$\s*(\d+(?:\.\d+)?)\s*(?:per|/)\s*(?:CYD|cubic\s+yard)',
        'invoice_deduction_usd':r'(?im)^.*first\s*10\s*(?:CYD|cubic\s+yards).*?\(?-?\$\s*([\d,]+\.\d{2})\)?.*$',
    }
    values={}
    for key,pattern in patterns.items():
        matches={match.replace(',','') for match in re.findall(pattern,text)}
        if len(matches)==1:values[key]=next(iter(matches))
    return values

def document_suggestions(record):
    path = Path(record['path']); groups = []
    if path.suffix.lower() == '.pdf':
        with fitz.open(path) as doc:
            if doc.needs_pass: raise ValueError('Password-protected PDF. Save an unlocked copy first.')
            current = None
            for index, page in enumerate(doc):
                text = page.get_text()
                role = classify_document(text, record.get('name', '')) if text.strip() else (current or classify_document('', record.get('name','')))
                # Continuation pages without a heading stay with the preceding document section.
                if role == 'other' and current: role = current
                if groups and groups[-1]['role'] == role: groups[-1]['end'] = index+1
                else: groups.append(dict(role=role, start=index+1, end=index+1))
                current = role
    else: groups = [dict(role=classify_document('', record.get('name','')), start=1, end=1)]
    suggestions=[dict(path=str(path), name=record.get('name',path.name), role=g['role'],
                 pages=f"{g['start']}-{g['end']}", confirmed=False, amount='', vendor='') for g in groups]
    if path.suffix.lower()=='.pdf':
        with fitz.open(path) as doc:
            for item,group in zip(suggestions,groups):
                values=extract_costs('\n'.join(doc[i].get_text() for i in range(group['start']-1,group['end'])))
                item['cost_suggestions']=values
                if item['role']=='bid':item['amount']=values.get('invoice_amount_usd','')
    return suggestions

def labeled_measurements(text):
    """Only explicit labeled dimensions; do not assume the order of an unlabeled triplet."""
    values = {}
    for label, key in [('length','length_ft'), ('width','width_ft'), ('height','side_height_ft')]:
        hits = re.findall(r'\b'+label+r'\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:ft\b|feet\b|[\'′])', text, re.I)
        unique = set(hits)
        if len(unique) == 1 and 0 < float(hits[0]) < 100: values[key] = hits[0]
    return values

def photo_suggestion(record, text=''):
    text = record.get('name','').replace('_',' ')+' '+text
    load = re.search(r'\bload[\s_#:-]*(\d{1,3})\b', text, re.I)
    stage = None
    for token, slot in [(r'\bempty\b|\b0\s*%', 'empty'), (r'\b25\s*%|\bquarter full\b','quarter'),
                        (r'\b50\s*%|\bhalf full\b','half'), (r'\b75\s*%|\bthree quarters\b','three_quarters'),
                        (r'\b100\s*%|\bfull container\b','full_1'), (r'\bdump receipt\b|\bscale ticket\b','receipt')]:
        if re.search(token,text,re.I):
            if stage: stage = None; break
            stage = slot
    return dict(path=record['path'], name=record.get('name',''), load=int(load[1]) if load else None,
                slot=stage, dimensions=labeled_measurements(text), excerpt=text[:500])

def validate(case):
    problems = []
    for i, load in enumerate(case.get('loads',[]),1):
        try: volume(load)
        except Exception as exc: problems.append(f'Load {i}: Measurements need review: {exc}.')
        if not load.get('measurements_confirmed'): problems.append(f'Load {i}: Confirm the container measurements and final fill.')
        _, calculator_issue = screenshot_status(load)
        if calculator_issue: problems.append(f'Load {i}: {calculator_issue}')
        for key in ('height','width','length','empty','quarter','half','three_quarters','full_1','full_2','receipt'):
            path=load.get('photos',{}).get(key)
            if not path or not Path(path).is_file(): problems.append(f'Load {i}: Add {key.replace("_"," ")} evidence.')
        if not load.get('disposal_photo') or not Path(load['disposal_photo']).is_file(): problems.append(f'Load {i}: Add unloading / disposal evidence.')
        if len([p for p in load.get('extra_measurement_photos',[]) if Path(p).is_file()])<3: problems.append(f'Load {i}: Add the supplemental measurement photos.')
    if not case.get('loads'): problems.append('Add at least one reviewed load.')
    elif not case['loads'][0].get('evidence_first_10_cyd'): problems.append('Add the first-10-CYD evidence.')
    for phase in ('before_photos','during_photos','after_photos'):
        if not any(Path(p).is_file() for p in case.get(phase,[])): problems.append(f'Add property {phase.replace("_photos","")} photos.')
    if case.get('invoice_quantity_basis') not in ('includes','excludes'): problems.append('Confirm the invoiced quantity basis.')
    if case.get('invoice_deduction_status') not in ('yes','no','alternate'): problems.append('Confirm the deduction shown on the invoice.')
    if case.get('first_10_prior_work') not in ('yes','no'): problems.append('Confirm whether the first-10-CYD allowance was handled elsewhere.')
    if case.get('financial_confirmation_hash')!=financial_fingerprint(case): problems.append('Confirm the invoice treatment after the current inputs are reviewed.')
    docs = [d for d in case.get('package_documents',[]) if d.get('role') not in ('exclude','approval')]
    for role in ('invoice','bid','estimate'):
        if not any(d.get('role') == role and d.get('confirmed') for d in docs):
            problems.append(f'Review and include the {ROLES[role]}.')
    used = set()
    for record in docs:
        if not record.get('confirmed'): problems.append(f"Confirm document: {record.get('name','Document')}.")
        path = Path(record.get('path',''))
        if not path.is_file(): problems.append(f'Missing document file: {path.name}.'); continue
        try:
            if path.suffix.lower() == '.pdf':
                with fitz.open(path) as d:
                    if d.needs_pass: raise ValueError('PDF is password protected')
                    pages = parse_pages(record.get('pages'), len(d))
            elif path.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.bmp','.tif','.tiff'): pages = [0]
            else: raise ValueError('Save this document as a PDF before export')
            for page in pages:
                identity = (str(path.resolve()), page)
                if identity in used: problems.append(f'Overlapping document pages: {path.name}, page {page+1}.')
                used.add(identity)
        except Exception as exc: problems.append(f'{path.name}: {exc}.')
    bids = [d for d in docs if d.get('role')=='bid']
    amounts = []
    for record in bids:
        try: amounts.append(number(record.get('amount')))
        except ValueError: problems.append(f"Enter the bid amount for {record.get('name','bid')}.")
    if not case.get('bid_review_confirmed') or case.get('bid_confirmation_hash')!=bid_fingerprint(case):
        problems.append('Confirm that all received bids were included and the lowest bid was selected.')
    try:
        value = totals(case)
        if value['quantity'] < 10: problems.append('Total debris is below 10 CYD. Resolve whether a COR request applies.')
        if value['gross'] < value['allowance']: problems.append('The requested amount cannot be negative. Review quantity, rate and allowance.')
        if amounts and value['gross'] > min(amounts)+Decimal('.01'):
            problems.append('Calculated gross exceeds the lowest entered bid. Reconcile the rate or bid before approval.')
        if rounded(case.get('verified_first_10_amount'))!=Decimal('300.00'): problems.append('The first-10-CYD allowance must be $300.00.')
        shown=number(case.get('invoice_deduction_usd'))
        if case.get('invoice_deduction_status')=='yes' and shown!=Decimal('300'): problems.append('The shown invoice deduction must reconcile to the $300 allowance.')
        if case.get('invoice_quantity_basis')=='includes':
            expected=value['gross']-(shown if case.get('invoice_deduction_status')=='yes' else Decimal('0'))
            if abs(number(case.get('invoice_amount_usd'))-expected)>Decimal('.06'): problems.append('The net invoice amount does not reconcile to its stated deduction.')
        if case.get('invoice_deduction_status')=='no' and value['allowance']>0: problems.append('The invoice does not reflect the required allowance; resolve before approval.')
    except Exception: problems.append('Confirm measurements for every load and the final rate.')
    return list(dict.fromkeys(problems))

NAVY = (0.09, .17, .26)
def new_page(doc, title, subtitle=''):
    page = doc.new_page(width=612, height=792)
    page.insert_text((32,32),title,fontsize=13,fontname='hebo',color=NAVY)
    if subtitle: page.insert_textbox(fitz.Rect(32,40,580,69), subtitle, fontsize=9, color=(.35,.4,.46))
    page.insert_text((32,776),'DRAFT - Human Review Required',fontsize=8,color=(.4,.4,.4))
    return page

def insert_picture(page, rectangle, path):
    path = Path(path)
    if path.suffix.lower() == '.pdf':
        with fitz.open(path) as source: page.show_pdf_page(rectangle,source,0)
    else:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert('RGB')
            stream = io.BytesIO(); image.save(stream,format='PNG')
            page.insert_image(rectangle,stream=stream.getvalue(),keep_proportion=True)

def picture_pages(doc, items, title, subtitle=''):
    for start in range(0,len(items),6):
        page = new_page(doc,title,subtitle)
        for i,(label,path) in enumerate(items[start:start+6]):
            row,col = divmod(i,2); x=32+col*280; y=77+row*224
            page.insert_textbox(fitz.Rect(x,y,x+268,y+20),label,fontsize=10,fontname='hebo')
            rectangle = fitz.Rect(x,y+24,x+268,y+210)
            page.draw_rect(rectangle,color=(.82,.85,.88),width=.5)
            if path and Path(path).is_file(): insert_picture(page,rectangle,path)
            else: page.insert_textbox(rectangle+fitz.Rect(10,10,-10,-10),'Missing Evidence - Draft Only',fontsize=10,color=(.6,.3,.1))

def assemble(case, destination, issues=None):
    """Build PDF without Word/LibreOffice. All selected source pages are preserved."""
    destination = Path(destination); destination.parent.mkdir(parents=True,exist_ok=True)
    errors = list(dict.fromkeys((issues or [])+validate(case)))
    with tempfile.TemporaryDirectory(dir=destination.parent,prefix='.cor-build-') as temp:
        temp = Path(temp); doc = fitz.open(); manifest=[]
        try:
            for role in ORDER:
                for item in case.get('package_documents',[]):
                    if item.get('role')!=role: continue
                    path = Path(item['path']); start=len(doc)+1
                    if path.suffix.lower()=='.pdf':
                        with fitz.open(path) as source:
                            if source.needs_pass: raise ValueError(f'Unlock PDF: {path.name}')
                            pages=parse_pages(item.get('pages'),len(source))
                            for index in pages: doc.insert_pdf(source,from_page=index,to_page=index)
                    else:
                        if path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.bmp','.tiff','.tif'):
                            raise ValueError(f'Save {path.name} as a PDF before export. Nothing was silently omitted.')
                        page=new_page(doc,ROLES[role],item.get('name',path.name));insert_picture(page,fitz.Rect(32,78,580,750),path)
                        pages=[0]
                    manifest.append(dict(section=ROLES[role],source=str(path),source_pages=[x+1 for x in pages],start_page=start,end_page=len(doc)))
            if not any(x['section']=='Vendor Invoice' for x in manifest):
                page=new_page(doc,'Vendor Invoice Missing');page.insert_text((32,100),'INCOMPLETE DRAFT - Attach and review the vendor invoice.',fontsize=11)
            for i,load in enumerate(case['loads'],1):
                start=len(doc)+1
                calculator,problem=screenshot_status(load)
                photos=load.get('photos',{})
                picture_pages(doc,[(name,calculator if key=='calculator' else photos.get(key)) for key,name in
                    [('calculator','CalculatorSoup Measurement Screenshot'),('height','Final Height'),('width','Width'),('length','Length'),('empty','Empty Container'),('quarter','Quarter Full')]],
                    f'Load {i} - Container Measurements',f"Container: {load.get('container_name') or 'Not Identified'}")
                picture_pages(doc,[(name,photos.get(key)) for key,name in [('half','Half Full'),('three_quarters','Three-Quarters Full'),('full_1','Full Container - View 1'),('full_2','Full Container - View 2'),('receipt','Dump Receipt')]],f'Load {i} - Loading Progression')
                additional=[('Unloading / Disposal',load.get('disposal_photo')),('First 10 CYD Evidence',load.get('evidence_first_10_cyd'))]+[(f'Additional Measurement {j}',p) for j,p in enumerate(load.get('extra_measurement_photos',[]),1)]
                additional=[item for item in additional if item[1]]
                if additional: picture_pages(doc,additional,f'Load {i} - Supporting Evidence')
                manifest.append(dict(section=f'Load {i}',start_page=start,end_page=len(doc)))
            for key,title in [('before_photos','Before Photos'),('during_photos','During Photos'),('after_photos','After Photos')]:
                items=[(f'{title} - {i}',p) for i,p in enumerate(case.get(key,[]),1)]
                if items:
                    start=len(doc)+1;picture_pages(doc,items,title)
                    manifest.append(dict(section=title,start_page=start,end_page=len(doc)))
            # Internal checklist stays out of the submission PDF; the external draft has a cover warning only when incomplete.
            if errors:
                import textwrap
                lines=[]
                for problem in errors: lines.extend(textwrap.wrap('- '+problem,width=95)+[''])
                for offset in range(0,len(lines),48):
                    page=new_page(doc,'Incomplete Draft - Review Checklist')
                    page.insert_textbox(fitz.Rect(32,80,580,740),'\n'.join(lines[offset:offset+48]),fontsize=9)
            elif not errors:
                (temp/'COR_Request_Description.txt').write_text(description(case),encoding='utf-8')
            report=dict(status='INCOMPLETE DRAFT' if errors else 'DRAFT - FINAL HUMAN REVIEW REQUIRED',issues=errors,pages=len(doc),sections=manifest)
            doc.set_metadata({'title':f"ED COR Package - {case.get('case_number','Case')} - DRAFT",'author':'ED Package Builder'})
            doc.save(temp/'package.pdf',garbage=3,deflate=True)
        finally: doc.close()
        # Publish only after the entire document was assembled successfully.
        os.replace(temp/'package.pdf',destination)
        (destination.parent/'Package_Review.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        desc=destination.parent/'COR_Request_Description.txt'
        if (temp/desc.name).exists(): os.replace(temp/desc.name,desc)
        elif desc.exists(): desc.unlink()  # Never leave a description from an older, valid state.
    return report
