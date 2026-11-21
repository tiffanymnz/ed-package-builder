"""Score frozen predictions against independently labelled submissions.

JSON arrays must contain id, case, load (integer or null), purpose (string or
null). Predictions must also contain source_sha256; labels must contain the
same hash and split='unseen'. Null predictions are abstentions, never successes.
This tool deliberately does not infer reference labels from filenames or PDF slots.
"""
import argparse
import json
from collections import Counter
from pathlib import Path


def score(labels,predictions,training_cases=()):
    if not labels:raise ValueError('No independent reference labels supplied.')
    def unique(rows):
        result={}
        for row in rows:
            if row['id'] in result:raise ValueError('Duplicate photo id: '+row['id'])
            result[row['id']]=row
        return result
    truth=unique(labels);pred=unique(predictions)
    if set(truth)!=set(pred):raise ValueError('Predictions and reference photos must match exactly.')
    totals={key:Counter() for key in ('load','purpose')};by_case={}
    for ident,label in truth.items():
        if label.get('split')!='unseen' or label['case'] in training_cases:
            raise ValueError('Development/training cases cannot be reported as unseen accuracy.')
        guess=pred[ident]
        if not label.get('source_sha256') or label['source_sha256']!=guess.get('source_sha256'):
            raise ValueError('Source bytes do not match for '+ident)
        if guess.get('case')!=label['case']:raise ValueError('Case mismatch for '+ident)
        counts=by_case.setdefault(label['case'],{key:Counter() for key in totals})
        for key in totals:
            outcome='unresolved' if guess.get(key) is None else 'correct' if guess[key]==label.get(key) else 'wrong'
            totals[key][outcome]+=1;counts[key][outcome]+=1
    def metrics(counts):
        n=sum(counts.values());answered=counts['correct']+counts['wrong']
        return dict(total=n,correct=counts['correct'],wrong=counts['wrong'],unresolved=counts['unresolved'],precision=counts['correct']/answered if answered else None,coverage=answered/n if n else 0)
    return dict(photos=len(truth),cases=len(by_case),overall={k:metrics(v) for k,v in totals.items()},by_case={c:{k:metrics(v) for k,v in values.items()} for c,values in by_case.items()})

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('labels');parser.add_argument('predictions');parser.add_argument('--training-cases',nargs='*',default=[]);parser.add_argument('--output',required=True);args=parser.parse_args()
    result=score(json.loads(Path(args.labels).read_text()),json.loads(Path(args.predictions).read_text()),args.training_cases)
    Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
