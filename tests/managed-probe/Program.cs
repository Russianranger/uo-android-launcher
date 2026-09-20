using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;

// Same bundled .NET version and IL-only System.Runtime assembly as the reported
// TazUO installation. No game files, graphics driver or server are involved.
public static class ManagedProbe
{
    public static void Main()
    {
        Assembly runtime=Assembly.LoadFrom(Path.Combine(AppContext.BaseDirectory,"System.Runtime.dll"));
        Console.WriteLine("MEMENTO_MANAGED_OK " + RuntimeInformation.FrameworkDescription + " " + runtime.GetName().Name);
    }
}
