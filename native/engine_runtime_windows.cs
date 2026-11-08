// Host the CPython 3.11 DLL shipped with the user's unmodified Ink/Stitch.
// Build with the Windows .NET Framework compiler; no Python is installed here.
using System;
using System.IO;
using System.Collections.Generic;
using System.Runtime.InteropServices;

class InkStudioEngineHost {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool SetDllDirectory(string path);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern IntPtr LoadLibrary(string path);
    [DllImport("kernel32.dll", CharSet=CharSet.Ansi)]
    static extern IntPtr GetProcAddress(IntPtr dll, string name);
    [DllImport("python311.dll", CallingConvention=CallingConvention.Cdecl)]
    static extern void Py_SetPath(IntPtr path);
    [DllImport("python311.dll", CallingConvention=CallingConvention.Cdecl)]
    static extern void Py_SetProgramName(IntPtr name);
    [DllImport("python311.dll", CallingConvention=CallingConvention.Cdecl)]
    static extern void Py_Initialize();
    [DllImport("python311.dll", CallingConvention=CallingConvention.Cdecl)]
    static extern void PySys_SetArgvEx(int argc, IntPtr argv, int update);
    [DllImport("python311.dll", CallingConvention=CallingConvention.Cdecl, CharSet=CharSet.Ansi)]
    static extern int PyRun_SimpleString(string code);
    [DllImport("python311.dll", CallingConvention=CallingConvention.Cdecl)]
    static extern int Py_FinalizeEx();

    static int Main(string[] args) {
        if (args.Length < 2) {
            Console.Error.WriteLine("Usage: engine-host BUNDLE BOOTSTRAP [worker arguments]");
            return 2;
        }
        var allocated = new List<IntPtr>();
        bool initialized = false;
        try {
            string bundle = Path.GetFullPath(args[0]);
            SetDllDirectory(bundle);
            IntPtr dll = LoadLibrary(Path.Combine(bundle, "python311.dll"));
            if (dll == IntPtr.Zero) {
                Console.Error.WriteLine("Cannot load Ink/Stitch's Python 3.11 DLL: " + Marshal.GetLastWin32Error());
                return 2;
            }
            foreach (string name in new [] {"Py_IgnoreEnvironmentFlag", "Py_NoSiteFlag", "Py_UTF8Mode"}) {
                IntPtr flag = GetProcAddress(dll, name);
                if (flag != IntPtr.Zero) Marshal.WriteInt32(flag, 1);
            }
            IntPtr search = Marshal.StringToHGlobalUni(Path.Combine(bundle, "base_library.zip") + ";" + bundle);
            IntPtr program = Marshal.StringToHGlobalUni(Path.Combine(bundle, "inkstitch.exe"));
            allocated.Add(search); allocated.Add(program);
            Py_SetPath(search); Py_SetProgramName(program); Py_Initialize(); initialized = true;
            IntPtr argv = Marshal.AllocHGlobal((args.Length - 1) * IntPtr.Size);
            allocated.Add(argv);
            for (int i = 1; i < args.Length; i++) {
                IntPtr value = Marshal.StringToHGlobalUni(args[i]); allocated.Add(value);
                Marshal.WriteIntPtr(argv, (i - 1) * IntPtr.Size, value);
            }
            PySys_SetArgvEx(args.Length - 1, argv, 0);
            // Emit ASCII Python source even when the user's path contains Unicode.
            string path = "";
            foreach (char value in Path.GetFullPath(args[1])) path += "\\u" + ((int)value).ToString("x4");
            int result = PyRun_SimpleString("__file__='" + path + "'; exec(compile(open(__file__,'rb').read(),__file__,'exec'))");
            int final = Py_FinalizeEx(); initialized = false;
            return result != 0 || final < 0 ? 1 : 0;
        } catch (Exception error) {
            Console.Error.WriteLine("Ink Studio engine host: " + error.Message);
            return 2;
        } finally {
            if (initialized) Py_FinalizeEx();
            foreach (IntPtr memory in allocated) Marshal.FreeHGlobal(memory);
        }
    }
}
