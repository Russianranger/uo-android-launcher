using Mono.Cecil;

internal static class MapMetadataContract
{
    internal const string Chunk = "System.Void ClassicUO.Game.Map.Chunk::Load(System.Int32,System.Boolean)";
    internal const string Sanitize = "System.Void ClassicUO.Assets.MapLoader::SanitizeMapIndex(System.Int32&)";
    internal const string Length = "System.Int64 ClassicUO.IO.FileReader::get_Length()";
    internal const string Wrapper = "System.Int64 ClassicUO.Assets.MapLoader::MementoMapChunkLength(ClassicUO.IO.FileReader)";
    // Ordinary accepted frame/music selections and the exact 0.2.19 diagnostic
    // versions. The optimization is the final independent restoration layer.
    internal static readonly Dictionary<string, string[]> Bases = new() {
        ["TazUO.dll"] = new[] {
            "aac6afae48a00ddeef711238b5e84491ae4b9bd0aff89e91fb4fc956fc0b0b76",
            "fe64075b3ec0ebbea7d07ffc8b4a010e53ba7767018491b6370026d86e7c3a80",
            "fe1c83cfde7de0afaa00c0f9cccc7a96af4297dfc551ce724500b017be4c03ed",
            "5272bc8a31a534a4530b409db5efba39dd9e630e33761437e2133d7a9bce4d36" },
        ["ClassicUO.Assets.dll"] = new[] {
            "1dd53cf0eea718aefeda33fba105c9797b138188be22562b47548c310524100d",
            "84340a487aeae33c0f17ae1b20a0c8d1b54122d1e23801e5a582452c7db905c9",
            "764e7cba68a58c3a1ef3d72013abcf866275b824ba3a662939d7a7630af2b20c",
            "b10baebafdcc4e006dfb347453928c686a5508136e90214d2e3b0fa146b35f14" },
    };
    internal static bool IsTarget(MethodDefinition method) => method.FullName == Chunk || method.FullName == Sanitize;
}
