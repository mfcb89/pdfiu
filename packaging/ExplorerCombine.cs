using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
using System.Windows.Forms;
using IDataObject = System.Runtime.InteropServices.ComTypes.IDataObject;

namespace PDFiu.Explorer
{
    [ComImport, Guid("00000122-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IWindowsDropTarget
    {
        [PreserveSig] int DragEnter(IDataObject data, uint keyState, PointL point, ref uint effect);
        [PreserveSig] int DragOver(uint keyState, PointL point, ref uint effect);
        [PreserveSig] int DragLeave();
        [PreserveSig] int Drop(IDataObject data, uint keyState, PointL point, ref uint effect);
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct PointL { public int X, Y; }

    [ComImport, Guid("00000001-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IClassFactory
    {
        [PreserveSig] int CreateInstance(IntPtr outer, ref Guid iid, out IntPtr instance);
        [PreserveSig] int LockServer([MarshalAs(UnmanagedType.Bool)] bool locked);
    }

    [ComVisible(true), ClassInterface(ClassInterfaceType.None)]
    public sealed class Factory : IClassFactory
    {
        public int CreateInstance(IntPtr outer, ref Guid iid, out IntPtr instance)
        {
            instance = IntPtr.Zero;
            if (outer != IntPtr.Zero)
                return unchecked((int)0x80040110); // CLASS_E_NOAGGREGATION
            Program.ResetIdleTimer();
            IntPtr unknown = Marshal.GetIUnknownForObject(new CombineDropTarget());
            try { return Marshal.QueryInterface(unknown, ref iid, out instance); }
            finally { Marshal.Release(unknown); }
        }

        public int LockServer(bool locked)
        {
            Program.ResetIdleTimer();
            return 0;
        }
    }

    [ComVisible(true), ClassInterface(ClassInterfaceType.None)]
    public sealed class CombineDropTarget : IWindowsDropTarget
    {
        private const uint Copy = 1;
        private const short FileDrop = 15; // CF_HDROP
        private List<string> selection;

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        private static extern uint DragQueryFile(IntPtr drop, uint index, StringBuilder path, uint size);

        [DllImport("ole32.dll")]
        private static extern void ReleaseStgMedium(ref STGMEDIUM medium);

        internal static List<string> ReadSelection(IDataObject data)
        {
            var format = new FORMATETC { cfFormat = FileDrop, dwAspect = DVASPECT.DVASPECT_CONTENT,
                                        lindex = -1, tymed = TYMED.TYMED_HGLOBAL };
            STGMEDIUM medium;
            data.GetData(ref format, out medium);
            try
            {
                var paths = new List<string>();
                uint count = DragQueryFile(medium.unionmember, uint.MaxValue, null, 0);
                for (uint i = 0; i < count; i++)
                {
                    uint length = DragQueryFile(medium.unionmember, i, null, 0);
                    var path = new StringBuilder(checked((int)length + 1));
                    if (length == 0 || DragQueryFile(medium.unionmember, i, path, (uint)path.Capacity) != length)
                        return null;
                    string filename = path.ToString();
                    if (!string.Equals(Path.GetExtension(filename), ".pdf", StringComparison.OrdinalIgnoreCase)
                        || !Path.IsPathRooted(filename))
                        return null;
                    paths.Add(filename);
                }
                return paths;
            }
            finally { ReleaseStgMedium(ref medium); }
        }

        public int DragEnter(IDataObject data, uint keys, PointL point, ref uint effect)
        {
            Program.ResetIdleTimer();
            try { selection = ReadSelection(data); }
            catch (COMException) { selection = null; }
            return DragOver(keys, point, ref effect);
        }

        public int DragOver(uint keys, PointL point, ref uint effect)
        {
            effect = selection != null && selection.Count > 0 ? effect & Copy : 0;
            return 0;
        }

        public int DragLeave()
        {
            selection = null;
            return 0;
        }

        public int Drop(IDataObject data, uint keys, PointL point, ref uint effect)
        {
            Program.ResetIdleTimer();
            effect &= Copy;
            try
            {
                var paths = selection ?? ReadSelection(data);
                if (paths == null || paths.Count == 0)
                {
                    effect = 0;
                    return 0;
                }
                Program.OpenPDFiu(paths);
                effect = Copy;
                return 0;
            }
            catch (Exception error)
            {
                effect = 0;
                return Marshal.GetHRForException(error);
            }
            finally { selection = null; }
        }
    }

    internal static class Program
    {
        private static readonly Guid ClassId = new Guid("10230B99-2AD4-4607-939D-7085BAFB4A96");
        private static Timer idle;

        [DllImport("ole32.dll")]
        private static extern int CoRegisterClassObject(ref Guid clsid,
            [MarshalAs(UnmanagedType.IUnknown)] object factory, uint context, uint flags, out uint registration);

        [DllImport("ole32.dll")]
        private static extern int CoRevokeClassObject(uint registration);

        [STAThread]
        private static int Main()
        {
            Application.OleRequired();
            var factory = new Factory();
            Guid clsid = ClassId;
            uint registration;
            int result = CoRegisterClassObject(ref clsid, factory, 4, 1, out registration); // LOCAL_SERVER, MULTIPLEUSE
            if (result < 0)
                return result;
            try
            {
                using (idle = new Timer { Interval = 15000 })
                {
                    idle.Tick += delegate { Application.ExitThread(); };
                    idle.Start();
                    Application.Run();
                }
                return 0;
            }
            finally
            {
                CoRevokeClassObject(registration);
                GC.KeepAlive(factory);
            }
        }

        internal static void ResetIdleTimer()
        {
            if (idle == null)
                return;
            idle.Stop();
            idle.Start();
        }

        internal static void OpenPDFiu(List<string> paths)
        {
            string selectionDirectory = Path.Combine(
                Environment.GetEnvironmentVariable("LOCALAPPDATA"), "PDFiu", "shell");
            Directory.CreateDirectory(selectionDirectory);
            string id = Guid.NewGuid().ToString("N");
            string list = Path.Combine(selectionDirectory, id + ".txt");
            try
            {
                File.WriteAllLines(list, paths, new UTF8Encoding(false));
                string exe = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "PDFiu.exe");
                using (Process.Start(new ProcessStartInfo(exe, "--combine-selection " + id) { UseShellExecute = false })) { }
            }
            catch
            {
                File.Delete(list);
                throw;
            }
        }
    }
}
