"""Order-independent groups backed by explicit source-bound load-card readings."""
from collections import defaultdict
from datetime import datetime
from calculator_evidence import file_digest

def propose_evidence_groups(case,rows):
    from load_identity import current_clue,text_numbers,propose_loads
    fresh={}
    imported={r['path'] for r in case.get('imported_files',[])}
    documents={d.get('path') for d in case.get('package_documents',[]) if d.get('confirmed') and d.get('role')!='exclude'}
    for row in rows:
        p=row['path']
        if case.get('load_card_dismissals',{}).get(p,{}).get('sha256')==row.get('sha256'):continue
        if p not in imported or p in documents or row.get('stage') in ('before','during','after'):continue
        reviewed_type=case.get('photo_category_examples',{}).get(p,{})
        if reviewed_type.get('sha256')==row.get('sha256') and reviewed_type.get('category') in ('property_photos','other'):continue
        try:
            if not row.get('sha256') or file_digest(p)!=row['sha256']:continue
        except OSError:continue
        fresh[p]=row
    cards=defaultdict(list);mappings=defaultdict(set);output={}
    for path,row in fresh.items():
        clue=current_clue(case,path,row['sha256'])
        review=case.get('load_card_reviews',{}).get(path,{})
        manual=review.get('vendor_load') if review.get('confirmed') and review.get('sha256')==row['sha256'] else None
        if manual is not None:
            number=manual
        else:
            if not clue or clue.get('status') not in ('single_reader','corroborated') or len(clue.get('options',[]))!=1:continue
            number=clue['options'][0]
            supporting=[r for r in clue.get('readings',[]) if number in text_numbers(r.get('text','')) and number in r.get('loads',[])]
            if not supporting:continue
        if isinstance(number,bool) or not isinstance(number,int) or not 1<=number<=150:continue
        row=dict(row,card_number_reviewed=manual is not None)
        from template_review import pixel_digest
        row=dict(row,card_pixel_hash=pixel_digest(path))
        cards[number].append(row)
        review=case.get('load_card_reviews',{}).get(path,{})
        target=review.get('load')
        if review.get('confirmed') and review.get('sha256')==row['sha256'] and isinstance(target,int) and not isinstance(target,bool) and 1<=target<=len(case.get('loads',[])):mappings[number].add(target)
    reused=set();location_conflicts=set()
    for number,members in cards.items():
        dates={r.get('sequence_date') or (r.get('sequence_time') or '').split('T')[0] for r in members}
        dates.discard('');dates.discard(None)
        if len(dates)>1:reused.add(number)
        locations={v['key'] for r in members for v in r.get('location_clues',[]) if v.get('key')}
        if len(locations)>1:location_conflicts.add(number)
    for number,members in sorted(cards.items()):
        members.sort(key=lambda r:r['sha256']);anchor=members[0];mapping=mappings[number]
        conflict=len(mapping)>1 or number in reused or number in location_conflicts;target=next(iter(mapping)) if len(mapping)==1 and not conflict else None
        proposal=dict(load=target,vendor_load=number,status='card_mapping_conflict' if conflict else 'card_group',
                      group_id=f'vendor-card:{number}',group_label=f'Card Reads Load {number}',
                      basis='Explicit Card Text',reason='Load Number Appears on Different Dates — Check Each Trip' if number in reused else 'Location Text Differs — Check the Source Photos' if number in location_conflicts else 'Package Load Mapping Conflicts' if conflict else f'Card Reads Load {number} · Check Package Load',
                      anchor_path=anchor['path'],verified=False)
        for row in members:
            if row.get('load') not in (None,target):continue
            output[row['path']]=dict(proposal,card_number_reviewed=row.get('card_number_reviewed',False))
    # A conflict in other photos must not erase this photo's explicit reviewed mapping.
    # It supplies no permission to propagate the same number to other sources.
    for path,row in fresh.items():
        review=case.get('load_card_reviews',{}).get(path,{})
        target=review.get('load')
        if not review.get('confirmed') or review.get('sha256')!=row['sha256'] or isinstance(target,bool) or not isinstance(target,int) or not 1<=target<=len(case.get('loads',[])):continue
        previous=output.get(path,{})
        if row.get('load') not in (None,target):
            output[path]=dict(load=None,status='card_mapping_conflict',reason='Reviewed Photo Load and Card Mapping Disagree',verified=False)
            continue
        number=review.get('vendor_load') or previous.get('vendor_load')
        conflict=bool(number in reused or number in location_conflicts or len(mappings.get(number,set()))>1)
        output[path]=dict(previous,load=target,vendor_load=number,status='reviewed_card',verified=False,
            group_id=f'reviewed-card:{target}',group_label=f'Load {target} · Reviewed Cards',
            reason=f'Reviewed Package Load {target}'+(' · Location Text Differs' if number in location_conflicts else ' · Different Dates — Check Other Trips' if number in reused else ' · Other Matching Numbers Need Review' if conflict else ''),basis='Source-Bound Card Review',cross_source_conflict=conflict)
    # Only two distinct cards with the same explicit number and exact clock
    # bound a proposed interval. No extrapolation from a lone card or date.
    for number,members in sorted(cards.items()):
        if len(mappings[number])>1 or number in reused or number in location_conflicts:continue
        for source in ('camera','photo_text'):
            timed=[]
            for row in members:
                if row.get('sequence_source')!=source:continue
                raw=row.get('sequence_time')
                try:
                    if not isinstance(raw,str) or 'T' not in raw:continue
                    stamp=datetime.fromisoformat(raw)
                    if stamp.tzinfo is not None:continue
                except ValueError:continue
                timed.append((stamp,row))
            if len({row['card_pixel_hash'] for _,row in timed})<2:continue
            timed.sort(key=lambda x:x[0]);start,end=timed[0][0],timed[-1][0]
            if not 0<(end-start).total_seconds()<=14400:continue
            foreign=[]
            for other,group in cards.items():
                if other==number:continue
                foreign.extend(row for row in group if row.get('sequence_source')==source)
            blocked=False
            for row in foreign:
                try:
                    if start<=datetime.fromisoformat(row.get('sequence_time',''))<=end:blocked=True
                except (ValueError,TypeError):pass
            target=next(iter(mappings[number])) if len(mappings[number])==1 else None
            for row in fresh.values():
                if row.get('load') not in (None,target) and row.get('sequence_source')==source:
                    try:
                        if start<=datetime.fromisoformat(row.get('sequence_time',''))<=end:blocked=True
                    except (ValueError,TypeError):pass
            if blocked:continue
            anchor=timed[0][1];base=dict(output.get(anchor['path'],{}))
            for path,row in fresh.items():
                if path in output or row.get('category') not in ('measurement','container_photos') or row.get('sequence_source')!=source:continue
                try:stamp=datetime.fromisoformat(row.get('sequence_time',''))
                except (ValueError,TypeError):continue
                if start<=stamp<=end and row.get('load') in (None,target):
                    output[path]=dict(base,status='card_time_group',basis='Matching Cards and Bounded Capture Times',reason=f'Between Matching Load {number} Cards · Check Evidence',anchors=[timed[0][1]['path'],timed[-1][1]['path']])
    # Existing manually checked start/end anchors remain usable independently.
    for path,p in propose_loads(case,list(fresh.values())).items():
        if p.get('status')!='sequence':continue
        previous=output.get(path)
        if previous and previous.get('load') not in (None,p.get('load')):
            output[path]=dict(load=None,status='card_mapping_conflict',reason='Card and Reviewed Time Boundaries Disagree',verified=False);continue
        output[path]=dict(p,group_id=f'reviewed-window:{p["load"]}',group_label=f'Load {p["load"]} · Reviewed Times',basis='Reviewed Time Boundaries',verified=False)
    return output

def propose_date_review_groups(case,rows,strong=None):
    """Calendar buckets for bulk inspection; never template-eligible load evidence."""
    strong=propose_evidence_groups(case,rows) if strong is None else strong
    by_path={r['path']:r for r in rows};days=defaultdict(list);blocked=set();output={}
    def day_of(row):
        day=row.get('sequence_date') or (row.get('sequence_time') or '').split('T')[0]
        try:
            if not isinstance(day,str) or len(day)!=10:return None
            datetime.strptime(day,'%Y-%m-%d');return day
        except ValueError:return None
    for path,proposal in strong.items():
        row=by_path.get(path,{})
        day=day_of(row)
        if not day:continue
        if proposal.get('status')=='card_mapping_conflict' or proposal.get('cross_source_conflict'):blocked.add(day)
        elif proposal.get('status') in ('card_group','reviewed_card') and isinstance(proposal.get('vendor_load'),int):days[day].append((proposal,row))
    imported={r['path'] for r in case.get('imported_files',[])}
    documents={d.get('path') for d in case.get('package_documents',[]) if d.get('confirmed') and d.get('role')!='exclude'}
    for day,entries in sorted(days.items()):
        numbers={proposal.get('vendor_load') for proposal,row in entries}
        if day in blocked or len(numbers)!=1:continue
        number=next(iter(numbers));targets={p.get('load') for p,r in entries if p.get('load') is not None}
        if len(targets)>1:continue
        target=next(iter(targets)) if targets else None
        anchor=min((row for proposal,row in entries),key=lambda row:row['sha256'])
        locations={v['key'] for p,r in entries for v in r.get('location_clues',[]) if v.get('key')}
        if len(locations)>1:continue
        for row in rows:
            path=row['path']
            if path in strong or path not in imported or path in documents or row.get('load') or row.get('category')!='container_photos' or row.get('stage') in ('before','during','after'):continue
            if day_of(row)!=day:continue
            own={v['key'] for v in row.get('location_clues',[]) if v.get('key')}
            if own and locations and own!=locations:continue
            try:
                if not row.get('sha256') or file_digest(path)!=row['sha256']:continue
            except OSError:continue
            output[path]=dict(load=target,vendor_load=number,status='date_review_group',review_only=True,
                group_id=f'date-review:{day}:{number}',group_label=f'{day} · Check Against Card {number}',
                reason=f'Same Date as Card {number} · Check Trip',anchor_path=anchor['path'],verified=False)
    return output
