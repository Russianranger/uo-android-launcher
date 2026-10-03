namespace Memento;

// Stable numeric IDs shared by the offline patcher and the timing helper.
internal static class GraphicsOperations
{
    internal static readonly string[] Names = {
        "FNA3D_DrawIndexedPrimitives", "FNA3D_DrawInstancedPrimitives", "FNA3D_DrawPrimitives",
        "FNA3D_SetTextureData2D", "FNA3D_SetTextureData3D", "FNA3D_SetTextureDataCube", "FNA3D_SetTextureDataYUV",
        "FNA3D_GetTextureData2D", "FNA3D_GetTextureData3D", "FNA3D_GetTextureDataCube",
        "FNA3D_ReadBackbuffer", "FNA3D_ResolveTarget", "FNA3D_ResetBackbuffer", "FNA3D_SwapBuffers",
        "FNA3D_AddDisposeTexture", "FNA3D_SetRenderTargets", "FNA3D_Clear", "FNA3D_DestroyDevice",
        "FNA3D_GetVertexBufferData", "FNA3D_GetIndexBufferData", "FNA3D_SetVertexBufferData", "FNA3D_SetIndexBufferData",
        "FNA3D_CreateDevice", "FNA3D_CreateTexture2D", "FNA3D_CreateTexture3D", "FNA3D_CreateTextureCube",
        "FNA3D_GenColorRenderbuffer", "FNA3D_GenDepthStencilRenderbuffer", "FNA3D_GenVertexBuffer", "FNA3D_GenIndexBuffer",
        "FNA3D_CreateEffect", "FNA3D_CloneEffect", "FNA3D_ApplyEffect", "FNA3D_BeginPassRestore", "FNA3D_EndPassRestore",
        "FNA3D_ApplyVertexBufferBindings", "FNA3D_VerifySampler", "FNA3D_VerifyVertexSampler", "FNA3D_Image_Load"
    };
}
