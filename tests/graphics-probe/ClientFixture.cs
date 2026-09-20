// The cached managed counters/properties read from the imported TazUO client.
namespace ClassicUO
{
    internal static class Client { public static GameController Game { get; } = new GameController(); }
    internal static class CUOEnviroment { public static uint CurrentRefreshRate = 47; }
    internal class GameController
    {
        public bool IsActive => true;
        public GameScene Scene { get; } = new GameScene();
    }
    internal class GameScene { }
}
