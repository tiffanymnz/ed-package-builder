"""User-supplied CalculatorSoup evidence; never manufacture a website screenshot."""
import hashlib
import json
from pathlib import Path
from PIL import Image

URL = 'https://www.calculatorsoup.com/calculators/construction/cubic-yards-calculator.php'
DIMENSIONS = ('length_ft', 'width_ft', 'side_height_ft', 'overage_height_ft', 'overage_cyd', 'fill_fraction')

def measurement_signature(load):
    values = {key: float(load.get(key, 1 if key == 'fill_fraction' else 0) or 0) for key in DIMENSIONS}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()

def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def screenshot_status(load):
    record = load.get('calculator_evidence') or {}
    path = Path(record.get('path') or '')
    if not record.get('path') or not path.is_file():
        return None, 'Attach a CalculatorSoup screenshot showing the measurements and result.'
    if record.get('source_url') != URL or not record.get('user_confirmed'):
        return None, 'Confirm this screenshot is from CalculatorSoup and matches this load.'
    try:
        if record.get('measurement_signature') != measurement_signature(load):
            return None, 'Measurements changed. Replace or recheck the CalculatorSoup screenshot.'
        if record.get('sha256') != file_digest(path):
            return None, 'The screenshot file changed. Attach and review it again.'
        with Image.open(path) as image:
            image.verify()
    except Exception:
        return None, 'The calculator screenshot cannot be read. Attach a PNG or JPG.'
    return str(path), None
