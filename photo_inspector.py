"""In-app inspection without losing the parent review selection or position."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageOps, ImageTk

class PhotoPane(ttk.Frame):
    MAX_PIXELS = 24_000_000
    def __init__(self, parent, path):
        super().__init__(parent)
        self.source = None; self.preview = None; self.scale = 1.; self.rotation = 0; self.fit_mode = True; self.fit_job = None
        ttk.Label(self, text=Path(path).name, wraplength=480).pack(fill='x', pady=5)
        controls=ttk.Frame(self); controls.pack(fill='x')
        for label, action in [('Fit', self.fit), ('-', lambda:self.zoom(.8)), ('+', lambda:self.zoom(1.25)), ('Rotate', self.rotate), ('Tape Detail', self.tape_detail)]:
            ttk.Button(controls,text=label,command=action,width=11 if label=='Tape Detail' else 7).pack(side='left',padx=2)
        self.detail=ttk.Label(controls,text='Drag to pan');self.detail.pack(side='left',padx=8)
        box=ttk.Frame(self);box.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(box,background='#202a35',highlightthickness=0)
        sx=ttk.Scrollbar(box,orient='horizontal',command=self.canvas.xview)
        sy=ttk.Scrollbar(box,command=self.canvas.yview)
        sy.pack(side='right',fill='y');sx.pack(side='bottom',fill='x');self.canvas.pack(fill='both',expand=True)
        self.canvas.configure(xscrollcommand=sx.set,yscrollcommand=sy.set)
        self.canvas.bind('<Configure>',self.resized)
        self.bind('<Destroy>',self.cleanup,add='+')
        self.canvas.bind('<ButtonPress-1>',lambda e:self.canvas.scan_mark(e.x,e.y))
        self.canvas.bind('<B1-Motion>',lambda e:self.canvas.scan_dragto(e.x,e.y,gain=1))
        self.canvas.bind('<MouseWheel>',lambda e:self.zoom(1.25 if e.delta>0 else .8))
        self.canvas.bind('<Button-4>',lambda e:self.zoom(1.25));self.canvas.bind('<Button-5>',lambda e:self.zoom(.8))
        try:
            with Image.open(path) as image:
                image=ImageOps.exif_transpose(image).convert('RGB')
                if image.width*image.height>self.MAX_PIXELS:
                    image.thumbnail((4800,4800))
                self.source=image.copy()
            self.after_idle(self.fit)
        except Exception as exc:self.canvas.create_text(20,25,anchor='nw',fill='white',text='Cannot preview this photo:\n'+str(exc),width=350)
    def cleanup(self,event):
        if event.widget is self and self.fit_job:
            self.after_cancel(self.fit_job);self.fit_job=None
    def resized(self,event):
        if self.fit_mode:
            if self.fit_job:self.after_cancel(self.fit_job)
            self.fit_job=self.after(60,self.fit)
    def image(self):return self.source.rotate(self.rotation,expand=True) if self.rotation else self.source
    def fit(self):
        if self.source is None:return
        self.fit_job=None;self.fit_mode=True
        self.update_idletasks();im=self.image()
        self.scale=min(max(100,self.canvas.winfo_width()-20)/im.width,max(100,self.canvas.winfo_height()-20)/im.height,1)
        self.render();self.canvas.xview_moveto(0);self.canvas.yview_moveto(0)
    def zoom(self,factor):
        if self.source is None:return
        self.fit_mode=False
        im=self.image();new=max(.03,min(self.scale*factor,8,6000/max(im.size)))
        x=self.canvas.xview();y=self.canvas.yview();self.scale=new;self.render()
        self.canvas.xview_moveto(x[0]);self.canvas.yview_moveto(y[0])
    def rotate(self):
        if self.source is not None:self.rotation=(self.rotation+90)%360;self.fit()
    def tape_detail(self):
        if self.source is None:return
        try:
            import cv2,numpy as np
            im=self.image().copy();im.thumbnail((800,800));pixels=np.asarray(im)
            hsv=cv2.cvtColor(pixels,cv2.COLOR_RGB2HSV);mask=cv2.inRange(hsv,(15,65,85),(42,255,255))
            contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            boxes=[cv2.boundingRect(c) for c in contours]
            boxes=[b for b in boxes if max(b[2:])/max(1,min(b[2:]))>4 and max(b[2:])>min(im.size)*.2]
            if boxes:
                x,y,w,h=max(boxes,key=lambda b:b[2]*b[3]);original=self.image();factor=original.width/im.width
                region_w=max(w*factor*1.4,original.width*.12);region_h=max(h*factor*1.4,original.height*.12)
                self.fit_mode=False;self.scale=min(self.canvas.winfo_width()/region_w,self.canvas.winfo_height()/region_h,4,6000/max(original.size));self.render()
                self.canvas.xview_moveto(max(0,(x+w/2)*factor/original.width-self.canvas.winfo_width()/(2*original.width*self.scale)))
                self.canvas.yview_moveto(max(0,(y+h/2)*factor/original.height-self.canvas.winfo_height()/(2*original.height*self.scale)))
                self.detail.configure(text='Possible Tape Region · Check Both Endpoints');return
        except (ImportError,ValueError,OSError):pass
        self.zoom(2);self.detail.configure(text='Locate the Tape · Check Both Endpoints')
    def render(self):
        im=self.image();size=(max(1,round(im.width*self.scale)),max(1,round(im.height*self.scale)))
        self.preview=ImageTk.PhotoImage(im.resize(size,Image.Resampling.LANCZOS))
        self.canvas.delete('all');self.canvas.create_image(0,0,anchor='nw',image=self.preview)
        self.canvas.configure(scrollregion=(0,0,*size));self.detail.configure(text=f'{self.scale:.0%} · Drag to Pan')

def inspect_photos(parent,paths,title='Inspect Photos'):
    paths=list(dict.fromkeys(str(p) for p in paths if p))
    if not paths:return None
    win=tk.Toplevel(parent);win.configure(background=parent.cget('background') if 'background' in parent.keys() else '#f2f5f8');win.title(title);win.geometry(f'{max(700,min(1180,parent.winfo_screenwidth()-40))}x{max(500,min(800,parent.winfo_screenheight()-60))}');win.minsize(700,500);win.transient(parent)
    ttk.Label(win,text='Inspect the load, tape endpoints and readability. Zoom and rotation affect this preview only.',wraplength=1100).pack(anchor='w',padx=16,pady=12)
    content=ttk.Panedwindow(win,orient='horizontal');content.pack(fill='both',expand=True,padx=12,pady=(0,12))
    for path in paths[:2]:content.add(PhotoPane(content,path),weight=1)
    win.bind('<Escape>',lambda e:win.destroy())
    return win
