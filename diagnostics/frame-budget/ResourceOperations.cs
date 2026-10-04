namespace Memento;

// IDs are shared by the exact-client patcher and its verifier. Do not reorder.
public static class ResourceOperations
{
    public static readonly string[] Names = {
        "art_lookup_decode", "land_decode", "static_art_decode", "gump_decode", "texmap_decode", "light_decode",
        "animation_uop_decode", "animation_mul_decode", "png_art", "png_gump", "png_image",
        "file_read", "file_read_at", "mapped_read_at", "chunk_load", "world_render_target", "world_render_list",
        "animation_frames", "item_create", "mobile_create", "image_from_stream", "resource_register", "resource_unregister",
        "animation_lock_wait", "resource_register_lock_wait", "resource_unregister_lock_wait", "network_processing"
    };
    // A separate ABI for aggregated, in-chunk observations. Do not reorder.
    public static readonly string[] ChunkParts = {
        "sanitize_map_index", "file_length", "get_tile_z", "apply_stretch",
        "land_create", "static_create", "tile_insert", "tile_marker"
    };
}
