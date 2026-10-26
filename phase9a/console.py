"""Cancellable Windows console/pipe reader; never blocks the simulation owner."""
import codecs
import ctypes
import os
import sys
import threading

class ConsoleInput:
    def __init__(self,bus,console):
        self.bus,self.console=bus,console;self.stop=threading.Event()
        self.thread=threading.Thread(target=self.run,name='phase9a-console',daemon=False)
    def start(self):self.thread.start()
    def run(self):
        if os.name!='nt':
            self.bus.submit('Consola interactiva soportada en Windows; use --script en este entorno','console',kind='status');return
        import msvcrt
        buffer='';skip=False
        if sys.stdin.isatty():
            while not self.stop.wait(.02):
                while msvcrt.kbhit():
                    ch=msvcrt.getwch()
                    if skip:skip=False;continue
                    if ch in ('\x00','\xe0'):skip=True;continue
                    if ch=='\x03':self.bus.submit('salir');return
                    if ch=='\x1a':return
                    if ch in ('\r','\n'):
                        print('',file=self.console,flush=True);self.bus.submit(buffer);buffer=''
                    elif ch=='\b':
                        if buffer:buffer=buffer[:-1];print('\b \b',end='',file=self.console,flush=True)
                    else:buffer+=ch;print(ch,end='',file=self.console,flush=True)
            return
        try:
            handle=msvcrt.get_osfhandle(sys.stdin.fileno());kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.GetFileType.argtypes=[ctypes.c_void_p];kernel.GetFileType.restype=ctypes.c_ulong
            kernel.PeekNamedPipe.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong),ctypes.c_void_p]
            kind=kernel.GetFileType(handle);decoder=codecs.getincrementaldecoder(sys.stdin.encoding or 'utf-8')(errors='replace')
            while not self.stop.wait(.02):
                if kind==3:
                    available=ctypes.c_ulong()
                    if not kernel.PeekNamedPipe(handle,None,0,None,ctypes.byref(available),None):return
                    if not available.value:continue
                    count=min(available.value,4096)
                elif kind==1:count=4096
                else:return
                data=os.read(sys.stdin.fileno(),count)
                if not data:
                    if buffer:self.bus.submit(buffer)
                    return
                buffer+=decoder.decode(data)
                while '\n' in buffer:
                    line,buffer=buffer.split('\n',1);self.bus.submit(line.rstrip('\r'))
        except (OSError,ValueError) as exc:self.bus.submit(f'Entrada de texto cerrada: {exc}','console',kind='status')
    def close(self):
        self.stop.set()
        if self.thread.ident:self.thread.join(timeout=2.)
        return not self.thread.is_alive()
