# Exact-build music enumeration cache

This is an offline Mono.Cecil patch generator. It accepts only the Assets DLL hash in `Program.cs`, adds one private cached array and helper, replaces the Directory.GetFiles call in GetTrueFileName, and clears the cache at Load/ClearResources entry. It keeps the original matching code and directory enumeration order.

Run `scripts/check-music-cache.sh` in the dotnet-wine CI environment to fetch checksum-pinned public fixture DLLs, regenerate/structurally verify the output, validate the shipped delta and execute the actual loader under .NET/Wine. Only the base64 BSDIFF delta is shipped in the APK. The standalone source equivalent is `patches/tazuo-music-cache.patch`.

Input: `1dd53cf0eea718aefeda33fba105c9797b138188be22562b47548c310524100d`.
Output: `84340a487aeae33c0f17ae1b20a0c8d1b54122d1e23801e5a582452c7db905c9`.

Original symbols are retained on device for restoration but not referenced by the rewritten assembly: injected IL changes method offsets. The verifier checks all original fields/constants/resources and every method; only the three intended methods may change. The enum Constant resolver is shared with the existing render patcher.
