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

ROLES = {'invoice': 'Final Invoice', 'bid': 'Vendor Bid', 'estimate': 'RBB / Bluebook',
         'work_order': 'Work Order', 'hpir': 'HPIR / Inspection', 'other': 'Supporting Document',
         'approval': 'Official Approval (Transmittal Only)', 'exclude': 'Exclude From Package'}
ORDER = ('approval', 'work_order', 'invoice', 'bid', 'estimate', 'hpir', 'other')
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
          'invoice_quantity_basis','invoice_deduction_status','financial_confirmation_note')
    def stable(raw):
        try:return str(number(raw).normalize())
        except ValueError:return str(raw or '')
    value={key:stable(case.get(key,'')) for key in keys}
    value['hud_calculation_rule']='first-10-cyd-at-request-rate-v1'
    value['load_dimensions']=[{key:stable(load.get(key,'')) for key in ('length_ft','width_ft','side_height_ft',
        'overage_height_ft','overage_cyd','measured_load_cyd','fill_fraction')} for load in case.get('loads',[])]
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

def totals(case):
    quantity = sum((rounded(volume(load)['total']) for load in case['loads']), Decimal('0')).quantize(CENT)
    rate = number(case.get('rate_per_cyd', ''))
    gross = rounded(quantity*rate)
    allowance = rounded(min(quantity,Decimal('10'))*rate)
    return dict(quantity=quantity, rate=rate, gross=gross, allowance=allowance,
                request=rounded(max(Decimal('0'), gross-allowance)),
                request_quantity=rounded(max(Decimal('0'), quantity-Decimal('10'))))

def description(case):
    if case.get('financial_confirmation_hash')!=financial_fingerprint(case):
        raise ValueError('Confirm the invoice and current rate-based HUD deduction first.')
    bid_issues=bid_requirements(case)
    if bid_issues:raise ValueError('\n'.join(bid_issues))
    value = totals(case)
    if value['quantity'] < 10 or value['gross'] < value['allowance']:
        raise ValueError('Resolve the quantity and allowance before generating a COR request.')
    if not case.get('bid_review_confirmed') or case.get('bid_confirmation_hash')!=bid_fingerprint(case):
        raise ValueError('Confirm the lowest received bid after reviewing the current documents and measurements.')
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
    if re.search(r'\b(BID|PROPOSAL|QUOTATION|PRICE QUOTE)\b', text[:900]): return 'bid'
    if 'WORK ORDER' in text[:200]: return 'work_order'
    if 'HPIR' in text[:300]: return 'hpir'
    name = name.lower()
    for token, role in [('invoice','invoice'), ('bid','bid'), ('estimate','estimate'), ('bluebook','estimate'), ('hpir','hpir'), ('workorder','work_order')]:
        if token in name: return role
    return 'other'

def extract_costs(text):
    """Conservative labeled values only. Ambiguous totals remain blank for review."""
    def normalized(raw):
        if not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?',raw):return None
        return raw.replace(',','')
    patterns={
        'invoice_amount_usd':r'(?im)^\s*(?:grand\s+total|total|balance\s+due)\s*[:$\s]*(?:USD\s*)?\$?\s*(\d[\d,]*\.\d{2})\s*$',
        'invoice_quantity_cyd':r'(?i)\bremoved(?:\s+and\s+(?:properly\s+)?disposed)?\s*:?\s*(\d+(?:\.\d+)?)\s*(?:CYD|cubic\s+yards)',
        'rate_per_cyd':r'(?i)(?:@|at)\s*\$\s*(\d+(?:\.\d+)?)\s*(?:per|/)\s*(?:CYD|cubic\s+yard)',
        'invoice_deduction_usd':r'(?im)^.*first\s*10\s*(?:CYD|cubic\s+yards).*?\(?-?\$\s*(\d[\d,]*\.\d{2})\)?.*$',
    }
    values={}
    for key,pattern in patterns.items():
        matches={value for match in re.findall(pattern,text) if (value:=normalized(match)) is not None}
        if len(matches)==1:values[key]=next(iter(matches))
    # Read explicitly printed values. Never calculate invoice quantities from
    # typed dimensions or replace the separate photo-supported measurements.
    rate_values={Decimal(value) for x in re.findall(
        r'(?i)\brate\s*(?:per|/)\s*(?:cubic\s+yard|CYD)s?\s*[:\s]*\$\s*(\d[\d,]*(?:\.\d{1,2})?)',text) if (value:=normalized(x)) is not None}
    if 'rate_per_cyd' in values:rate_values.add(Decimal(values['rate_per_cyd']))
    if len(rate_values)==1:values['rate_per_cyd']=str(next(iter(rate_values)))
    elif len(rate_values)>1:values.pop('rate_per_cyd',None)
    quantities={Decimal(x) for x in re.findall(r'(?i)\btotal\s+(?:CYDs?|cubic\s+yards)(?:\s+removed)?\s*[:=]\s*(\d+(?:\.\d+)?)',text)}
    per_load={};ambiguous=False
    for load_id,quantity in re.findall(r'(?im)^\s*load\s*#?\s*(\d+)\s*:\s*[^\n=]{0,120}=\s*(\d+(?:\.\d+)?)\s*(?:CYDs?|cubic\s+yards)\b',text):
        value=Decimal(quantity);load_id=str(int(load_id))
        if load_id in per_load and per_load[load_id]!=value:ambiguous=True
        per_load[load_id]=value
    if per_load and not ambiguous:quantities.add(sum(per_load.values(),Decimal(0)))
    if 'invoice_quantity_cyd' in values:quantities.add(Decimal(values['invoice_quantity_cyd']))
    if ambiguous or len(quantities)>1:values.pop('invoice_quantity_cyd',None)
    elif len(quantities)==1:values['invoice_quantity_cyd']=str(next(iter(quantities)))
    deductions=set()
    if 'invoice_deduction_usd' in values:deductions.add(Decimal(values['invoice_deduction_usd']))
    for match in re.finditer(r'(?im)^\s*(?:first\s*)?10\s*(?:CYDs?|cubic\s+yards)\b[^\n]*',text):
        line=match.group(0)
        if not re.search(r'(?i)first|FSM|responsib|deduct|initial',line):continue
        # Parenthesized/negative money distinguishes the deduction from a nearby
        # per-CYD rate. Stop at the next line-item total rather than scan footer fees.
        block=text[match.start():match.end()+100]
        block=re.split(r'(?im)^\s*(?:sub\s*total|grand\s*total|total|balance|load\s*\d+)\b',block)[0]
        for amount in re.findall(r'\(\s*\$\s*(\d[\d,]*\.\d{2})\s*\)|-\s*\$\s*(\d[\d,]*\.\d{2})',block):
            value=normalized(next(x for x in amount if x))
            if value is not None:deductions.add(Decimal(value))
    if len(deductions)==1:values['invoice_deduction_usd']=str(next(iter(deductions)))
    elif len(deductions)>1:values.pop('invoice_deduction_usd',None)
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

def apply_document_text_suggestions(case):
    """Use fresh local OCR as editable suggestions, preserving confirmed entries."""
    from calculator_evidence import file_digest
    for document in case.get('package_documents',[]):
        path=document.get('path','');cached=case.get('photo_text_cache',{}).get(path,{})
        if not cached.get('text') or not cached.get('sha256'):continue
        try:
            if cached['sha256']!=file_digest(path):continue
        except OSError:continue
        values=extract_costs(cached['text']);document['cost_suggestions']=values
        if document.get('confirmed'):continue
        role=classify_document(cached['text'])
        if document.get('role')=='other' and role!='other':document['role']=role
        if document.get('role')=='bid' and not str(document.get('amount','')).strip():
            document['amount']=values.get('invoice_amount_usd','')

def labeled_measurements(text):
    """Read explicit labeled imperial dimensions; leave ambiguous values blank."""
    from fractions import Fraction
    number=r'(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)'
    feet=r"(?:ft\b|feet\b|foot\b|['′])"
    inches=r'(?:in\b|inches\b|inch\b|["″])'
    def numeric(raw):
        return sum(float(Fraction(part)) for part in raw.split())
    labels=list(re.finditer(r'\b(length|width|height)\s*[:=]?\s*',text,re.I))
    found={};bad=set()
    for index,label in enumerate(labels):
        key={'length':'length_ft','width':'width_ft','height':'side_height_ft'}[label[1].lower()]
        segment=text[label.end():labels[index+1].start() if index+1<len(labels) else len(text)].split('\n',1)[0].strip(' \t,;')
        mixed=re.fullmatch(r'('+number+r')\s*'+feet+r'(?:\s*(?:and\s+)?('+number+r')\s*'+inches+r')?',segment,re.I)
        inch_only=re.fullmatch(r'('+number+r')\s*'+inches,segment,re.I)
        try:
            if mixed:
                extra=numeric(mixed[2]) if mixed[2] else 0
                if not 0<=extra<12:raise ValueError('Invalid inch component')
                value=numeric(mixed[1])+extra/12
            elif inch_only:value=numeric(inch_only[1])/12
            else:raise ValueError('Unsupported or incomplete measurement')
            if not 0<value<100:raise ValueError('Out of range')
            found.setdefault(key,set()).add(format(value,'.10g'))
        except (ValueError,ZeroDivisionError):bad.add(key)
    result={key:next(iter(values)) for key,values in found.items() if len(values)==1 and key not in bad}
    # A compact card must explicitly label its axis order and every unit.
    # Never assume an unlabeled "19 x 7.8 x 6.5" means L/W/H or feet.
    unit_value=r'('+number+r')\s*'+feet
    triples=list(re.finditer(unit_value+r'\s*[x×]\s*'+unit_value+r'\s*[x×]\s*'+unit_value,text,re.I))
    card_values={};card_bad=False
    axis=r'(length|width|height|L|W|H)'
    for triple in triples:
        neighborhood=text[max(0,triple.start()-80):min(len(text),triple.end()+80)]
        axes=re.findall(r'\b'+axis+r'\s*(?:[x×]\s*|\s+)'+axis+r'\s*(?:[x×]\s*|\s+)'+axis+r'\b',neighborhood,re.I)
        orders={tuple(label[0].lower() for label in order) for order in axes}
        if len(orders)!=1 or len(set(next(iter(orders))))!=3:continue
        order=next(iter(orders));mapping={'l':'length_ft','w':'width_ft','h':'side_height_ft'}
        try:
            vals=[numeric(triple[index]) for index in (1,2,3)]
            if any(not 0<value<100 for value in vals):raise ValueError()
            for label,value in zip(order,vals):card_values.setdefault(mapping[label],set()).add(format(value,'.10g'))
        except (ValueError,ZeroDivisionError):card_bad=True
    if not card_bad:
        for key,values in card_values.items():
            if len(values)>1 or (key in result and result[key] not in values):result.pop(key,None)
            elif len(values)==1:result[key]=next(iter(values))
    return result

def photo_suggestion(record, text=''):
    # Filenames are display labels only, never evidence of contents or load.
    from review_assist import visible_load_numbers
    loads=visible_load_numbers(text)
    document=classify_document(text) in ('invoice','bid','estimate')
    stage = None
    for token, slot in [(r'\bempty\b|\b0\s*%', 'empty'), (r'\b25\s*%|\bquarter full\b|(?:1\s*/\s*4|¼)\s*full\b','quarter'),
                        (r'\b50\s*%|\bhalf full\b|(?:1\s*/\s*2|½)\s*full\b','half'), (r'\b75\s*%|\bthree quarters\b|(?:3\s*/\s*4|¾)\s*full\b','three_quarters'),
                        (r'\b100\s*%|\bfull container\b','full_1'), (r'\bdump receipt\b|\bscale ticket\b','receipt')]:
        if re.search(token,text,re.I):
            if stage: stage = None; break
            stage = slot
    dimensions={} if document else labeled_measurements(text)
    if stage is None and len(dimensions)==1:
        stage={'length_ft':'length','width_ft':'width','side_height_ft':'height'}[next(iter(dimensions))]
    return dict(path=record['path'], name=record.get('name',''), load=loads[0] if len(loads)==1 and not document else None,
                slot=None if document else stage, dimensions=dimensions, excerpt=text[:500],
                note='Review the original; multiple load numbers are visible.' if len(loads)>1 else '')

def current_photo_suggestions(case):
    from calculator_evidence import file_digest
    rows=[]
    for record in case.get('imported_files',[]):
        path=record['path'];cached=case.get('photo_text_cache',{}).get(path,{})
        if Path(path).suffix.lower() not in ('.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff'):continue
        if not cached.get('text') or not cached.get('sha256'):continue
        try:
            if file_digest(path)!=cached['sha256']:continue
        except OSError:continue
        row=photo_suggestion(record,cached['text']);row['sha256']=cached['sha256']
        if row.get('load') or row.get('slot') or row.get('dimensions') or row.get('note'):rows.append(row)
    return rows

def apply_photo_suggestions(case, selected):
    """Revalidate the full selected batch, then commit without partial updates."""
    import copy
    from ed_app import default_load
    current={row['path']:row for row in current_photo_suggestions(case)}
    proposed=copy.deepcopy(case.get('loads',[]));touched=set();financial_changed=False
    new_loads={row['load'] for row in selected if isinstance(row.get('load'),int) and row['load']>len(proposed)}
    if new_loads and new_loads!=set(range(len(proposed)+1,max(new_loads)+1)):
        raise ValueError('A load number skips existing loads. Check the original and add the correct loads manually.')
    for row in selected:
        fresh=current.get(row.get('path'))
        if fresh is None or any(row.get(key)!=fresh.get(key) for key in ('sha256','load','slot','dimensions')):
            raise ValueError('A source photo or its reading changed. Read and review the current photo again.')
        n=fresh.get('load')
        if not n or not 1<=n<=150:raise ValueError('Choose a photo with one readable load number; otherwise assign it manually.')
        while len(proposed)<n:proposed.append(default_load(len(proposed)+1))
        load=proposed[n-1];slot=fresh.get('slot')
        if slot:
            old=load.setdefault('photos',{}).get(slot)
            if old and old!=fresh['path']:raise ValueError(f'Load {n}: {slot} already has a different photo. Choose the clearest view manually.')
            load['photos'][slot]=fresh['path']
        for key,value in fresh['dimensions'].items():
            old=load.get(key)
            if old not in (None,'') and number(old)!=number(value):
                raise ValueError(f'Load {n}: {key.replace("_ft","")} conflicts with an existing value. Compare the originals before applying.')
            if old in (None,''):financial_changed=True
            load[key]=value
        if slot or fresh['dimensions']:
            touched.add(n)
            if fresh['dimensions'] or slot in ('height','width','length'):
                load['measurement_source']='Reviewed Photo Text';load['measurements_confirmed']=False
    if touched:
        financial_changed=financial_changed or len(proposed)!=len(case.get('loads',[]))
        case['loads']=proposed
        if financial_changed:
            case['bid_review_confirmed']=False
            case.pop('bid_confirmation_hash',None);case.pop('financial_confirmation_hash',None)
    return len(touched)

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
        # The package template uses one reviewed photo per dimension. Additional
        # views support verification; their count is not a package requirement.
    if not case.get('loads'): problems.append('Add at least one reviewed load.')
    elif not case['loads'][0].get('evidence_first_10_cyd'): problems.append('Add the first-10-CYD evidence.')
    for phase in ('before_photos','during_photos','after_photos'):
        if not any(Path(p).is_file() for p in case.get(phase,[])): problems.append(f'Add property {phase.replace("_photos","")} photos.')
    if case.get('invoice_quantity_basis') not in ('includes','excludes'): problems.append('Confirm the invoiced quantity basis.')
    if case.get('invoice_deduction_status') not in ('yes','no','alternate'): problems.append('Confirm the deduction shown on the invoice.')
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
    problems.extend(bid_requirements(case))
    amounts = []
    for record in bids:
        try: amounts.append(number(record.get('amount')))
        except ValueError: problems.append(f"Enter the bid amount for {record.get('name','bid')}.")
    if not case.get('bid_review_confirmed') or case.get('bid_confirmation_hash')!=bid_fingerprint(case):
        problems.append('Confirm that all received bids were included and the lowest bid was selected.')
    try:
        value = totals(case)
        if value['rate']<=0:problems.append('Confirm a positive HUD request rate.')
        if value['quantity'] < 10: problems.append('Total debris is below 10 CYD. Resolve whether a COR request applies.')
        if value['gross'] < value['allowance']: problems.append('The requested amount cannot be negative. Review quantity, rate and allowance.')
        if amounts and value['gross'] > min(amounts)+Decimal('.01'):
            problems.append('Calculated gross exceeds the lowest entered bid. Reconcile the rate or bid before approval.')
        shown=number(case.get('invoice_deduction_usd'))
        if case.get('invoice_deduction_status')=='yes' and shown!=value['allowance']: problems.append('The invoice deduction differs from 10 CYD at the HUD request rate. Reconcile the invoice.')
        if case.get('invoice_deduction_status')=='no' and shown!=0:problems.append('The invoice deduction conflicts with the selected No answer.')
        billed=number(case.get('invoice_quantity_cyd'))
        target=value['quantity'] if case.get('invoice_quantity_basis')=='includes' else value['request_quantity']
        if abs(billed-target)>Decimal('.02'):problems.append('Invoice cubic yards differ from the photo-supported measured quantity. Reconcile the invoice; do not overwrite the photo measurements.')
        if case.get('invoice_quantity_basis')=='includes':
            expected=value['gross']-(shown if case.get('invoice_deduction_status')=='yes' else Decimal('0'))
            if abs(number(case.get('invoice_amount_usd'))-expected)>Decimal('.06'): problems.append('The net invoice amount does not reconcile to its stated deduction.')
        elif case.get('invoice_quantity_basis')=='excludes':
            if abs(number(case.get('invoice_amount_usd'))-value['request'])>Decimal('.06'):problems.append('The invoice excludes the first 10 CYD, but its total does not reconcile to the excess-debris amount.')
    except Exception: problems.append('Confirm measurements for every load and the final rate.')
    return list(dict.fromkeys(problems))

def required_bid_count(case):
    """Apply the confirmed under/over rule where plausible amount bases agree."""
    amounts=[]
    try:
        value=totals(case);amounts.extend([value['gross'],value['request']])
    except (ValueError,KeyError):pass
    bids=[]
    for d in case.get('package_documents',[]):
        if d.get('role')=='bid':
            try:
                amount=number(d.get('amount'))
                if amount>0:bids.append(amount)
            except ValueError:pass
    if bids:amounts.append(min(bids))
    try:amounts.append(number(case.get('invoice_amount_usd')))
    except ValueError:pass
    amounts=[a for a in amounts if a>0]
    if not amounts:return None
    if all(a<2500 for a in amounts):return 1
    if all(a>2500 for a in amounts):return 3
    return None # Exact boundary / gross-versus-net basis has not been confirmed.

def bid_requirements(case):
    """One bid under $2,500; three over; do not invent unresolved boundary rules."""
    from calculator_evidence import file_digest
    issues=[];distinct=set()
    for bid in case.get('package_documents',[]):
        if bid.get('role')!='bid':continue
        name=bid.get('name','Bid')
        if not bid.get('confirmed'):
            issues.append(f'Review bid: {name}.');continue
        try:
            if number(bid.get('debris_quantity_cyd'))<=0:raise ValueError()
        except ValueError:
            issues.append(f'Confirm the debris quantity shown on {name}.');continue
        try:
            path=Path(bid.get('path',''))
            if path.suffix.lower()=='.pdf':
                with fitz.open(path) as doc:pages=tuple(parse_pages(bid.get('pages'),len(doc)))
            else:pages=(0,)
            distinct.add((file_digest(path),pages))
        except Exception:continue # File/page errors are reported by validate.
    required=required_bid_count(case)
    if required is None:
        if len(distinct)<3:issues.append('Confirm the required bid count: the amount is unresolved, exactly $2,500, or crosses $2,500 depending on the amount basis.')
    elif len(distinct)<required:
        issues.append(f'Include {required} distinct reviewed bid(s) showing debris quantity ({len(distinct)} of {required} ready).')
    return issues

NAVY = (0.09, .17, .26)
def new_page(doc, title, subtitle=''):
    page = doc.new_page(width=612, height=792)
    page.insert_text((32,32),title,fontsize=13,fontname='hebo',color=NAVY)
    if subtitle: page.insert_textbox(fitz.Rect(32,40,580,69), subtitle, fontsize=9, color=(.35,.4,.46))
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
            else: page.insert_textbox(rectangle+fitz.Rect(10,10,-10,-10),'Evidence Not Attached',fontsize=10,color=(.6,.3,.1))

def template_cell(page, rectangle, label, path=None, note=None):
    """Approved-package geometry, preserving the complete source photograph."""
    page.draw_rect(rectangle,color=(.35,.35,.35),width=.5)
    heading=fitz.Rect(rectangle.x0+4,rectangle.y0+1,rectangle.x1-4,rectangle.y0+19)
    page.insert_textbox(heading,label,fontsize=9,align=1)
    image_rect=fitz.Rect(rectangle.x0+15,rectangle.y0+19,rectangle.x1-15,rectangle.y1-12)
    if path and Path(path).is_file():insert_picture(page,image_rect,path)
    else:
        y=(rectangle.y0+rectangle.y1)/2
        page.insert_textbox(fitz.Rect(rectangle.x0+10,y,rectangle.x1-10,y+30),note or 'Evidence Not Attached',fontsize=9,align=1)

def template_load_pages(doc, load, number):
    """Two template tables followed by a readable full-page dump receipt."""
    photos=load.get('photos',{});calculator,_=screenshot_status(load)
    first=doc.new_page(width=612,height=792)
    first.insert_text((75,63),f'LOAD {number}',fontsize=10)
    for index,(label,path) in enumerate([
        ('Cubic Yard Calculation',calculator),('Final Height',photos.get('height')),
        ('Width',photos.get('width')),('Length',photos.get('length')),
        ('Empty Container',photos.get('empty')),('1/4 Full',photos.get('quarter'))]):
        row,col=divmod(index,2)
        template_cell(first,fitz.Rect(72+col*234,72+row*210,306+col*234,282+row*210),label,path)
    second=doc.new_page(width=612,height=792)
    for index,(label,key) in enumerate([('1/2 Full','half'),('3/4 Full','three_quarters'),('Full Container','full_1'),('Full Container','full_2')]):
        row,col=divmod(index,2)
        template_cell(second,fitz.Rect(72+col*234,72+row*205,306+col*234,277+row*205),label,photos.get(key))
    receipt=photos.get('receipt')
    template_cell(second,fitz.Rect(72,482,540,707),'Dump Receipt',note='See Following Page' if receipt and Path(receipt).is_file() else None)
    if receipt and Path(receipt).is_file():
        page=doc.new_page(width=612,height=792)
        insert_picture(page,fitz.Rect(72,72,540,720),receipt)

def property_photo_pages(doc, paths, title):
    """Nine photographs per page, matching the approved property-photo grid."""
    for start in range(0,len(paths),9):
        page=doc.new_page(width=612,height=792)
        page.insert_text((27,28),title,fontsize=10,fontname='hebo')
        for index,path in enumerate(paths[start:start+9]):
            row,col=divmod(index,3)
            rectangle=fitz.Rect(27+col*189,36+row*243,207+col*189,270+row*243)
            if path and Path(path).is_file():insert_picture(page,rectangle,path)
            else:page.insert_textbox(rectangle,'Evidence Not Attached',fontsize=9)

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
            if not any(x['section']==ROLES['invoice'] for x in manifest):
                page=new_page(doc,'Final Invoice Missing');page.insert_text((32,100),'INCOMPLETE DRAFT - Attach and review the final invoice.',fontsize=11)
            for i,load in enumerate(case['loads'],1):
                start=len(doc)+1
                template_load_pages(doc,load,i)
                additional=[('Unloading / Disposal',load.get('disposal_photo')),('First 10 CYD Evidence',load.get('evidence_first_10_cyd'))]
                if load.get('include_supporting_measurements',False):
                    additional.extend((f'Additional Measurement {j}',p) for j,p in enumerate(load.get('extra_measurement_photos',[]),1))
                additional=[item for item in additional if item[1]]
                if additional: picture_pages(doc,additional,f'Load {i} - Supporting Evidence')
                manifest.append(dict(section=f'Load {i}',start_page=start,end_page=len(doc)))
            for key,title in [('before_photos','Before Photos'),('during_photos','During Photos'),('after_photos','After Photos')]:
                paths=case.get(key,[])
                if paths:
                    start=len(doc)+1;property_photo_pages(doc,paths,title)
                    manifest.append(dict(section=title,start_page=start,end_page=len(doc)))
            # Internal checks are saved separately, never printed in the package.
            if not errors:
                (temp/'COR_Request_Description.txt').write_text(description(case),encoding='utf-8')
            report=dict(status='Items Missing' if errors else 'Complete',issues=errors,pages=len(doc),sections=manifest)
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
