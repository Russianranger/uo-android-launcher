using System.Reflection;
using ClassicUO.Game.Scenes;

namespace ClassicUO.Game.Scenes
{
    public class GameObject
    {
        public int Z;
        public (int X, int Y) RealScreenPosition;
        public Action OnDraw;
        public float CalculateDepthZ() => 0;
        public bool Draw(object batcher, int x, int y, float depth) { OnDraw?.Invoke(); return true; }
    }

    public class GameScene
    {
        readonly List<GameObject> items = new();
        readonly int _maxGroundZ = 100;
        void FillGameObjectList() { items.Clear(); items.Add(new()); items.Add(new()); items.Add(new()); }
        // Same release loop as the uploaded TazUO assembly. Graphics/game
        // objects are fixtures; this verifies instrumentation, not device play.
        private int DrawRenderList(object batcher, List<GameObject> renderList)
        {
            int done = 0;
            foreach (GameObject obj in renderList)
            {
                if (obj.Z <= _maxGroundZ)
                {
                    float depth = obj.CalculateDepthZ();
                    if (obj.Draw(batcher, obj.RealScreenPosition.X, obj.RealScreenPosition.Y, depth)) ++done;
                }
            }
            return done;
        }
        public void Run(string scenario)
        {
            FillGameObjectList();
            switch (scenario)
            {
                case "same-thread": items[0].OnDraw = FillGameObjectList; break;
                case "other-thread": items[0].OnDraw = () => { var t = new Thread(FillGameObjectList); t.Start(); t.Join(); }; break;
                case "untracked-write": items[0].OnDraw = () => items.Add(new()); break;
                case "unchanged-versions": items[0].OnDraw = () => throw new InvalidOperationException("injected draw failure"); break;
                case "other-exception": items[0].OnDraw = () => throw new ArgumentException("injected different failure"); break;
                case "overflow":
                    typeof(List<GameObject>).GetField("_version", BindingFlags.NonPublic | BindingFlags.Instance)!.SetValue(items, int.MaxValue - 1);
                    FillGameObjectList(); break;
            }
            bool expectedFailure = scenario is not ("normal" or "overflow");
            Exception observed = null;
            try { if (DrawRenderList(null, items) != 3) throw new Exception("draw count changed"); }
            catch (Exception e) { observed = e; Console.WriteLine("ORIGINAL_EXCEPTION " + e.GetType().Name); }
            if (expectedFailure != (observed != null)) throw new Exception("exception propagation changed");
            if (scenario == "other-exception" && observed is not ArgumentException) throw new Exception("exception type changed");
            FillGameObjectList();
            if (DrawRenderList(null, items) != 3) throw new Exception("next draw failed");
            Console.WriteLine("RENDER_PROBE_OK " + scenario);
        }
    }
}
public static class Program
{
    public static void Main(string[] args) => new GameScene().Run(args.Length > 0 ? args[0] : "normal");
}
