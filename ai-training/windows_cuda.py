"""Use the installed NVIDIA driver when Windows' public CUDA DLL is absent."""
import ctypes
import os
from pathlib import Path
import shutil


def configure_windows_cuda():
    handles = []
    if os.name != 'nt' or not hasattr(os, 'add_dll_directory'):
        return handles
    try:
        handles.append(ctypes.WinDLL('nvcuda.dll'))
        return handles
    except OSError:
        pass
    store = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/DriverStore/FileRepository'
    for driver in sorted(store.glob('nv*/nvcuda64.dll'), key=lambda p:p.stat().st_mtime, reverse=True):
        try:
            handles.append(os.add_dll_directory(str(driver.parent)))
            # App-local alias of the existing signed driver; no system files changed.
            local = Path(__file__).resolve().parents[1] / '.runtime/cuda-driver/loader'
            local.mkdir(parents=True, exist_ok=True)
            target = local / 'nvcuda.dll'
            loader=driver.with_name('nvcuda_loader64.dll')
            source=loader if loader.exists() else driver
            if not target.exists() or target.stat().st_mtime != source.stat().st_mtime:
                shutil.copy2(source, target)
            handles.append(os.add_dll_directory(str(local)))
            os.environ['PATH'] = str(local) + os.pathsep + str(driver.parent) + os.pathsep + os.environ.get('PATH','')
            lib=ctypes.WinDLL(str(target))
            handles.append(lib)
            count=ctypes.c_int()
            if lib.cuInit(0)!=0 or lib.cuDeviceGetCount(ctypes.byref(count))!=0 or count.value<1:
                continue
            print('[AI] CUDA driver recovered from installed NVIDIA driver (app-local)', flush=True)
            return handles
        except (OSError, ValueError) as exc:
            print(f'[AI] CUDA driver recovery failed: {exc}', flush=True)
    return handles
