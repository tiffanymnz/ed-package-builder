"""Guided desktop workspace. Existing case manifests and validation are preserved."""
import os
import re
import subprocess
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from ed_app import App, BASE, IMAGE_EXT, PHASES, default_load, make_case, safe, as_number
from ed_builder import volume
from calculator_evidence import URL, screenshot_status, measurement_signature, file_digest

BG = '#f2f5f8'
INK = '#172b43'
MUTED = '#61738a'
ACCENT = '#087f8c'
SLOT_LABELS = {
    'height': 'Height measurement', 'width': 'Width measurement', 'length': 'Length measurement',
    'empty': 'Empty container', 'quarter': 'Quarter full', 'half': 'Half full',
    'three_quarters': 'Three quarters full', 'full_1': 'Full container · view 1',
    'full_2': 'Full container · view 2', 'receipt': 'Dump receipt',
    'disposal_photo': 'Unloading / disposal', 'first_10_proof': 'First 10 CYD evidence',
    'measurement_extra_1': 'Supporting Measurement 1 (Optional)',
    'measurement_extra_2': 'Supporting Measurement 2 (Optional)',
    'measurement_extra_3': 'Supporting Measurement 3 (Optional)',
    'before_photos': 'Property · before work', 'during_photos': 'Property · during work',
    'after_photos': 'Property · after work', 'financial_pdfs': 'Invoice / financial PDF',
}
STEPS = [('Case & loads', 'Property details and measurements'),
         ('Photos & files', 'Connect evidence to each load'),
         ('Invoice', 'Check the invoice and calculated first-10-CYD deduction'),
         ('Review & Export', 'Resolve issues and create a draft')]

class GuidedApp(App):
    def __init__(self, root):
        self.root = root
        root.title('ED Package Builder')
        root.geometry('1180x800')
        root.minsize(900, 640)
        root.configure(bg=BG)
        from tkinter import font as tkfont
        available = {name.lower(): name for name in tkfont.families(root)}
        self.ui_font = next((available[name] for name in ('segoe ui', 'dejavu sans', 'liberation sans', 'arial', 'helvetica') if name in available), 'sans')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=(self.ui_font, 10), background=BG, foreground=INK)
        style.configure('TFrame', background=BG)
        style.configure('Card.TFrame', background='white')
        style.configure('TLabel', background=BG)
        style.configure('Card.TLabel', background='white')
        style.configure('Muted.TLabel', foreground=MUTED)
        style.configure('Heading.TLabel', font=(self.ui_font, 23, 'bold'))
        style.configure('Section.TLabel', font=(self.ui_font, 12, 'bold'), background='white')
        style.configure('TButton', padding=(13, 9), background='white', borderwidth=0)
        style.map('TButton', background=[('active', '#e2edf0')])
        style.configure('Primary.TButton', background=ACCENT, foreground='white', font=(self.ui_font, 10, 'bold'))
        style.map('Primary.TButton', background=[('active', '#096775'), ('disabled', '#a4bfc5')], foreground=[('disabled', '#f0f5f6')])
        style.configure('TEntry', padding=8, fieldbackground='white')
        style.configure('TCombobox', padding=7, fieldbackground='white')
        style.configure('Treeview', background='white', fieldbackground='white', rowheight=34, borderwidth=0)
        style.configure('Treeview.Heading', font=(self.ui_font, 10, 'bold'), padding=8)
        style.map('Treeview', background=[('selected', '#d7eef0')], foreground=[('selected', INK)])
        style.layout('Pages.TNotebook.Tab', [])
        style.configure('Pages.TNotebook', borderwidth=0, background=BG, tabmargins=0)
        self.case = None
        self.case_dir = None
        self.selected_photo = None
        self.photos = []
        self.thumb_cache = {}
        self.vars = {}
        self.status = tk.StringVar(value='Your files stay on this computer.')
        self.case_caption = tk.StringVar(value='No case open')
        self.page_title = tk.StringVar(value=STEPS[0][0])
        self.page_help = tk.StringVar(value=STEPS[0][1])
        self.step_buttons = []
        side = tk.Frame(root, bg=INK, width=205)
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        tk.Label(side, text='ED Package\nBuilder', bg=INK, fg='white', font=(self.ui_font, 17, 'bold'), justify='left').pack(anchor='w', padx=22, pady=(30, 8))
        tk.Label(side, text='CASE FILES', bg=INK, fg='#8da7c1', font=(self.ui_font, 9)).pack(anchor='w', padx=22, pady=(0, 30))
        for i, (title, _) in enumerate(STEPS):
            button = tk.Button(side, text=f'{i+1}    {title}', command=lambda j=i: self.go(j),
                               bg=INK, fg='#d3deeb', activebackground='#25435e', activeforeground='white',
                               bd=0, highlightthickness=0, anchor='w', padx=19, pady=16, font=(self.ui_font, 11), cursor='hand2', wraplength=180)
            button.pack(fill='x', padx=8, pady=3)
            self.step_buttons.append(button)
        tk.Label(side, text='Files are saved locally.', bg=INK, fg='#9db0c5',
                 justify='left', font=(self.ui_font, 9), wraplength=165).pack(side='bottom', padx=20, pady=24)
        workspace = ttk.Frame(root)
        workspace.pack(side='left', fill='both', expand=True)
        header = ttk.Frame(workspace, padding=(24, 15))
        header.pack(fill='x')
        ttk.Label(header, textvariable=self.case_caption, font=(self.ui_font, 11, 'bold')).pack(side='left')
        menu_button = ttk.Menubutton(header, text='Tools')
        menu_button.pack(side='right', padx=(8, 0))
        tools = tk.Menu(menu_button, tearoff=False)
        menu_button.configure(menu=tools)
        for label, fn in [('Photo gallery', self.visual_gallery), ('Photo suggestions', self.visual_triage),
                          ('Timeline review', self.timeline_review), ('Find similar photos', self.similar_photos),
                          ('Read photo text', self.read_photo_text), ('Local AI review', self.local_ai_review),
                          ('Audit source files', self.audit_evidence), ('Analyze files', self.analyze_files),
                          ('Verify samples', self.verify_samples), ('Suggest sample types', self.suggest_sample_types),
                          ('Build transmittal PDF', self.transmittal), ('How to use', self.help)]:
            tools.add_command(label=label, command=fn)
        for label, fn in [('Save', self.save), ('Open', self.open_case), ('New Case', self.new_case)]:
            ttk.Button(header, text=label, command=fn).pack(side='right', padx=4)
        heading = ttk.Frame(workspace, padding=(24, 6))
        heading.pack(fill='x')
        ttk.Label(heading, textvariable=self.page_title, style='Heading.TLabel').pack(anchor='w')
        ttk.Label(heading, textvariable=self.page_help, style='Muted.TLabel', wraplength=600).pack(anchor='w', pady=(5, 10))
        footer = ttk.Frame(workspace, padding=(24, 14))
        footer.pack(side='bottom', fill='x')
        self.back_button = ttk.Button(footer, text='Back', command=lambda: self.go(self.current_step()-1))
        self.back_button.pack(side='left')
        self.next_button = ttk.Button(footer, text='Next: Photos & files', style='Primary.TButton', command=self.next_step)
        self.next_button.pack(side='right')
        ttk.Button(footer, text='Open Output Folder', command=self.open_output).pack(side='right', padx=8)
        ttk.Label(workspace, textvariable=self.status, style='Muted.TLabel', wraplength=700).pack(side='bottom', fill='x', padx=24, pady=(0, 6))
        self.tabs = ttk.Notebook(workspace, style='Pages.TNotebook', takefocus=False)
        self.tabs.pack(fill='both', expand=True, padx=24, pady=(0, 8))
        self.case_tab = ttk.Frame(self.tabs)
        self.evidence_tab = ttk.Frame(self.tabs)
        self.finance_tab = ttk.Frame(self.tabs)
        self.check_tab = ttk.Frame(self.tabs)
        for tab, (name, _) in zip((self.case_tab, self.evidence_tab, self.finance_tab, self.check_tab), STEPS):
            self.tabs.add(tab, text=name)
        self.draw_case(); self.draw_evidence(); self.draw_finance(); self.draw_checks()
        self.tabs.bind('<<NotebookTabChanged>>', lambda event: self.update_guide())
        root.bind('<Control-s>', lambda event: self.save())
        root.bind('<Control-o>', lambda event: self.open_case())
        root.protocol('WM_DELETE_WINDOW', self.close_app)
        self.update_guide()

    def current_step(self):
        return self.tabs.index(self.tabs.select())

    def go(self, index):
        if not 0 <= index < 4: return
        if self.case: self.save()
        self.tabs.select(index)
        self.update_guide()

    def next_step(self):
        if not self.require(): return
        if self.current_step() == 3: self.generate()
        else: self.go(self.current_step()+1)

    def update_guide(self):
        i = self.current_step()
        self.page_title.set(STEPS[i][0]); self.page_help.set(STEPS[i][1])
        for j, button in enumerate(self.step_buttons):
            button.configure(bg=ACCENT if i == j else INK, fg='white' if i == j else '#d3deeb')
        self.back_button.configure(state='disabled' if i == 0 else 'normal')
        self.next_button.configure(text='Generate Word draft' if i == 3 else f'Next: {STEPS[i+1][0]}')
        if self.case:
            self.case_caption.set(f"{str(self.case.get('case_number', 'Case'))[:16]}  ·  {len(self.case['loads'])} {'Load' if len(self.case['loads']) == 1 else 'Loads'}")
            if i == 3: self.show_checks()

    def close_app(self):
        if self.case:
            try: self.save()
            except Exception as exc:
                messagebox.showerror('Could not save', str(exc)); return
        self.root.destroy()

    def save(self):
        super().save()
        if self.case:
            self.status.set(f"Saved locally · {self.case.get('case_number', 'Case')}")

    def refresh(self):
        self.selected_photo = None
        super().refresh()
        self.status.set('Case loaded. Work through the four steps on the left.')

    def open_case(self):
        if self.case: self.save()
        path = filedialog.askopenfilename(title='Open a saved ED case', initialdir=str(BASE), filetypes=[('ED case', 'case.json')])
        if not path: return
        import json
        try:
            case = json.loads(Path(path).read_text(encoding='utf-8'))
            if not isinstance(case.get('loads'), list) or not case['loads']:
                raise ValueError('This file does not contain any loads.')
            self.case = case; self.case_dir = Path(path).parent; self.vars = {}
            self.refresh(); self.go(0)
        except Exception as exc: messagebox.showerror('Could not open case', str(exc))

    def new_case(self):
        if self.case: self.save()
        win = tk.Toplevel(self.root); win.title('Create a case'); win.geometry('520x530')
        win.transient(self.root); win.grab_set(); win.configure(bg=BG)
        body = ttk.Frame(win, padding=24); body.pack(fill='both', expand=True)
        ttk.Label(body, text='Start a new package', font=(self.ui_font, 19, 'bold')).pack(anchor='w', pady=(0, 5))
        ttk.Label(body, text='Use one case for one property and work order.', style='Muted.TLabel').pack(anchor='w', pady=(0, 14))
        entries = {}
        for label, key, default in [('Case number', 'case_number', ''), ('Property address', 'address', ''),
                                     ('Vendor name', 'vendor', ''), ('Number of loads', 'loads', '1'),
                                     ('ED rate per cubic yard ($)', 'rate', '35')]:
            row = ttk.Frame(body); row.pack(fill='x', pady=5)
            ttk.Label(row, text=label, width=26).pack(side='left')
            entry = ttk.Entry(row, width=24); entry.insert(0, default); entry.pack(side='left', fill='x', expand=True)
            entries[key] = entry
        ttk.Label(body, text='The first 10 CYD are deducted at the HUD request rate. Confirm Invoice Treatment in step 3.', wraplength=440, style='Muted.TLabel').pack(anchor='w', pady=18)
        def create():
            try:
                number = entries['case_number'].get().strip()
                if not number or not safe(number): raise ValueError('Enter a case number.')
                count = int(entries['loads'].get())
                if not 1 <= count <= 150: raise ValueError('Load count must be between 1 and 150.')
                rate = float(entries['rate'].get())
                import math
                if not math.isfinite(rate) or rate < 0: raise ValueError('Enter a valid rate.')
                directory = BASE/safe(number)
                if (directory/'case.json').exists(): raise ValueError('This case already exists. Use Open.')
                self.case = make_case(number, entries['address'].get(), entries['vendor'].get(), count, rate)
                self.case['verified_first_10_amount'] = ''
                self.case_dir = directory; self.vars = {}; self.save(); self.refresh(); self.go(0); win.destroy()
            except Exception as exc: messagebox.showerror('Check case details', str(exc), parent=win)
        ttk.Button(body, text='Create case', style='Primary.TButton', command=create).pack(anchor='e', pady=10)
        entries['case_number'].focus_set()

    def clear(self, tab):
        for child in tab.winfo_children(): child.destroy()

    def empty(self, tab):
        self.clear(tab)
        card = self.card(tab, 'Build your first debris package', 'Start with a case. Then add measurements, match photos and review the invoice.')
        ttk.Button(card, text='Create a case', style='Primary.TButton', command=self.new_case).pack(anchor='w', pady=(16, 8))
        ttk.Button(card, text='Open a saved case', command=self.open_case).pack(anchor='w')

    def card(self, parent, title, description=None):
        card = ttk.Frame(parent, style='Card.TFrame', padding=20)
        card.pack(fill='x', pady=(0, 14))
        heading=ttk.Label(card,text=title,style='Section.TLabel',wraplength=610);heading.pack(fill='x')
        heading.bind('<Configure>',lambda e:heading.configure(wraplength=max(180,e.width)))
        if description:
            detail=ttk.Label(card,text=description,style='Card.TLabel',foreground=MUTED,wraplength=610);detail.pack(fill='x',pady=(6,12))
            detail.bind('<Configure>',lambda e:detail.configure(wraplength=max(180,e.width)))
        return card

    def scroll_page(self, tab):
        self.clear(tab)
        canvas = tk.Canvas(tab, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y'); canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        content = ttk.Frame(canvas)
        item = canvas.create_window((0, 0), window=content, anchor='nw')
        content.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))
        # One dispatcher per application, with destroyed pages removed. Rebuilding
        # a page must not leave global callbacks referencing its old widgets.
        pages=getattr(self,'_scroll_pages',None)
        if pages is None:
            self._scroll_pages={};pages=self._scroll_pages
            def wheel(event):
                widget=self.root.winfo_containing(event.x_root,event.y_root)
                while widget is not None:
                    target=self._scroll_pages.get(widget)
                    if target is not None:
                        step=-1 if getattr(event,'num',None)==4 else 1 if getattr(event,'num',None)==5 else int(-event.delta/120) or (-1 if event.delta>0 else 1)
                        target.yview_scroll(step,'units');return 'break'
                    widget=getattr(widget,'master',None)
            for sequence in ('<MouseWheel>','<Button-4>','<Button-5>'):self.root.bind_all(sequence,wheel,add='+')
        pages[content]=canvas;pages[canvas]=canvas
        def forget(event):
            if event.widget==canvas:pages.pop(content,None);pages.pop(canvas,None)
        canvas.bind('<Destroy>',forget,add='+')
        return content

    def field(self, parent, label, key, value, row, column=0, width=25):
        ttk.Label(parent, text=label, style='Card.TLabel').grid(row=row*2, column=column, sticky='w', padx=(0, 16), pady=(8, 4))
        variable = tk.StringVar(value=str(value if value is not None else ''))
        self.vars[key] = variable
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.grid(row=row*2+1, column=column, sticky='ew', padx=(0, 16), pady=(0, 6))
        parent.columnconfigure(column, weight=1)
        return variable

    def draw_case(self):
        if not self.case: self.empty(self.case_tab); return
        content = self.scroll_page(self.case_tab)
        card = self.card(content, 'Property & vendor')
        grid = ttk.Frame(card, style='Card.TFrame'); grid.pack(fill='x')
        for n, (label, key) in enumerate([('Case number', 'case_number'), ('Vendor name', 'vendor'), ('Property address', 'address'), ('Rate per CYD ($)', 'rate_per_cyd')]):
            self.field(grid, label, key, self.case.get(key, ''), n//2, n%2)
        self.load_totals = []
        self.screenshot_labels = []
        for i, load in enumerate(self.case['loads']):
            card = self.card(content, f'Load {i+1}', 'Enter the vendor measurements in feet.')
            grid = ttk.Frame(card, style='Card.TFrame'); grid.pack(fill='x')
            for j, (label, key) in enumerate([('Length (ft)', 'length_ft'), ('Width (ft)', 'width_ft'), ('Wall height (ft)', 'side_height_ft')]):
                self.field(grid, label, f'L:{i}:{key}', load.get(key, ''), 0, j, 12)
            total = ttk.Label(card, text='', style='Card.TLabel', foreground=ACCENT, font=(self.ui_font, 12, 'bold'))
            total.pack(anchor='w', pady=12); self.load_totals.append(total)
            extras = ttk.Frame(card, style='Card.TFrame')
            toggle = ttk.Button(card, text='+ Overage / extra debris above the walls')
            toggle.pack(anchor='w', pady=4)
            def toggle_extra(frame=extras, button=toggle):
                if frame.winfo_manager(): frame.pack_forget(); button.configure(text='+ Overage / extra debris above the walls')
                else: frame.pack(fill='x', pady=8); button.configure(text='− Hide overage fields')
            toggle.configure(command=toggle_extra)
            for j, (label, key) in enumerate([('Uniform extra height (ft)', 'overage_height_ft'), ('Separate overage (CYD)', 'overage_cyd'), ('Evidence / explanation', 'overage_note')]):
                self.field(extras, label, f'L:{i}:{key}', load.get(key, ''), j, 0)
            if as_number(load.get('overage_height_ft')) or as_number(load.get('overage_cyd')): toggle_extra()
            ttk.Separator(card).pack(fill='x', pady=12)
            ttk.Label(card, text='cubic yard calculation', style='Section.TLabel').pack(anchor='w')
            label = ttk.Label(card, text='', style='Card.TLabel', wraplength=600)
            label.pack(anchor='w', pady=8); self.screenshot_labels.append(label)
            row = ttk.Frame(card, style='Card.TFrame'); row.pack(fill='x')
            ttk.Button(row, text='1  Open Cubic Yard Calculation', command=lambda n=i: self.calculator_help(n)).pack(side='left', padx=(0, 8))
            ttk.Button(row, text='2  Attach screenshot', command=lambda n=i: self.attach_calculator(n)).pack(side='left')
        ttk.Button(content, text='+ Add another load', command=self.add_load).pack(anchor='w', pady=(0, 14))
        for key, variable in self.vars.items():
            if key.startswith('L:'): variable.trace_add('write', lambda *args: self.update_measurements())
        self.update_measurements()

    def update_measurements(self):
        if not self.case: return
        self.sync_case()
        for i, load in enumerate(self.case['loads']):
            try:
                result = volume(load)
                self.load_totals[i].configure(text=f"Measured volume  {result['total']:.2f} CYD")
            except Exception: self.load_totals[i].configure(text='Enter length, width and height to calculate volume.')
            _, issue = screenshot_status(load)
            self.screenshot_labels[i].configure(text=issue or 'Attached · manually checked against current measurements', foreground='#a65b12' if issue else ACCENT)

    def calculator_help(self, index):
        self.save()
        try: result = volume(self.case['loads'][index])
        except Exception as exc: messagebox.showwarning('Enter measurements first', str(exc)); return
        instructions = (f"Load {index+1}\n\nSelect Rectangle and set all units to feet.\n"
                        f"Length: {result['length']:g} ft\nWidth: {result['width']:g} ft\n"
                        f"Depth / height: {result['height']*float(self.case['loads'][index].get('fill_fraction',1))+result['over_height']:g} ft\nQuantity: 1\n"
                        f"Container plus uniform overage: {result['total'] if not as_number(self.case['loads'][index].get('overage_cyd')) else result['container']:.2f} CYD\n\n"
                        'Click Calculate. Capture the Cubic Yard Calculation name, inputs, units and answer using Windows + Shift + S. '
                        'Save the screenshot as a PNG, then click Attach screenshot. No property or vendor information is sent by this app.')
        if as_number(self.case['loads'][index].get('overage_cyd')):
            instructions += '\n\nSeparate overage needs its own documented calculation. Include all results in your screenshot; do not change the container height to invent overage geometry.'
        webbrowser.open(URL)
        messagebox.showinfo('Capture the actual Cubic Yard Calculation result', instructions)

    def attach_calculator(self, index):
        self.save(); load = self.case['loads'][index]
        try: result = volume(load)
        except Exception as exc: messagebox.showwarning('Enter measurements first', str(exc)); return
        path = filedialog.askopenfilename(title='Select the actual cubic yard calculation', filetypes=[('Screenshot', '*.png *.jpg *.jpeg')])
        if not path: return
        try:
            with Image.open(path) as image: image.verify()
            win = tk.Toplevel(self.root); win.title(f'Review cubic yard calculation · Load {index+1}')
            win.geometry('780x590'); win.transient(self.root); win.grab_set()
            body = ttk.Frame(win, padding=20); body.pack(fill='both', expand=True)
            ttk.Label(body, text='Check the screenshot before attaching', font=(self.ui_font, 16, 'bold')).pack(anchor='w')
            ttk.Label(body, text=f"Load {index+1}: {result['length']:g} × {result['width']:g} × {result['height']:g} ft · total {result['total']:.2f} CYD", wraplength=700).pack(anchor='w', pady=10)
            image = Image.open(path).convert('RGB'); image.thumbnail((700, 300))
            preview = ImageTk.PhotoImage(image)
            label = ttk.Label(body, image=preview); label.image = preview; label.pack(expand=True)
            checked = tk.BooleanVar(value=False)
            ttk.Checkbutton(body, variable=checked, text='Actual cubic yard calculation; inputs, units and result match this load.').pack(anchor='w', pady=14)
            def attach():
                if not checked.get(): messagebox.showwarning('Review required', 'Check the confirmation after reviewing the image.', parent=win); return
                folder = self.case_dir/'originals'; folder.mkdir(exist_ok=True)
                digest = file_digest(path); target = folder/(digest[:12]+'_Cubic Yard Calculation'+Path(path).suffix.lower())
                import shutil
                if Path(path).resolve() != target.resolve(): shutil.copy2(path, target)
                load['calculator_evidence'] = dict(path=str(target), sha256=digest, source_url=URL,
                    user_confirmed=True, measurement_signature=measurement_signature(load))
                self.save(); self.update_measurements(); win.destroy()
            ttk.Button(body, text='Attach verified screenshot', style='Primary.TButton', command=attach).pack(anchor='e')
        except Exception as exc: messagebox.showerror('Cannot attach screenshot', str(exc))

    def draw_evidence(self):
        if not self.case: self.empty(self.evidence_tab); return
        self.clear(self.evidence_tab)
        imports = ttk.Frame(self.evidence_tab); imports.pack(fill='x', pady=(0, 12))
        ttk.Button(imports, text='Import Folder', style='Primary.TButton', command=self.import_files).pack(side='left')
        ttk.Button(imports, text='Import ZIPs', command=self.import_zips).pack(side='left', padx=8)
        ttk.Label(imports, text='Originals are copied into this case.', style='Muted.TLabel').pack(side='left', padx=8)
        row = ttk.Frame(self.evidence_tab); row.pack(fill='x', pady=(0, 12))
        ttk.Label(row, text='Load').pack(side='left')
        self.e_load = tk.StringVar(value='1')
        chooser = ttk.Combobox(row, textvariable=self.e_load, values=[str(i) for i in range(1, len(self.case['loads'])+1)], width=5, state='readonly')
        chooser.pack(side='left', padx=8); chooser.bind('<<ComboboxSelected>>', lambda event: self.refresh_assignments())
        self.slot = tk.StringVar(value='empty')
        self.slot_display = tk.StringVar(value=SLOT_LABELS['empty'])
        purpose = ttk.Combobox(row, textvariable=self.slot_display, values=list(SLOT_LABELS.values()), width=28, state='readonly')
        purpose.pack(side='left', padx=(0, 8))
        purpose.bind('<<ComboboxSelected>>', lambda event: self.slot.set(next(key for key, value in SLOT_LABELS.items() if value == self.slot_display.get())))
        ttk.Button(row, text='Assign Photo', style='Primary.TButton', command=self.assign).pack(side='left')
        ttk.Button(row, text='Clear', command=self.clear_slot).pack(side='left', padx=6)
        panes = ttk.Panedwindow(self.evidence_tab, orient='horizontal'); panes.pack(fill='both', expand=True)
        left = ttk.Frame(panes, style='Card.TFrame', padding=12)
        right = ttk.Frame(panes, style='Card.TFrame', padding=12)
        panes.add(left, weight=1); panes.add(right, weight=1)
        ttk.Label(left, text='Select an Imported File', style='Section.TLabel').pack(anchor='w', pady=(0, 10))
        listing = ttk.Frame(left); listing.pack(fill='both', expand=True)
        self.filelist = tk.Listbox(listing, width=20, height=4, exportselection=False, bd=0, highlightthickness=0,
                                   bg='white', fg=INK, selectbackground='#d7eef0', selectforeground=INK,
                                   font=(self.ui_font, 10), activestyle='none')
        scroll = ttk.Scrollbar(listing, orient='vertical', command=self.filelist.yview)
        scroll.pack(side='right', fill='y'); self.filelist.pack(side='left', fill='both', expand=True)
        self.filelist.configure(yscrollcommand=scroll.set)
        self.photos = self.case.get('imported_files', [])
        for item in self.photos: self.filelist.insert('end', item['name'])
        self.filelist.bind('<<ListboxSelect>>', self.preview)
        if not self.photos: ttk.Label(left, text='No files yet. Start with Import Folder or Import ZIPs.', style='Card.TLabel', wraplength=260).pack(pady=16)
        ttk.Label(right, text='Preview & Match', style='Section.TLabel').pack(anchor='w')
        self.preview_label = ttk.Label(right, text='Select a File to Preview', style='Card.TLabel', anchor='center')
        self.preview_label.pack(fill='x', pady=8)
        self.selected_label = ttk.Label(right, text='Then choose its purpose above and click Assign Photo.', style='Card.TLabel', wraplength=300)
        self.selected_label.pack(fill='x', pady=5)
        checklist = ttk.Frame(right); checklist.pack(fill='both', expand=True)
        self.assignment_tree = ttk.Treeview(checklist, columns=('status',), show='tree headings', height=5)
        self.assignment_tree.heading('#0', text='Evidence for this load'); self.assignment_tree.heading('status', text='Status')
        self.assignment_tree.column('#0', width=210, minwidth=100); self.assignment_tree.column('status', width=75, stretch=False)
        scroll = ttk.Scrollbar(checklist, command=self.assignment_tree.yview)
        scroll.pack(side='right', fill='y'); self.assignment_tree.pack(fill='both', expand=True)
        self.assignment_tree.configure(yscrollcommand=scroll.set)
        self.assignment_tree.bind('<<TreeviewSelect>>', self.pick_purpose)
        self.refresh_assignments()

    def preview(self, event=None):
        selected = self.filelist.curselection()
        if not selected: return
        item = self.photos[selected[0]]; self.selected_photo = item['path']
        self.selected_label.configure(text=item['name'])
        try:
            if Path(item['path']).suffix.lower() == '.pdf':
                import fitz
                with fitz.open(item['path']) as doc:
                    pix = doc[0].get_pixmap(matrix=fitz.Matrix(.7, .7), alpha=False)
                    image = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
            else: image = Image.open(item['path']).convert('RGB')
            image.thumbnail((max(160, self.preview_label.winfo_width()-20), 150))
            self.current_image = ImageTk.PhotoImage(image)
            self.preview_label.configure(image=self.current_image, text='')
        except Exception: self.preview_label.configure(image='', text='Preview unavailable for this file')

    def pick_purpose(self, event=None):
        selected = self.assignment_tree.selection()
        if selected and selected[0] in SLOT_LABELS:
            self.slot.set(selected[0]); self.slot_display.set(SLOT_LABELS[selected[0]])

    def assign(self):
        if not self.selected_photo:
            messagebox.showinfo('Select a file first', 'Click an imported file on the left, then choose its purpose.'); return
        if self.slot.get() != 'financial_pdfs' and Path(self.selected_photo).suffix.lower() not in IMAGE_EXT:
            messagebox.showwarning('Image required', 'Choose an image for photo evidence. Use Invoice / financial PDF for PDF attachments.'); return
        if self.slot.get().startswith('measurement_extra_'):
            load = self.case['loads'][int(self.e_load.get())-1]
            mapping = load.setdefault('extra_measurement_slots', {})
            mapping[self.slot.get()] = self.selected_photo
            load['extra_measurement_photos'] = list(dict.fromkeys(mapping.values()))
            self.save(); self.refresh_assignments()
        else: super().assign()
        self.status.set(f'Assigned · {self.slot_display.get()} · Load {self.e_load.get()}')

    def clear_slot(self):
        if self.slot.get().startswith('measurement_extra_'):
            load = self.case['loads'][int(self.e_load.get())-1]
            mapping = load.get('extra_measurement_slots', {})
            if mapping:
                mapping.pop(self.slot.get(), None)
                load['extra_measurement_photos'] = list(dict.fromkeys(mapping.values()))
            else:
                messagebox.showinfo('Older case', 'These supplemental photos were saved together by an older version. Use More → Photo gallery to review them.'); return
            self.save(); self.refresh_assignments()
        else: super().clear_slot()

    def refresh_assignments(self):
        if not self.case or not hasattr(self, 'assignment_tree') or not self.assignment_tree.winfo_exists(): return
        tree = self.assignment_tree; tree.delete(*tree.get_children())
        load = self.case['loads'][int(self.e_load.get())-1]
        extras = load.get('extra_measurement_photos', [])
        for key, label in SLOT_LABELS.items():
            if key in PHASES:
                count = len(self.case.get(key, [])); status = f'{count} file(s)'
            else:
                if key == 'disposal_photo': path = load.get(key)
                elif key == 'first_10_proof': path = load.get('evidence_first_10_cyd')
                elif key.startswith('measurement_extra_'):
                    n = int(key[-1])-1
                    path = load.get('extra_measurement_slots', {}).get(key) if load.get('extra_measurement_slots') else (extras[n] if len(extras)>n else None)
                else: path = load.get('photos', {}).get(key)
                status = 'Added' if path and Path(path).is_file() else ('Optional' if key.startswith('measurement_extra_') else 'Missing')
            tree.insert('', 'end', iid=key, text=label, values=(status,))

    def draw_finance(self):
        if not self.case: self.empty(self.finance_tab); return
        content = self.scroll_page(self.finance_tab)
        self.card(content, 'First 10 CYD at the Request Rate', 'The HUD deduction is calculated from cubic yards and rate. Separate vendor bookkeeping credits are not used.')
        card = self.card(content, 'Invoice Figures')
        grid = ttk.Frame(card, style='Card.TFrame'); grid.pack(fill='x')
        for i, (label, key) in enumerate([('Quantity billed (CYD)', 'invoice_quantity_cyd'), ('Net invoice amount ($)', 'invoice_amount_usd'), ('Deduction shown on invoice ($)', 'invoice_deduction_usd')]):
            self.field(grid, label, key, self.case.get(key, ''), i//2, i%2)
        self.vars['verified_first_10_amount']=tk.StringVar(value='')
        ttk.Label(grid,text='Calculated HUD Deduction ($)').grid(row=2,column=0,sticky='w',pady=8)
        ttk.Label(grid,textvariable=self.vars['verified_first_10_amount']).grid(row=2,column=1,sticky='w')
        card = self.card(content, 'Invoice Treatment')
        options = [('Does the invoice quantity include the first 10 CYD?', 'invoice_quantity_basis',
                    [('Choose an answer', 'unknown'), ('Yes · full measured quantity', 'includes'), ('No · first 10 CYD excluded', 'excludes')]),
                   ('Is a deduction already shown on this invoice?', 'invoice_deduction_status',
                    [('Choose an answer', 'unknown'), ('Yes · separately deducted', 'yes'), ('No deduction shown', 'no'), ('Different billing arrangement', 'alternate')]),
                   ('Was the allowance handled on another work order?', 'first_10_prior_work',
                    [('Choose an answer', 'unknown'), ('No', 'no'), ('Yes', 'yes')])]
        self.finance_displays = {}
        for label, key, choices in options:
            ttk.Label(card, text=label, style='Card.TLabel', wraplength=580).pack(anchor='w', pady=(12, 5))
            raw = tk.StringVar(value=self.case.get(key, 'unknown')); self.vars[key] = raw
            display = tk.StringVar(value=next((name for name, value in choices if value == raw.get()), choices[0][0]))
            self.finance_displays[key] = display
            combo = ttk.Combobox(card, textvariable=display, values=[name for name, _ in choices], state='readonly', width=42)
            combo.pack(anchor='w')
            combo.bind('<<ComboboxSelected>>', lambda event, r=raw, d=display, opts=choices: r.set(dict(opts)[d.get()]))
        grid = ttk.Frame(card, style='Card.TFrame'); grid.pack(fill='x', pady=10)
        self.field(grid, 'Policy / work-order reference', 'financial_confirmation_note', self.case.get('financial_confirmation_note', ''), 0)
        ttk.Button(card, text='Confirm Invoice Treatment', style='Primary.TButton', command=self.confirm_financial_rule).pack(anchor='w', pady=(12, 0))
        card = self.card(content, 'Invoice Check')
        self.finance_summary = ttk.Label(card, text='', style='Card.TLabel', wraplength=600, justify='left')
        self.finance_summary.pack(anchor='w', pady=8)
        ttk.Button(card, text='Check Figures', command=self.show_checks).pack(anchor='w')
        self.show_checks()

    def evaluate(self):
        self.sync_case()
        from cor_package import totals
        try:amount=str(totals(self.case)['allowance'])
        except (ValueError,KeyError):amount=''
        self.case['verified_first_10_amount']=amount
        self.case['first_10_prior_work']='no'
        if 'verified_first_10_amount' in self.vars and self.vars['verified_first_10_amount'].get()!=amount:self.vars['verified_first_10_amount'].set(amount)
        if 'first_10_prior_work' in self.vars:self.vars['first_10_prior_work'].set('no')
        qty, gross, ded, issues = super().evaluate()
        # Missing-slot findings are already reported per load above. Preserve all other audit findings.
        issues = [issue for issue in issues if not re.match(r'BLOCKING / Source audit: Missing (height|width|length|empty|quarter|half|three_quarters|full_1|full_2|receipt|disposal/unloading image)$', issue)]
        issues = [issue for issue in issues if 'Field Guide supplemental measurement views not fully linked (template remains unchanged)' not in issue]
        for i, load in enumerate(self.case['loads'], 1):
            _, problem = screenshot_status(load)
            if problem: issues.append(f'BLOCKING / Load {i} calculator: {problem}')
        return qty, gross, ded, issues

    def confirm_financial_rule(self):
        self.sync_case()
        from cor_package import totals
        try:self.vars['verified_first_10_amount'].set(str(totals(self.case)['allowance']))
        except (ValueError,KeyError):
            messagebox.showerror('Check Measurements','Confirm the measurements and request rate first.');return
        super().confirm_financial_rule()

    def show_checks(self):
        if not self.case: return []
        qty, gross, ded, issues = self.evaluate()
        net = 'Needs confirmation' if ded is None else f'${gross-ded:,.2f}'
        summary = f'Measured: {qty:.2f} CYD     Gross: ${gross:,.2f}\nHUD Request: {net}'
        if hasattr(self, 'finance_summary') and self.finance_summary.winfo_exists():
            finance = [x.split(' / ', 1)[-1] for x in issues if self.issue_step(x) == 2]
            self.finance_summary.configure(text=summary+'\n\n'+('\n'.join(finance) if finance else 'Invoice figures agree.'))
        if hasattr(self, 'review_tree') and self.review_tree.winfo_exists():
            tree = self.review_tree; tree.delete(*tree.get_children())
            self.issue_routes = {}
            self.review_summary.configure(text=summary)
            blocking = sum(x.startswith('BLOCKING') for x in issues)
            self.review_count.configure(text=f'{blocking} items to resolve · {len(issues)-blocking} items to review' if issues else 'All checks complete')
            for i, issue in enumerate(issues):
                route = self.issue_step(issue)
                text = issue.split(' / ', 1)[-1]
                text = text.removeprefix('Source audit: ')
                for raw, human in SLOT_LABELS.items(): text = text.replace('image '+raw, 'photo: '+human)
                text = text.replace('First 10 CYD progression/remaining debris evidence unlinked', 'Assign first-10-CYD evidence in Photos & files.')
                text = text.replace('Missing property before and/or after photo selections', 'Assign property before-work and after-work photos.')
                ident = str(i); self.issue_routes[ident] = route
                tree.insert('', 'end', iid=ident, text=text, values=('Resolve' if issue.startswith('BLOCKING') else 'Review', STEPS[route][0]))
        return issues

    def issue_step(self, issue):
        lower = issue.lower()
        if 'supplemental measurement' in lower: return 1
        if 'calculator' in lower or 'measurement:' in lower or 'overage evidence' in lower: return 0
        if any(word in lower for word in ('image', 'photo', 'evidence', 'source audit', 'progression')): return 1
        return 2

    def draw_checks(self):
        if not self.case: self.empty(self.check_tab); return
        self.clear(self.check_tab)
        card = self.card(self.check_tab, 'Package Summary')
        self.review_summary = ttk.Label(card, text='', style='Card.TLabel', font=(self.ui_font, 11), justify='left', wraplength=600)
        self.review_summary.pack(anchor='w', pady=10)
        self.review_count = ttk.Label(self.check_tab, text='', font=(self.ui_font, 12, 'bold'))
        self.review_count.pack(anchor='w', pady=(0, 5))
        ttk.Label(self.check_tab, text='Select an item, then click Go to step. Export stays available for an incomplete draft.', style='Muted.TLabel', wraplength=650).pack(anchor='w', pady=(0, 10))
        body = ttk.Frame(self.check_tab); body.pack(fill='both', expand=True)
        self.review_tree = ttk.Treeview(body, columns=('status', 'step'), show='tree headings')
        tree = self.review_tree
        tree.heading('#0', text='What needs attention'); tree.heading('status', text='Action'); tree.heading('step', text='Where')
        tree.column('#0', width=440, minwidth=220); tree.column('status', width=70, stretch=False); tree.column('step', width=125, stretch=False)
        scroll = ttk.Scrollbar(body, command=tree.yview); scroll.pack(side='right', fill='y')
        horizontal = ttk.Scrollbar(self.check_tab, orient='horizontal', command=tree.xview); horizontal.pack(fill='x')
        tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set); tree.pack(fill='both', expand=True)
        buttons = ttk.Frame(self.check_tab); buttons.pack(fill='x', pady=(12, 0))
        ttk.Button(buttons, text='Go to Selected Step', command=self.resolve_issue).pack(side='left')
        ttk.Button(buttons, text='Refresh Checks', command=self.show_checks).pack(side='left', padx=8)
        tree.bind('<Double-1>', lambda event: self.resolve_issue())
        self.show_checks()

    def resolve_issue(self):
        selected = self.review_tree.selection()
        if selected: self.go(self.issue_routes[selected[0]])

    def open_output(self):
        if not self.require(): return
        folder = self.case_dir/'output'
        if getattr(self,'_last_export_case_dir',None)==self.case_dir:
            folder=getattr(self,'_last_export_folder',folder)
        folder.mkdir(parents=True,exist_ok=True)
        try:
            if sys.platform == 'win32': os.startfile(str(folder))
            elif sys.platform == 'darwin': subprocess.Popen(['open', str(folder)])
            else: subprocess.Popen(['xdg-open', str(folder)])
        except Exception: messagebox.showinfo('Output folder', str(folder))

    def help(self):
        messagebox.showinfo('Four steps to a package',
            '1. CASE & LOADS\nEnter measurements and attach a real cubic yard calculation for each load.\n\n'
            '2. PHOTOS & FILES\nImport a folder or ZIP. Select a file, choose its purpose and assign it.\n\n'
            '3. INVOICE\nCopy the invoice figures and confirm how the calculated first-10-CYD deduction was handled.\n\n'
            '4. REVIEW & EXPORT\nSelect an issue to return to the right step. Generate a Word draft and use Open output folder.\n\n'
            'Changes save when moving between steps and closing the app. Ctrl+S saves at any time. Advanced tools are under More.')

