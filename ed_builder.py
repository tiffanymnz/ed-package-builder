"""ED Package Builder Stage 1: local manifest-driven template assembler.
Run: python ed_builder.py --example to create a manifest, then python ed_builder.py case.json
"""
import os,sys,json,copy,argparse,io,math
from pathlib import Path
from docx import Document
from docx.shared import Inches,Pt
from docx.oxml import OxmlElement
from PIL import Image,ImageDraw,ImageFont

SLOTS1 = ['calculator','height','width','length','empty','quarter']
SLOTS2 = ['half','three_quarters','full_1','full_2','receipt']
ALL = SLOTS1+SLOTS2
HERE=Path(getattr(__import__('sys'), '_MEIPASS', Path(__file__).resolve().parent))
TEMPLATE=HERE/'Debris Progression template.docx'

def make_example(path):
    obj={'case_number':'093-EXAMPLE','address':'Enter property address','vendor':'Enter vendor',
         'rate_per_cyd':35,'deduct_first_10_cyd':True,
         'loads':[{'name':f'Load {i}','length_ft':12,'width_ft':6,'side_height_ft':5,
                   'overage_height_ft':0, 'overage_cyd':0, 'overage_note':'',
                   'measured_load_cyd':None,
                   'photos':{k:'' for k in ALL if k!='calculator'},
                   'extra_measurement_photos':[], 'disposal_photo':'',
                   'evidence_first_10_cyd':''} for i in range(1,4)],
         'financial_pdfs':[], 'before_photos':[], 'during_photos':[], 'after_photos':[]}
    Path(path).write_text(json.dumps(obj,indent=2));return obj

def numeric(x,name,minimum=0):
    try: n=float(x)
    except (ValueError,TypeError):raise ValueError(f'{name} is not a number: {x}')
    if not math.isfinite(n) or n<minimum:raise ValueError(f'{name} must be >= {minimum}')
    return n

def volume(load):
    L=numeric(load.get('length_ft'),'length_ft',.01);W=numeric(load.get('width_ft'),'width_ft',.01)
    H=numeric(load.get('side_height_ft'),'side_height_ft',.01)
    over=numeric(load.get('overage_height_ft',0),'overage_height_ft')
    explicit=numeric(load.get('overage_cyd',0),'overage_cyd')
    if over>0 and explicit>0:raise ValueError('Enter either uniform overage height OR separately measured overage CYD, not both')
    # Uniform height only where vendor states overage spans whole footprint.
    return {'container':L*W*H/27,'overage':(L*W*over/27 if over else explicit),
            'total':L*W*(H+over)/27+explicit,'length':L,'width':W,'height':H,'over_height':over}

def image_file(p):
    p=Path(p)
    if not p.is_file():return None
    if p.suffix.lower()=='.pdf':
        import fitz
        d=fitz.open(str(p));page=d[0];pix=page.get_pixmap(matrix=fitz.Matrix(1.7,1.7));raw=pix.tobytes('png');d.close()
        return io.BytesIO(raw)
    if p.suffix.lower() in ('.jpg','.jpeg','.png','.bmp','.webp','.tif','.tiff'):return str(p)
    return None

def calc_image(vol,out):
    """Auditable calculator-style display; NOT a screenshot from CalculatorSoup."""
    im=Image.new('RGB',(1200,520),'white');d=ImageDraw.Draw(im)
    try: font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf';a=ImageFont.truetype(font,32);b=ImageFont.truetype(font,25);c=ImageFont.truetype(font,42)
    except: a=b=c=ImageFont.load_default()
    d.rectangle((2,2,1197,516),outline='#999999',width=3)
    d.rectangle((3,3,1196,80),fill='#ac3129')
    d.text((30,24),'Cubic Yards Calculation',font=a,fill='white')
    d.text((28,115),f"Length: {vol['length']:g} ft     Width: {vol['width']:g} ft     Height: {vol['height']:g} ft",font=b,fill='#222')
    d.text((28,174),f"Container capacity: {vol['container']:.2f} CYD",font=b,fill='#222')
    if vol['overage']:
        d.text((28,225),f"Documented overage: {vol['overage']:.2f} CYD",font=b,fill='#222')
        d.text((28,283),'Uniform overage height applies only if supported by measurements.',font=b,fill='#a12e22')
    d.line((25,358,1170,358),fill='#ddd',width=3)
    d.text((28,380),f"Calculated measured volume: {vol['total']:.2f} CYD",font=c,fill='#222')
        d.text((28,485),'Generated calculation record — NOT a CalculatorSoup website screenshot',font=b,fill='#555')
    im.save(out)

def remove_pictures(cell):
    # Remove images and preserve title paragraphs / table formatting.
    for p in cell.paragraphs:
        for r in list(p.runs):
            if r._r.xpath('.//*[local-name()="blip" or local-name()="imagedata"]'):
                p._p.remove(r._r)

def put_picture(cell,path,maxw=3.0,maxh=2.25):
    if not path:return
    src=image_file(path)
    if src is None:return
    with Image.open(src) as image:
        w,h=image.size
    scale=min(maxw/w,maxh/h)
    width=Inches(w*scale)
    p=cell.paragraphs[-1] if cell.paragraphs else cell.add_paragraph()
    p.alignment=1
    r=p.add_run()
    try:r.add_picture(src,width=width)
    except Exception as e:raise ValueError(f'Could not embed {path}: {e}')

def add_pagebreak(doc):
    p=doc.add_paragraph();p.add_run().add_break(__import__("docx").enum.text.WD_BREAK.PAGE)

def clean_template(doc):
    for t in list(doc.tables)[2:]:t._element.getparent().remove(t._element)
    for para in list(doc.paragraphs):para._element.getparent().remove(para._element)
    second=doc.tables[1]
    for row in list(second.rows)[3:]:second._tbl.remove(row._tr)
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:remove_pictures(cell)
    return doc

def build(data,dest):
    from docx.table import Table
    if not TEMPLATE.exists():raise FileNotFoundError(f'Missing original template: {TEMPLATE}')
    doc=clean_template(Document(TEMPLATE))
    base=[copy.deepcopy(x._element) for x in doc.tables]
    # Remove tables from document: rebuilt from the original formatting per load.
    for tab in list(doc.tables):tab._element.getparent().remove(tab._element)
    body=doc._element.body
    loads=data.get('loads',[])
    if not loads:raise ValueError('At least one load is required')
    output=Path(dest);output.parent.mkdir(parents=True,exist_ok=True)
    calc_dir=output.parent/'calculation_records';calc_dir.mkdir(exist_ok=True)
    errors=[]; totals=[]; manifest=[]
    for i,load in enumerate(loads,1):
        v=volume(load);totals.append(v['total']); photos=load.get('photos',{})
        if i>1:add_pagebreak(doc)
        new=[]
        for xml in base:
            body.insert(len(body)-1,copy.deepcopy(xml))
            new.append(Table(body[-2],doc._body))
        t1,t2=new
        cells={
            'calculator':t1.cell(0,0),'height':t1.cell(0,1),'width':t1.cell(1,0),
            'length':t1.cell(1,1),'empty':t1.cell(2,0),'quarter':t1.cell(2,1),
            'half':t2.cell(0,0),'three_quarters':t2.cell(0,1),
            'full_1':t2.cell(1,0),'full_2':t2.cell(1,1),'receipt':t2.cell(2,0)}
        calcpath=calc_dir/f'load_{i}_calculation.png';calc_image(v,calcpath)
        put_picture(cells['calculator'],str(calcpath),2.9,2.1)
        missing=[]
        for key in ALL:
            if key=='calculator':continue
            p=photos.get(key,'')
            if not p or not Path(p).is_file():missing.append(key)
            else:put_picture(cells[key],p)
        # Merge receipt heading across the two receipt table cells was already part of template.
        extra=load.get('extra_measurement_photos',[])
        if len(extra)<3:errors.append(f'Load {i}: only {len(extra)+3} measurement photos listed (guide requests 6; the template displays 3)')
        if not load.get('disposal_photo'):errors.append(f'Load {i}: disposal/unloading image not listed')
        if missing:errors.append(f'Load {i}: missing image slots: '+', '.join(missing))
        if (v['overage']>0 and not load.get('overage_note')):errors.append(f'Load {i}: overage included but description/proof absent')
        if v['overage']>0:errors.append(f'Load {i}: verify overage geometry and supporting measurements before COR approval')
        recorded=load.get('measured_load_cyd')
        if recorded not in (None,'') and abs(numeric(recorded,'measured_load_cyd')-v['total'])>.05:
            errors.append(f'Load {i}: vendor claims {float(recorded):.2f} CYD, calculated {v["total"]:.2f} CYD')
        if not load.get('evidence_first_10_cyd') and i==1:errors.append('First 10 CYD supporting evidence not linked; confirm separately')
        manifest.append({'load':i,'container_cyd':round(v['container'],2),'overage_cyd':round(v['overage'],2),'total_cyd':round(v['total'],2),'missing_slots':missing,'photos':photos})
    # Append property photos without changing per-load two page layout.
    for name,label in [('before_photos','BEFORE PHOTOS'),('during_photos','DURING PHOTOS'),('after_photos','AFTER PHOTOS')]:
        imgs=[p for p in data.get(name,[]) if image_file(p)]
        if imgs:
            add_pagebreak(doc);doc.add_heading(label,level=1)
            table=doc.add_table(rows=0,cols=3)
            for k in range(0,len(imgs),3):
                cells=table.add_row().cells
                for c,p in zip(cells,imgs[k:k+3]):put_picture(c,p,maxw=1.9,maxh=2.1)
    doc.save(str(output))
    sumcyd=sum(totals)
    raw=data.get('verified_first_10_amount','')
    ded=(float(raw) if str(raw).strip() else None)
    if data.get('first_10_prior_work')=='yes':ded=0.0
    rate=numeric(data.get('rate_per_cyd',0),'rate_per_cyd')
    summary={'case':data.get('case_number'),'address':data.get('address'),'loads':manifest,
             'total_cyd':round(sumcyd,2),'first_10_cyd_confirmed_deduction_usd':(round(ded,2) if ded is not None else None),
             'invoice_quantity_cyd':data.get('invoice_quantity_cyd'),'billable_cyd':None,'rate_per_cyd':rate,
             'estimated_billable_amount':(round(sumcyd*rate-ded,2) if ded is not None else None),
             'warnings':errors,'note':'Volumes are calculated from entered measurements; photo-stage assignments are manual and NOT AI-verified.'}
    output.with_suffix('.review.json').write_text(json.dumps(summary,indent=2))
    output.with_suffix('.review.txt').write_text('\n'.join([f"Case: {data.get('case_number')}",f'Total CYD: {sumcyd:.2f}',f'Gross measured CYD: {sumcyd:.2f}',f'Confirmed first-10 allowance deduction: {ded if ded is not None else "UNVERIFIED"}',f'Estimated net: {(sumcyd*rate-ded) if ded is not None else "UNVERIFIED"}','', 'REVIEW WARNINGS:']+(['- '+x for x in errors] or ['None detected; human photo/receipt validation still required.'])))
    return summary

def main():
    ap=argparse.ArgumentParser(description='Build ED progression using original Word template')
    ap.add_argument('manifest',nargs='?',help='Path to case.json');ap.add_argument('--example',action='store_true')
    ap.add_argument('--output',default='ED_Progression.docx');a=ap.parse_args()
    if a.example:
        p=HERE/'case_example.json';make_example(p);print(f'Example created: {p}');return
    if not a.manifest:ap.print_help();return
    data=json.loads(Path(a.manifest).read_text());path=Path(a.output).absolute();s=build(data,path)
    print('Created',path);print('Calculated',s['total_cyd'],'CYD; issues:',len(s['warnings']))
    # PDF conversion optional; no hard dependency on LibreOffice.
    import shutil,subprocess
    if shutil.which('libreoffice'):
        subprocess.run(['libreoffice','-env:UserInstallation=file:///tmp/ed_lo_profile','--headless','--convert-to','pdf','--outdir',str(path.parent),str(path)],capture_output=True,timeout=60)
        pdf=path.with_suffix('.pdf')
        if pdf.is_file():
            try:
                import fitz
                merged=fitz.open()
                for f in data.get('financial_pdfs',[]):
                    if Path(f).is_file() and Path(f).suffix.lower()=='.pdf':
                        source=fitz.open(f); merged.insert_pdf(source); source.close()
                source=fitz.open(str(pdf)); merged.insert_pdf(source);source.close()
                destination=path.parent/(path.stem+'_COR_Package.pdf')
                merged.save(str(destination),garbage=3,deflate=True);merged.close()
                print('Assembled COR package PDF:',destination)
            except Exception as e:print('Package PDF merge failed:',e)
if __name__=='__main__':main()
