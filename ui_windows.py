"""Keep primary review windows inside the current monitor's usable work area."""
import sys

def work_area(parent):
 if sys.platform=='win32':
  try:
   import ctypes
   from ctypes import wintypes
   class MonitorInfo(ctypes.Structure):
    _fields_=[('cbSize',wintypes.DWORD),('rcMonitor',wintypes.RECT),('rcWork',wintypes.RECT),('dwFlags',wintypes.DWORD)]
   user=ctypes.windll.user32
   user.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD];user.MonitorFromWindow.restype=wintypes.HANDLE
   user.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(MonitorInfo)];user.GetMonitorInfoW.restype=wintypes.BOOL
   monitor=user.MonitorFromWindow(parent.winfo_id(),2);info=MonitorInfo();info.cbSize=ctypes.sizeof(info)
   if user.GetMonitorInfoW(monitor,ctypes.byref(info)):
    r=info.rcWork;return r.left,r.top,r.right,r.bottom
  except (AttributeError,OSError,ValueError):pass
 return 0,0,parent.winfo_screenwidth(),max(200,parent.winfo_screenheight()-50)

def fit_window(win,parent,preferred=(1100,800),minimum=(900,600)):
 left,top,right,bottom=work_area(parent)
 width=max(200,min(preferred[0],right-left-32));height=max(150,min(preferred[1],bottom-top-60))
 win.minsize(min(minimum[0],width),min(minimum[1],height))
 x=left+(right-left-width)//2;y=top+12
 win.geometry(f'{width}x{height}{x:+d}{y:+d}')
 if sys.platform=='win32':
  # Native placement handles negative monitor coordinates without Tk's
  # right-edge interpretation of negative geometry offsets.
  try:
   import ctypes
   from ctypes import wintypes
   win.update_idletasks();user=ctypes.windll.user32
   user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];user.GetAncestor.restype=wintypes.HWND
   user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT];user.SetWindowPos.restype=wintypes.BOOL
   user.SetWindowPos(user.GetAncestor(win.winfo_id(),2),None,x,y,0,0,1|4|16)
  except (AttributeError,OSError,ValueError):pass
 return left,top,right,bottom
