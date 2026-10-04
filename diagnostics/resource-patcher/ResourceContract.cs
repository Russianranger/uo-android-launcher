using Mono.Cecil;

internal static class ResourceContract
{
    internal static readonly Dictionary<string, string[]> Bases = new() {
        ["TazUO.dll"] = new[] { "aac6afae48a00ddeef711238b5e84491ae4b9bd0aff89e91fb4fc956fc0b0b76", "fe64075b3ec0ebbea7d07ffc8b4a010e53ba7767018491b6370026d86e7c3a80" },
        ["ClassicUO.Assets.dll"] = new[] { "1dd53cf0eea718aefeda33fba105c9797b138188be22562b47548c310524100d", "84340a487aeae33c0f17ae1b20a0c8d1b54122d1e23801e5a582452c7db905c9" },
        ["ClassicUO.IO.dll"] = new[] { "334d1932f6fefe22731cccbbd812a6761d55ffa607ff0a4a291c2bc796c78483" },
        ["ClassicUO.Renderer.dll"] = new[] { "1b0c7d0e7bcbf4f54e9d9c7f7229aa33d1ac84c9cdb40ebe4b45d2419676e906" },
        ["FNA.dll"] = new[] { "18c88d506dbe15dcb4bb56f98e4b1756d9f8074ba8ab485ad36e10c087f168b1" }
    };
    internal static int Operation(MethodDefinition m) => (m.DeclaringType.FullName, m.Name) switch {
        ("ClassicUO.Assets.ArtLoader", "GetArt") => 0,
        ("ClassicUO.Assets.ArtLoader", "LoadLand") => 1,
        ("ClassicUO.Assets.ArtLoader", "LoadArt") => 2,
        ("ClassicUO.Assets.GumpsLoader", "GetGump") => 3,
        ("ClassicUO.Assets.TexmapsLoader", "GetTexmap") => 4,
        ("ClassicUO.Assets.LightsLoader", "GetLight") => 5,
        ("ClassicUO.Assets.AnimationsLoader", "ReadUOPAnimationFrames") => 6,
        ("ClassicUO.Assets.AnimationsLoader", "ReadMULAnimationFrames") => 7,
        ("ClassicUO.Assets.PNGLoader", "LoadArtTexture") => 8,
        ("ClassicUO.Assets.PNGLoader", "LoadGumpTexture") => 9,
        ("ClassicUO.Assets.PNGLoader", "GetImageTexture") => 10,
        ("ClassicUO.IO.FileReader", "Read") when !m.HasGenericParameters => 11,
        ("ClassicUO.IO.FileReader", "ReadAt") when !m.HasGenericParameters => 12,
        ("ClassicUO.IO.MMFileReader", "ReadAt") when !m.HasGenericParameters => 13,
        ("ClassicUO.Game.Map.Chunk", "Load") => 14,
        ("ClassicUO.Game.Scenes.GameScene", "DrawWorldRenderTarget") => 15,
        ("ClassicUO.Game.Scenes.GameScene", "DrawRenderList") => 16,
        ("ClassicUO.Renderer.Animations.Animations", "GetAnimationFrames") => 17,
        ("ClassicUO.Game.GameObjects.Item", "Create") => 18,
        ("ClassicUO.Game.GameObjects.Mobile", "Create") => 19,
        ("Microsoft.Xna.Framework.Graphics.Texture2D", "FromStream") => 20,
        ("Microsoft.Xna.Framework.Graphics.GraphicsDevice", "AddResourceReference") => 21,
        ("Microsoft.Xna.Framework.Graphics.GraphicsDevice", "RemoveResourceReference") => 22,
        _ => -1
    };
    internal static int LockOperation(int operation) => operation switch { 17 => 23, 21 => 24, 22 => 25, _ => -1 };
    // Exact signatures keep overloads, generic mapped reads and primitive getters
    // outside the focused attribution layer. These scopes only collect while an
    // originating-thread Chunk.Load observation is active.
    internal static readonly Dictionary<string, int> ChunkParts = new() {
        ["System.Void ClassicUO.Assets.MapLoader::SanitizeMapIndex(System.Int32&)"] = 0,
        ["System.Int64 ClassicUO.IO.FileReader::get_Length()"] = 1,
        ["System.SByte ClassicUO.Game.Map.Map::GetTileZ(System.Int32,System.Int32)"] = 2,
        ["System.Void ClassicUO.Game.GameObjects.Land::ApplyStretch(ClassicUO.Game.Map.Map,System.Int32,System.Int32,System.SByte)"] = 3,
        ["ClassicUO.Game.GameObjects.Land ClassicUO.Game.GameObjects.Land::Create(ClassicUO.Game.World,System.UInt16)"] = 4,
        ["ClassicUO.Game.GameObjects.Static ClassicUO.Game.GameObjects.Static::Create(ClassicUO.Game.World,System.UInt16,System.UInt16,System.Int32)"] = 5,
        ["System.Void ClassicUO.Game.Map.Chunk::AddGameObject(ClassicUO.Game.GameObjects.GameObject,System.Int32,System.Int32)"] = 6,
        ["System.Boolean ClassicUO.Game.Managers.TileMarkerManager::IsTileMarked(System.Int32,System.Int32,System.Int32,System.UInt16&)"] = 7,
    };
    internal static int ChunkPart(MethodDefinition m) => ChunkParts.TryGetValue(m.FullName, out int part) ? part : -1;
    internal static bool IsChunk(MethodDefinition m) => m.FullName == "System.Void ClassicUO.Game.Map.Chunk::Load(System.Int32,System.Boolean)";
    internal static int ExpectedResource(string name) => name switch { "TazUO.dll" => 5, "ClassicUO.Assets.dll" => 11, "ClassicUO.IO.dll" => 3, "ClassicUO.Renderer.dll" => 1, "FNA.dll" => 4, _ => 0 };
    internal static int ExpectedParts(string name) => name switch { "TazUO.dll" => 6, "ClassicUO.Assets.dll" => 1, "ClassicUO.IO.dll" => 1, _ => 0 };
    internal static int Expected(string name) => ExpectedResource(name) + ExpectedParts(name);
}
