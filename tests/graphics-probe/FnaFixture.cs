// FNA's public logging contract; no native renderer or game content.
namespace Microsoft.Xna.Framework
{
    public static class FNALoggerEXT
    {
        public static int OriginalCalls;
        public static System.Action<string> LogInfo = _ => OriginalCalls++;
        public static System.Action<string> LogWarn;
        public static System.Action<string> LogError;
    }
}
