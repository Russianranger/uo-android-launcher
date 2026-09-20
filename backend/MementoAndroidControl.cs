// Added to the app's deployment copy; upstream source is never rewritten.
using System;
using System.IO;
namespace Server.Misc {
    public sealed class MementoAndroidControl : Timer {
        public static void Initialize() { new MementoAndroidControl().Start(); }
        private MementoAndroidControl() : base(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(1)) {}
        protected override void OnTick() {
            string request = "/work/run/world-command.json";
            if (!File.Exists(request) || World.Saving) return;
            string action = File.ReadAllText(request).Trim();
            File.Delete(request);
            try {
                World.WaitForWriteCompletion();
                World.Save(true, false);
                World.WaitForWriteCompletion();
                File.WriteAllText("/work/run/world-command.done", action);
                if (action == "stop") Core.Kill(false);
            } catch (Exception e) {
                File.WriteAllText("/work/run/world-command.error", e.ToString());
            }
        }
    }
}
