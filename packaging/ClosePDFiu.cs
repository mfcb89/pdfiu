using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

internal static class ClosePDFiu
{
    private const int StillOpen = 10;
    private const int Failed = 11;
    private const uint WmClose = 0x0010;
    private static readonly string[] Executables = { "PDFiu", "Folio PDF", "PDFiuExplorer" };

    private delegate bool WindowVisitor(IntPtr window, IntPtr state);
    [DllImport("user32.dll")]
    private static extern bool EnumWindows(WindowVisitor callback, IntPtr state);
    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
    [DllImport("user32.dll")]
    private static extern bool IsWindow(IntPtr window);
    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")]
    private static extern bool IsIconic(IntPtr window);
    [DllImport("user32.dll")]
    private static extern bool ShowWindowAsync(IntPtr window, int command);
    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")]
    private static extern IntPtr GetWindow(IntPtr window, uint command);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr window, StringBuilder title, int capacity);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool PostMessage(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);

    private static HashSet<int> RunningProcesses(HashSet<string> paths)
    {
        var ids = new HashSet<int>();
        foreach (string name in Executables)
            foreach (Process process in Process.GetProcessesByName(name))
            using (process)
            {
                try
                {
                    if (!process.HasExited && paths.Contains(process.MainModule.FileName))
                        ids.Add(process.Id);
                }
                catch (InvalidOperationException) { }
                catch (System.ComponentModel.Win32Exception) { }
            }
        return ids;
    }

    private static IntPtr RequestClose(HashSet<int> ids)
    {
        IntPtr requested = IntPtr.Zero;
        EnumWindows(delegate(IntPtr window, IntPtr state)
        {
            uint id;
            GetWindowThreadProcessId(window, out id);
            int pid = (int)id;
            if (!ids.Contains(pid) || !IsWindowVisible(window) || GetWindow(window, 4) != IntPtr.Zero)
                return true;
            var title = new StringBuilder(512);
            GetWindowText(window, title, title.Capacity);
            string caption = title.ToString();
            if (caption == "PDFiu" || caption == "Folio PDF" ||
                caption.EndsWith(" · PDFiu", StringComparison.Ordinal) ||
                caption.EndsWith(" · Folio PDF", StringComparison.Ordinal))
            {
                if (IsIconic(window))
                    ShowWindowAsync(window, 9); // SW_RESTORE
                SetForegroundWindow(window);
                if (PostMessage(window, WmClose, IntPtr.Zero, IntPtr.Zero))
                {
                    requested = window;
                    return false;
                }
            }
            return true;
        }, IntPtr.Zero);
        return requested;
    }

    private static int Main(string[] args)
    {
        if (args.Length < 2 || (args[0] != "--check" && args[0] != "--close"))
            return Failed;
        try
        {
            var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (int index = 1; index < args.Length; index++)
                if (!string.IsNullOrWhiteSpace(args[index]) && Path.IsPathRooted(args[index]))
                    foreach (string executable in Executables)
                        paths.Add(Path.GetFullPath(Path.Combine(args[index], executable + ".exe")));
            if (paths.Count == 0)
                return Failed;
            if (args[0] == "--check")
                return RunningProcesses(paths).Count == 0 ? 0 : StillOpen;
            IntPtr requested = IntPtr.Zero;
            var timer = Stopwatch.StartNew();
            do
            {
                HashSet<int> ids = RunningProcesses(paths);
                if (ids.Count == 0)
                    return 0;
                if (requested == IntPtr.Zero || !IsWindow(requested) || !IsWindowVisible(requested))
                    requested = RequestClose(ids);
                Thread.Sleep(250);
            }
            while (timer.Elapsed < TimeSpan.FromSeconds(45));
            return StillOpen;
        }
        catch (Exception)
        {
            return Failed;
        }
    }
}
