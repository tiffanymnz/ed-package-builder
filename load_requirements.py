"""Evidence applicability for a user-confirmed final fill; no visual estimation."""
from decimal import Decimal,InvalidOperation
LOADING=('empty','quarter','half','three_quarters','full_1','full_2')
LEVELS={'empty':Decimal('0'),'quarter':Decimal('.25'),'half':Decimal('.5'),'three_quarters':Decimal('.75'),'full_1':Decimal('1'),'full_2':Decimal('1')}
def confirmed_fill(load):
    try:
        fill=Decimal(str(load.get('fill_fraction',1)))
        if load.get('measurements_confirmed') and fill.is_finite() and 0<fill<=1:return fill
    except (InvalidOperation,ValueError,TypeError):pass
    return Decimal('1')
def required_loading_slots(load):
    fill=confirmed_fill(load)
    endpoint=next(level for level in (Decimal('.25'),Decimal('.5'),Decimal('.75'),Decimal('1')) if level>=fill)
    return {slot for slot in LOADING if LEVELS[slot]<=endpoint}
def applicable(load,slot):return slot not in LOADING or slot in required_loading_slots(load)
def stage_label(load,slot,default):
    fill=confirmed_fill(load)
    if slot in LEVELS and 0<fill<1 and LEVELS[slot]>fill and applicable(load,slot):
        return 'Final Load - '+format(fill*100,'g')+'% Full'+(' - View '+slot[-1] if slot.startswith('full_') else '')
    return default
def evidence_conflicts(load):return [slot for slot in LOADING if not applicable(load,slot) and load.get('photos',{}).get(slot)]
