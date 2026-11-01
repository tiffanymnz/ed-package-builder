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

def read_image(path):
    try:
        with tempfile.TemporaryDirectory(prefix='ed-ocr-') as folder:
            target = Path(folder)/'image.png'
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((2200,2200));image.save(target)
            options=dict(capture_output=True,timeout=25)
            if sys.platform=='win32': options['creationflags']=subprocess.CREATE_NO_WINDOW
            if shutil.which('tesseract'):
                process=subprocess.run(['tesseract',str(target),'stdout','--psm','11'],**options)
            elif sys.platform=='win32':
                env=os.environ.copy();env['ED_OCR_INPUT']=str(target)
                code=base64.b64encode(WINDOWS_SCRIPT.encode('utf-16le')).decode()
                process=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',code],env=env,**options)
            else: return '', 'Local OCR is unavailable. Review measurements manually.'
            if process.returncode: return '', 'Local OCR could not read this photo. Review it manually.'
            return process.stdout.decode('utf-8',errors='replace').strip(), ''
    except Exception: return '', 'Local OCR could not read this photo. Review it manually.'
