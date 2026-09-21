/* Real imported SDL -> Wine WASAPI -> ALSA -> Android PCM protocol fixture.
 * Synthetic stereo tones only; never reads client assets or records a device.
 */
#define SDL_MAIN_HANDLED
#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define REQUIRE(x) do { if (!(x)) { fprintf(stderr,"FAIL %s: %s\n",#x,SDL_GetError()); return 2; } } while (0)
int main(void) {
    SDL_SetMainReady();
    REQUIRE(SDL_Init(SDL_INIT_AUDIO));
    REQUIRE(SDL_GetCurrentAudioDriver() && !strcmp(SDL_GetCurrentAudioDriver(),"wasapi"));
    SDL_AudioSpec spec={SDL_AUDIO_F32,2,48000};
    SDL_AudioStream *stream=SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK,&spec,NULL,NULL);
    REQUIRE(stream);
    int frames=48000*4;
    float *pcm=malloc((size_t)frames*2*sizeof(float));REQUIRE(pcm);
    for(int i=0;i<frames;i++) {
        pcm[i*2]=(float)(.25*sin(2*3.141592653589793*440*i/48000));
        pcm[i*2+1]=(float)(.25*sin(2*3.141592653589793*660*i/48000));
    }
    REQUIRE(SDL_PutAudioStreamData(stream,pcm,frames*2*(int)sizeof(float)));
    REQUIRE(SDL_ResumeAudioStreamDevice(stream));
    SDL_Delay(5000);
    REQUIRE(SDL_GetAudioStreamQueued(stream)==0);
    SDL_DestroyAudioStream(stream);SDL_Quit();free(pcm);
    puts("SDL_WASAPI_AUDIO_OK original SDL, float stereo, four seconds drained");
    return 0;
}
