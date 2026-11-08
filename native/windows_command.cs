// Launch one engine command on a private Windows desktop, forwarding its pipes.
// Python's STARTUPINFO wrapper omits lpDesktop, so this small native boundary
// supplies it explicitly. The caller's Job Object owns the whole child tree.
using System;
using System.Text;
using System.Runtime.InteropServices;

class InkStudioWindowsCommand {
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    struct Startup {
        public int cb; public string reserved, desktop, title;
        public int x,y,width,height,xchars,ychars,fill,flags;
        public short show,reserved2; public IntPtr reservedBytes,input,output,error;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct ProcessInfo { public IntPtr process,thread; public uint pid,tid; }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool CreateProcessW(string app,StringBuilder command,IntPtr procSecurity,IntPtr threadSecurity,bool inherit,uint flags,IntPtr environment,string cwd,ref Startup startup,out ProcessInfo process);
    [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int kind);
    [DllImport("kernel32.dll")] static extern bool SetHandleInformation(IntPtr handle,uint mask,uint flags);
    [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr handle,uint ms);
    [DllImport("kernel32.dll")] static extern bool GetExitCodeProcess(IntPtr process,out uint code);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern bool SetDllDirectoryW(string directory);

    static string Quote(string arg) {
        var text=new StringBuilder("\""); int slashes=0;
        foreach(char ch in arg) {
            if(ch=='\\') {slashes++;continue;}
            if(ch=='\"')text.Append('\\',slashes*2+1).Append(ch);
            else text.Append('\\',slashes).Append(ch);
            slashes=0;
        }
        return text.Append('\\',slashes*2).Append('"').ToString();
    }
    static int Main(string[] args) {
        if(args.Length<2) {Console.Error.WriteLine("Usage: windows-command DESKTOP EXE [arguments]");return 2;}
        // The Ink/Stitch host sets its own DLL directory. External programs
        // must load their own libraries, rather than inheriting that override.
        SetDllDirectoryW(null);
        var command=new StringBuilder();
        for(int i=1;i<args.Length;i++){if(i>1)command.Append(' ');command.Append(Quote(args[i]));}
        var startup=new Startup(); startup.cb=Marshal.SizeOf(startup);
        startup.desktop="winsta0\\"+args[0];
        startup.flags=0x100|0x1|0x80; // standard handles, hidden, no busy cursor
        startup.input=GetStdHandle(-10);startup.output=GetStdHandle(-11);startup.error=GetStdHandle(-12);
        foreach(IntPtr handle in new[]{startup.input,startup.output,startup.error})
            if(handle!=IntPtr.Zero&&handle!=new IntPtr(-1))SetHandleInformation(handle,1,1);
        ProcessInfo process;
        if(!CreateProcessW(args[1],command,IntPtr.Zero,IntPtr.Zero,true,0x08000000,IntPtr.Zero,null,ref startup,out process)) {
            Console.Error.WriteLine("Could not start the hidden engine command: "+Marshal.GetLastWin32Error());return 2;
        }
        CloseHandle(process.thread);
        try {WaitForSingleObject(process.process,0xffffffff);uint code;GetExitCodeProcess(process.process,out code);return unchecked((int)code);}
        finally {CloseHandle(process.process);}
    }
}
