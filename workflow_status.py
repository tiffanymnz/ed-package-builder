"""A readable package inventory, with concrete navigation targets."""
from pathlib import Path
from template_review import SLOTS, assigned_path
from cor_package import ROLES


def package_inventory(case):
    rows=[]
    documents=case.get('package_documents',[])
    from calculator_evidence import file_digest
    from evidence_audit import reviewed_source_conflicts
    changed_loads={row['load'] for row in reviewed_source_conflicts(case)}
    def current_document(item):
        if not item.get('confirmed') or not Path(item.get('path','')).is_file():return False
        try:return not item.get('reviewed_sha256') or item['reviewed_sha256']==file_digest(item['path'])
        except OSError:return False
    for role in ('invoice','bid','estimate'):
        selected=[d for d in documents if d.get('role')==role and current_document(d)]
        rows.append(dict(label=ROLES[role],detail=f'{len(selected)} Confirmed' if selected else 'Add or Confirm Document',step=0,kind='documents'))
    ordered=[item for item in SLOTS if item[0]!='calculator']+[item for item in SLOTS if item[0]=='calculator']
    for number,load in enumerate(case.get('loads',[]),1):
        from load_requirements import applicable
        missing=[label for slot,label in ordered if applicable(load,slot) and (not assigned_path(load,slot) or not Path(assigned_path(load,slot)).is_file())]
        rows.append(dict(label=f'Load {number}',detail='Photo Changed — Review Current Evidence' if number in changed_loads else f'Choose {missing[0]}' if missing else 'Photos Attached — Check Measurements' if not load.get('measurements_confirmed') else 'Photos and Measurements Recorded',step=1,load=number,kind='template',slot=next((slot for slot,label in ordered if label in missing),None)))
    for key,label in [('before_photos','Before Removal'),('during_photos','Removal in Progress'),('after_photos','After Removal')]:
        count=sum(Path(p).is_file() for p in case.get(key,[]))
        rows.append(dict(label=label,detail=f'{count} Photos Selected' if count else 'Select Property Photos',step=1,kind='stage'))
    return rows
