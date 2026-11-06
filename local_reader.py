"""Optional local OCR. Failure always falls back to manual review."""
import base64
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageOps

WINDOWS_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]
$generic = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 } | Select-Object -First 1
function Await($operation, $type) {
  $task = $generic.MakeGenericMethod($type).Invoke($null, @($operation))
  $task.Wait()
  return $task.Result
}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($env:ED_OCR_INPUT)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
try {
  $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  try {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $engine) { throw 'No OCR language is installed.' }
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    Write-Output $result.Text
  } finally { $bitmap.Dispose() }
} finally { $stream.Dispose() }
'''

def read_image(path,page_mode=11):
    try:
        with tempfile.TemporaryDirectory(prefix='ed-ocr-') as folder:
            target = Path(folder)/'image.png'
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((2200,2200));image.save(target)
            options=dict(capture_output=True,timeout=25)
            if sys.platform=='win32': options['creationflags']=subprocess.CREATE_NO_WINDOW
            if shutil.which('tesseract'):
                process=subprocess.run(['tesseract',str(target),'stdout','--psm',str(page_mode)],**options)
            elif sys.platform=='win32':
                env=os.environ.copy();env['ED_OCR_INPUT']=str(target)
                code=base64.b64encode(WINDOWS_SCRIPT.encode('utf-16le')).decode()
                process=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',code],env=env,**options)
            else: return '', 'Local OCR is unavailable. Review measurements manually.'
            if process.returncode: return '', 'Local OCR could not read this photo. Review it manually.'
            return process.stdout.decode('utf-8',errors='replace').strip(), ''
    except Exception: return '', 'Local OCR could not read this photo. Review it manually.'


def read_timestamp(path):
    """Read the common printed footer separately; output remains unverified.

    No dates or clocks are synthesized. Sources with another timestamp layout
    may still require review. Original image bytes are never modified.
    """
    from PIL import ImageEnhance
    try:
        with tempfile.TemporaryDirectory(prefix='ed-clock-') as folder:
            target=Path(folder)/'footer.png'
            with Image.open(path) as source:
                image=ImageOps.exif_transpose(source).convert('RGB')
                crop=image.crop((0,round(image.height*.7),image.width,image.height))
                crop.thumbnail((1100,1100))
                crop=crop.resize((crop.width*2,crop.height*2))
                ImageEnhance.Contrast(crop).enhance(1.4).save(target)
            text,error=read_image(target,page_mode=6)
            from visual_photo_review import timing_clues
            clues=timing_clues(path,text)
            if not clues['flags'] and any(c.get('date') and c.get('time') for c in clues['clues']):return text,error
            # White printed overlay text needs different preparation from dark
            # handwriting. Isolate observed bright neutral strokes, not digits.
            import cv2
            import numpy as np
            pixels=np.asarray(crop);hsv=cv2.cvtColor(pixels,cv2.COLOR_RGB2HSV)
            mask=(hsv[:,:,1]<90)&(hsv[:,:,2]>190)
            Image.fromarray(np.where(mask,0,255).astype(np.uint8)).save(target)
            alternative,other_error=read_image(target,page_mode=6)
            return text+'\n'+alternative,error or other_error
    except (OSError,ValueError):return '', 'Printed date/time could not be read.'
