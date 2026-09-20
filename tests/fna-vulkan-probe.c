/* Exercise TazUO 5.2's actual FNA3D.dll with both original and updated SDL.
 * This checks Wine ABI / render-target lifetime, not Android or game stability.
 */
#define SDL_MAIN_HANDLED
#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "FNA3D.h"

#define LOAD(name) \
    FARPROC raw##name = GetProcAddress(fna, "FNA3D_" #name); \
    __typeof__(&FNA3D_##name) p##name; \
    _Static_assert(sizeof(p##name) == sizeof(raw##name), "Function pointer size"); \
    memcpy(&p##name, &raw##name, sizeof(p##name)); \
    if (!p##name) return 3
#define REQUIRE(expr) do { if (!(expr)) { fprintf(stderr, "FAIL %s: %s\n", #expr, SDL_GetError()); return 2; } } while (0)
static void log_message(const char *message) { puts(message); fflush(stdout); }
static void log_error(const char *message) { fprintf(stderr, "FNA ERROR: %s\n", message); exit(4); }

int main(void) {
    SDL_SetMainReady();
    REQUIRE(SDL_Init(SDL_INIT_VIDEO));
    SDL_SetHint("FNA3D_FORCE_DRIVER", "Vulkan");
    HMODULE fna = LoadLibraryA("FNA3D.dll");
    REQUIRE(fna);
    LOAD(HookLogFunctions); LOAD(PrepareWindowAttributes); LOAD(CreateDevice);
    LOAD(LinkedVersion);
    LOAD(DestroyDevice); LOAD(CreateTexture2D); LOAD(AddDisposeTexture);
    LOAD(SetRenderTargets); LOAD(Clear); LOAD(GetTextureData2D);
    LOAD(SwapBuffers); LOAD(ResetBackbuffer); LOAD(SetViewport); LOAD(SetScissorRect);
    pHookLogFunctions(log_message, log_message, log_error);
    printf("Graphics fixture SDL=%d FNA3D=%u\n", SDL_GetVersion(), pLinkedVersion());
    fflush(stdout);
    SDL_Window *window = SDL_CreateWindow("TazUO graphics compatibility", 640, 480, pPrepareWindowAttributes());
    REQUIRE(window);
    FNA3D_PresentationParameters pp = {0};
    pp.backBufferWidth = 640; pp.backBufferHeight = 480;
    pp.backBufferFormat = FNA3D_SURFACEFORMAT_COLOR;
    pp.deviceWindowHandle = window;
    pp.presentationInterval = FNA3D_PRESENTINTERVAL_IMMEDIATE;
    FNA3D_Device *device = pCreateDevice(&pp, 0);
    REQUIRE(device);
    for (int frame = 0; frame < 120; frame++) {
        if (frame % 20 == 0) {
            pp.backBufferWidth = (frame % 40 == 0) ? 640 : 1280;
            pp.backBufferHeight = (frame % 40 == 0) ? 480 : 720;
            REQUIRE(SDL_SetWindowSize(window, pp.backBufferWidth, pp.backBufferHeight));
            SDL_PumpEvents();
            pResetBackbuffer(device, &pp);
        }
        int width = (frame % 2) ? 1098 : 640, height = (frame % 2) ? 720 : 480;
        FNA3D_Texture *textures[16];
        for (int n = 0; n < 16; n++) {
            textures[n] = pCreateTexture2D(device, FNA3D_SURFACEFORMAT_COLOR, width, height, 1, 1);
            REQUIRE(textures[n]);
        }
        FNA3D_RenderTargetBinding binding = {0};
        binding.twod.width = width; binding.twod.height = height;
        binding.levelCount = 1; binding.texture = textures[frame % 16];
        pSetRenderTargets(device, &binding, 1, NULL, FNA3D_DEPTHFORMAT_NONE, 0);
        FNA3D_Viewport viewport = {0, 0, width, height, 0.0f, 1.0f};
        FNA3D_Rect scissor = {0, 0, width, height};
        pSetViewport(device, &viewport); pSetScissorRect(device, &scissor);
        FNA3D_Vec4 color = {(frame % 2) ? 1.0f : 0.0f, 0.0f, 0.0f, 1.0f};
        pClear(device, FNA3D_CLEAROPTIONS_TARGET, &color, 1.0f, 0);
        pSetRenderTargets(device, NULL, 0, NULL, FNA3D_DEPTHFORMAT_NONE, 0);
        unsigned char pixel[4] = {42, 42, 42, 42};
        pGetTextureData2D(device, binding.texture, 0, 0, 1, 1, 0, pixel, sizeof(pixel));
        REQUIRE(pixel[0] == ((frame % 2) ? 255 : 0) && pixel[1] == 0 && pixel[2] == 0 && pixel[3] == 255);
        for (int n = 0; n < 16; n++) pAddDisposeTexture(device, textures[n]);
        pSwapBuffers(device, NULL, NULL, window);
        SDL_PumpEvents();
    }
    pDestroyDevice(device);
    SDL_DestroyWindow(window);
    printf("FNA_VULKAN_LIFETIME_OK SDL=%d targets=1920 resizes=6 readbacks=120\n", SDL_GetVersion());
    SDL_Quit();
    return 0;
}
