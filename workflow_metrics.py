"""Local aggregate diagnostics; no filenames, photo text or outbound telemetry."""
import os,platform,shutil,time,sys
from pathlib import Path

def folder_bytes(folder):
 total=0
 if not folder:return total
 for base,dirs,files in os.walk(folder,followlinks=False):
  dirs[:]=[d for d in dirs if not (Path(base)/d).is_symlink()]
  for name in files:
   p=Path(base)/name
   try:
    if not p.is_symlink():total+=p.stat().st_size
   except OSError:pass
 return total

def measure(case,directory):
 from photo_flow import build_photo_rows
 start=time.perf_counter();rows,_=build_photo_rows(case);cold=time.perf_counter()-start
 start=time.perf_counter();warm,_=build_photo_rows(case,rows);cached=time.perf_counter()-start
 if len(rows)!=len(warm):raise ValueError('Photo count changed during measurement.')
 from small_vision_runtime import RUNTIME
 base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local'/'share'))/'EDPackageBuilder'
 bundled=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'assets'/'handwriting'
 return dict(photos=len(rows),analyzed_photos=sum(r.get('embedding') is not None for r in rows),cold_seconds=round(cold,3),cached_seconds=round(cached,3),project_mb=round(folder_bytes(directory)/1048576,1),model_mb=round((folder_bytes(base/'LoadTextReader')+folder_bytes(RUNTIME.root)+folder_bytes(bundled))/1048576,1),free_disk_mb=round(shutil.disk_usage(directory).free/1048576),logical_cpus=os.cpu_count(),system=platform.system(),machine=platform.machine(),note='Measures cached photo-review preparation on this computer. It does not measure model processing, sorting accuracy or human review time.')
