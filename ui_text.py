"""Readable display text; diagnostic validation and navigation stay unchanged."""
import re
FIELDS={'length_ft':'Length (ft)','width_ft':'Width (ft)','side_height_ft':'Wall Height (ft)','fill_fraction':'Final Fill','overage_height_ft':'Overage Height (ft)','overage_cyd':'Documented Overage (CYD)','rate_per_cyd':'Request Rate ($/CYD)'}
def readable_issue(text):
    for key,label in FIELDS.items():text=re.sub(r'\b'+re.escape(key)+r'\b',lambda m:label,text)
    text=re.sub(r'is not a number:\s*$', 'needs a valid number.',text)
    return text
