"""Offline visual evidence review: image features, similar-photo neighbors, and paged thumbnail viewer.
Never auto-verifies load identity, fullness, or receipt.
"""
from pathlib import Path
import math, json
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageOps, ImageStat

EXT={'.jpg','.jpeg','.png','.tiff','.tif','.webp','.bmp'}

def feature(path):
    try:
        with Image.open(path) as raw:
            im=ImageOps.exif_transpose(raw).convert('RGB')
            w,h=im.size
            small=im.resize((32,32))
            # low-resolution RGB histogram captures photo composition without relying on filenames
            hist=small.histogram()
            buckets=[]
            for channel in range(3):
                part=hist[channel*256:(channel+1)*256]
                buckets += [sum(part[i:i+32])/1024 for i in range(0,256,32)]
            greys=small.convert('L').resize((9,8))
            pix=list(greys.getdata());bits=0
            for y in range(8):
                for x in range(8):
                    bits=(bits<<1)|(pix[y*9+x]>pix[y*9+x+1])
            stat=ImageStat.Stat(small)
            return dict(path=str(path),width=w,height=h,aspect=round(w/h,3),brightness=round(sum(stat.mean)/3,1),hist=buckets,dhash=bits)
    except Exception:return None

def distance(a,b):
    # Similarity suggestion, not a duplicate finding or proof of a shared load.
    h=sum((x-y)**2 for x,y in zip(a['hist'],b['hist']))**.5
    p=(a['dhash']^b['dhash']).bit_count()/64
    aspect=abs(math.log(max(.01,a['aspect'])/max(.01,b['aspect'])))
    return h+2.0*p+.4*aspect

def gallery(root,records,assign_callback=None,page_size=48):
    records=[r for r in records if Path(r['path']).suffix.lower() in EXT and Path(r['path']).is_file()]
    win=tk.Toplevel(root);win.title('Visual Evidence Gallery — Suggestions only');win.geometry('1190x790')
    ttk.Label(win,text='Visual Photo Gallery',font=('Segoe UI',16,'bold')).pack(anchor='w',padx=15,pady=(12,2))
    ttk.Label(win,text='Browse image thumbnails, view originals and find similar-looking photos. Similarity does not prove same load or progression stage.',wraplength=1100).pack(anchor='w',padx=15)
    state={'page':0,'features':{},'sort':'original','selected':None,'results':records,'imgs':[]}
    controls=ttk.Frame(win,padding=10);controls.pack(fill='x')
    counter=ttk.Label(controls,text='');counter.pack(side='left',padx=8)
    container=ttk.Frame(win);container.pack(fill='both',expand=True,padx=12,pady=5)
    canvas=tk.Canvas(container,highlightthickness=0);sb=ttk.Scrollbar(container,orient='vertical',command=canvas.yview)
    canvas.configure(yscrollcommand=sb.set);canvas.pack(side='left',fill='both',expand=True);sb.pack(side='right',fill='y')
    frame=ttk.Frame(canvas);canvas.create_window((0,0),window=frame,anchor='nw')
    frame.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
    def details(r):
        state['selected']=r
        d=tk.Toplevel(win);d.title(Path(r['path']).name);d.geometry('780x680')
        title=ttk.Label(d,text=r.get('name',Path(r['path']).name),wraplength=740,font=('Segoe UI',11,'bold'));title.pack(padx=10,pady=7)
        try:
            with Image.open(r['path']) as source:
                im=ImageOps.exif_transpose(source).convert('RGB');im.thumbnail((745,540));tkim=ImageTk.PhotoImage(im)
            label=ttk.Label(d,image=tkim);label.image=tkim;label.pack(pady=5)
        except Exception as ex:ttk.Label(d,text=f'Preview failed: {ex}').pack()
        buttons=ttk.Frame(d);buttons.pack(pady=7)
        def similar():
            base=state['features'].get(r['path'])
            if base is None:
                base=feature(r['path']);state['features'][r['path']]=base
            if not base:return
            scored=[]
            for rec in records:
                if rec['path']==r['path']:continue
                f=state['features'].get(rec['path'])
                if f is None:f=feature(rec['path']);state['features'][rec['path']]=f
                if f:scored.append((distance(base,f),rec))
            scored.sort(key=lambda x:x[0]);state['results']=[r]+[rec for _,rec in scored[:95]];state['page']=0;state['sort']='similar';render();d.destroy()
        ttk.Button(buttons,text='Find visually similar photos',command=similar).pack(side='left',padx=5)
        if assign_callback:ttk.Button(buttons,text='Select for load / slot assignment',command=lambda:(assign_callback(r),d.destroy())).pack(side='left',padx=5)
    def render():
        for widget in frame.winfo_children():widget.destroy()
        state['imgs']=[]
        pages=max(1,math.ceil(len(state['results'])/page_size))
        state['page']=max(0,min(state['page'],pages-1));start=state['page']*page_size
        subset=state['results'][start:start+page_size]
        counter.configure(text=f'{len(records):,} imported images  |  {state["sort"]} view  |  Page {state["page"]+1} / {pages}')
        for i,r in enumerate(subset):
            cell=ttk.Frame(frame,padding=5);cell.grid(row=i//6,column=i%6,sticky='n',padx=2,pady=4)
            try:
                with Image.open(r['path']) as source:
                    im=ImageOps.exif_transpose(source).convert('RGB');im.thumbnail((155,122));thumb=ImageTk.PhotoImage(im)
                state['imgs'].append(thumb)
                tk.Button(cell,image=thumb,command=lambda rr=r:details(rr),relief='flat',cursor='hand2').pack()
            except Exception:ttk.Button(cell,text='Cannot preview',command=lambda rr=r:details(rr)).pack()
            ttk.Label(cell,text=r.get('name',Path(r['path']).name)[:26],width=26,anchor='center').pack()
    def prev():state['page']-=1;render()
    def nxt():state['page']+=1;render()
    def reset():state['results']=records;state['sort']='original';state['page']=0;render()
    ttk.Button(controls,text='Previous page',command=prev).pack(side='right',padx=5)
    ttk.Button(controls,text='Next page',command=nxt).pack(side='right',padx=5)
    ttk.Button(controls,text='Show all',command=reset).pack(side='right',padx=5)
    render();return win
