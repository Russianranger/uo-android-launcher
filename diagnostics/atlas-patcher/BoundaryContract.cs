using Mono.Cecil;

internal static class AtlasBoundaryContract
{
    internal const string RendererHash = "52068cb6033327f6d3683acd0fe89c5e4d61c33ea694395ec207a7ef8599c171";
    internal const string FnaHash = "399c91458ccbd08bcd8094bde39a1091f5edd545fd77a9b4579016e7ac5498c6";
    internal const string NativeType = "Microsoft.Xna.Framework.Graphics.FNA3D";
    internal const string HelperType = "Memento.AtlasUploads";
    internal const string NativePrefix = "MementoNative_";
    // These boundaries consume pixels, mutate resources or may submit/wait for
    // the native upload/render command buffers. Ordinary sampler/state setters
    // do not consume atlas pixels and retain their original paths.
    internal static readonly HashSet<string> NativeNames = new(StringComparer.Ordinal) {
        "FNA3D_DrawIndexedPrimitives", "FNA3D_DrawInstancedPrimitives", "FNA3D_DrawPrimitives",
        "FNA3D_SetTextureData2D", "FNA3D_SetTextureData3D", "FNA3D_SetTextureDataCube", "FNA3D_SetTextureDataYUV",
        "FNA3D_GetTextureData2D", "FNA3D_GetTextureData3D", "FNA3D_GetTextureDataCube",
        "FNA3D_ReadBackbuffer", "FNA3D_ResolveTarget", "FNA3D_ResetBackbuffer", "FNA3D_SwapBuffers",
        "FNA3D_AddDisposeTexture", "FNA3D_SetRenderTargets", "FNA3D_Clear", "FNA3D_DestroyDevice",
        "FNA3D_GetVertexBufferData", "FNA3D_GetIndexBufferData", "FNA3D_SetVertexBufferData", "FNA3D_SetIndexBufferData"
    };
    internal static MethodDefinition[] NativeMethods(ModuleDefinition module) =>
        module.GetType(NativeType).Methods.Where(m => NativeNames.Contains(m.Name)).ToArray();
    internal static string CloneName(MethodDefinition method) => NativePrefix + method.Name;
    internal static MethodDefinition TextureDispose(ModuleDefinition module) =>
        module.GetType("Microsoft.Xna.Framework.Graphics.Texture").Methods.Single(m =>
            m.Name == "Dispose" && m.Parameters.Count == 1 && m.Parameters[0].ParameterType.FullName == "System.Boolean");
}
