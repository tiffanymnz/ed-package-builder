"""Printed street clues for review; GPS/overlay text is not proof of job identity."""
import re
STREET=re.compile(r'^\s*(\d{1,6}(?:\s*-\s*\d{1,6})?)\s+([A-Za-z0-9][A-Za-z0-9 .\'-]{1,55}?)\s+(STREET|ST|ROAD|RD|AVENUE|AVE|DRIVE|DR|COURT|CT|LANE|LN|BOULEVARD|BLVD|WAY|TERRACE|TER|PLACE|PL|CIRCLE|CIR)\b(?:\s*,.*)?\s*$',re.I)
ENDINGS={'street':'st','road':'rd','avenue':'ave','drive':'dr','court':'ct','lane':'ln','boulevard':'blvd','terrace':'ter','place':'pl','circle':'cir'}
def printed_locations(text):
    found={}
    for line in str(text or '').splitlines():
        match=STREET.fullmatch(line.strip(' .,'))
        if not match:continue
        number=re.sub(r'\s+','',match[1]);name=' '.join(match[2].lower().replace('.','').split());end=ENDINGS.get(match[3].lower(),match[3].lower())
        normalized=f'{number} {name} {end}'
        found[normalized]=' '.join(line.strip().split())
    return [dict(key=key,text=found[key]) for key in sorted(found)]
def photo_locations(case,path,sha):
    cache=case.get('photo_text_cache',{}).get(path,{})
    if not sha or cache.get('sha256')!=sha:return []
    return printed_locations(cache.get('text','')+'\n'+cache.get('timing_text',''))
