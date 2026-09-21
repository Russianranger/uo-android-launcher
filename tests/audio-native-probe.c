/* Exercise the real ALSA plug conversion, ring negotiation and partial writes. */
#include <alsa/asoundlib.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#define OK(expr) do { int e=(expr); if(e<0){fprintf(stderr,"%s: %s\n",#expr,snd_strerror(e));exit(1);} } while(0)
int main(int argc,char **argv) {
    (void)argc;
    snd_pcm_t *pcm; snd_pcm_hw_params_t *hw; unsigned period_us=10000,periods=4,rate=48000;
    int floating=argv[1][0]=='f';
    OK(snd_pcm_open(&pcm,"default",SND_PCM_STREAM_PLAYBACK,SND_PCM_NONBLOCK));
    snd_pcm_hw_params_alloca(&hw); OK(snd_pcm_hw_params_any(pcm,hw));
    OK(snd_pcm_hw_params_set_access(pcm,hw,SND_PCM_ACCESS_RW_INTERLEAVED));
    OK(snd_pcm_hw_params_set_format(pcm,hw,floating?SND_PCM_FORMAT_FLOAT_LE:SND_PCM_FORMAT_S16_LE));
    OK(snd_pcm_hw_params_set_channels(pcm,hw,2));
    OK(snd_pcm_hw_params_set_rate_near(pcm,hw,&rate,NULL));
    OK(snd_pcm_hw_params_set_period_time_near(pcm,hw,&period_us,NULL));
    OK(snd_pcm_hw_params_set_periods_near(pcm,hw,&periods,NULL));
    OK(snd_pcm_hw_params(pcm,hw));
    snd_pcm_uframes_t buffer,period;
    OK(snd_pcm_hw_params_get_buffer_size(hw,&buffer)); OK(snd_pcm_hw_params_get_period_size(hw,&period,NULL));
    if(period<960||buffer<3840){fprintf(stderr,"Too little jitter tolerance: %lu %lu\n",period,buffer);return 2;}
    snd_pcm_sw_params_t *sw; snd_pcm_sw_params_alloca(&sw);
    OK(snd_pcm_sw_params_current(pcm,sw)); OK(snd_pcm_sw_params_set_start_threshold(pcm,sw,1)); OK(snd_pcm_sw_params(pcm,sw));
    OK(snd_pcm_prepare(pcm));
    short samples[48000];float floats[48000];
    for(int i=0;i<24000;i++){short v=(short)((i%401-200)*64);samples[i*2]=v;samples[i*2+1]=-v;floats[i*2]=v/32768.f;floats[i*2+1]=-v/32768.f;}
    size_t done=0;int retries=0;
    while(done<24000){
        size_t n=24000-done;if(n>480)n=480;
        const void *data=floating?(const void *)(floats+2*done):(const void *)(samples+2*done);
        snd_pcm_sframes_t sent=snd_pcm_writei(pcm,data,n);
        if(sent==-EAGAIN){if(++retries>10000)return 3;usleep(1000);continue;}
        OK(sent);done+=sent;
    }
    OK(snd_pcm_nonblock(pcm,0)); OK(snd_pcm_drain(pcm)); OK(snd_pcm_close(pcm));
    printf("ALSA_%s_OK period=%lu buffer=%lu frames=%zu\n",floating?"FLOAT":"S16",period,buffer,done);return 0;
}
