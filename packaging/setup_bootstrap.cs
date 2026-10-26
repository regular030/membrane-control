// Windows includes .NET Framework 4.8. This launcher requires no Python.
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;

internal static class SetupBootstrap
{
    private static string Quote(string value)
    {
        if (value.IndexOf('"') >= 0 || value.IndexOf('\r') >= 0 || value.IndexOf('\n') >= 0)
            throw new ArgumentException("Invalid path argument.");
        return "\"" + value.TrimEnd('\\') + "\"";
    }

    public static int Main(string[] args)
    {
        string temporary = null;
        bool plan = false;
        try
        {
            string target = null;
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--plan") plan = true;
                else if (args[i] == "--target" && i + 1 < args.Length) target = args[++i];
                else throw new ArgumentException("Usage: Setup.exe [--plan] [--target <folder>]");
            }
            try { Console.Title = "Membrane Control Setup"; }
            catch (IOException) { /* Headless build/test runners may have no console. */ }
            Console.WriteLine("Membrane Control setup: app, Python and ESP32 build tools.");
            if (!Environment.Is64BitOperatingSystem || !Environment.Is64BitProcess)
                throw new InvalidOperationException("Use a Windows x64 PC for this installer.");
            temporary = Path.Combine(Path.GetTempPath(), "MembraneControl-Setup-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(temporary);
            string archive = Path.Combine(temporary, "payload.zip");
            using (Stream source = Assembly.GetExecutingAssembly().GetManifestResourceStream("MembraneControl.Payload.zip"))
            {
                if (source == null) throw new InvalidOperationException("The setup payload is missing.");
                using (FileStream destination = File.Create(archive)) source.CopyTo(destination);
            }
            string payload = Path.Combine(temporary, "payload");
            ZipFile.ExtractToDirectory(archive, payload);
            string script = Path.Combine(payload, "packaging", "setup_windows.ps1");
            string powershell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),
                "WindowsPowerShell", "v1.0", "powershell.exe");
            string arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File " + Quote(script)
                + " -SourceRoot " + Quote(payload);
            if (plan) arguments += " -Plan";
            if (target != null) arguments += " -InstallRoot " + Quote(Path.GetFullPath(target));
            ProcessStartInfo start = new ProcessStartInfo(powershell, arguments);
            start.UseShellExecute = false;
            start.WorkingDirectory = payload;
            using (Process process = Process.Start(start))
            {
                process.WaitForExit();
                if (!plan && !Console.IsInputRedirected)
                {
                    Console.WriteLine("\nPress Enter to close this setup window.");
                    Console.ReadLine();
                }
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            Console.Error.WriteLine("Setup could not finish: " + error.Message);
            if (!plan && !Console.IsInputRedirected) Console.ReadLine();
            return 1;
        }
        finally
        {
            // Only clean the unique directory this process created beneath TEMP.
            if (temporary != null)
            {
                string allowed = Path.GetFullPath(Path.GetTempPath()).TrimEnd('\\') + "\\MembraneControl-Setup-";
                string resolved = Path.GetFullPath(temporary);
                if (resolved.StartsWith(allowed, StringComparison.OrdinalIgnoreCase))
                {
                    try { Directory.Delete(resolved, true); }
                    catch { /* A locked setup log can remain for diagnostics. */ }
                }
            }
        }
    }
}
