package io.github.russianranger.trasc;

import android.content.Context;
import android.media.*;
import android.net.*;
import android.os.Handler;
import android.os.Looper;
import android.os.Build;
import android.system.Os;
import java.io.*;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.*;

/** App-private ALSA to AudioTrack bridge. No TCP, capture device or root access. */
final class AudioBridge implements AutoCloseable {
    private final File path,log;
    private final LocalSocket bound=new LocalSocket();
    private LocalServerSocket server;
    private final Set<Connection> connections=new HashSet<>();
    private volatile boolean closed;
    private volatile float volume=1;
    private final AudioManager manager;
    private final AudioFocusRequest focus;
    private final AudioAttributes attributes=new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_GAME).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build();
    private int opened;

    static AudioBridge start(Context context,File path,File log)throws Exception {
        AudioBridge bridge=new AudioBridge(context,path,log);
        try{bridge.listen();return bridge;}catch(Exception e){bridge.close();throw e;}
    }
    private AudioBridge(Context context,File path,File log)throws IOException {
        this.path=path;this.log=log;manager=(AudioManager)context.getSystemService(Context.AUDIO_SERVICE);
        focus=new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN).setAudioAttributes(attributes)
            .setOnAudioFocusChangeListener(change->{
                volume=change==AudioManager.AUDIOFOCUS_GAIN?1:change==AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK?.2f:0;
                synchronized(connections){for(Connection c:connections)c.volume(volume);}
                record("focus="+change);
            },new Handler(Looper.getMainLooper())).build();
        LogRetention.rotate(log);
    }
    private void listen()throws Exception {
        Files.deleteIfExists(path.toPath());
        bound.bind(new LocalSocketAddress(path.getPath(),LocalSocketAddress.Namespace.FILESYSTEM));
        Os.chmod(path.getPath(),0600);server=new LocalServerSocket(bound.getFileDescriptor());
        int granted=manager.requestAudioFocus(focus);volume=granted==AudioManager.AUDIOFOCUS_REQUEST_GRANTED?1:0;
        record("bridge=alsa-audiotrack protocol=1 rate=48000 channels=2 focus="+granted+" media_volume="+manager.getStreamVolume(AudioManager.STREAM_MUSIC));
        Thread listener=new Thread(()->{
            try {
                while(!closed) {
                    LocalSocket socket=server.accept();
                    synchronized(connections) {
                        if(closed||connections.size()>=8||socket.getPeerCredentials().getUid()!=android.os.Process.myUid()){socket.close();continue;}
                        Connection c=new Connection(socket);connections.add(c);opened++;
                        Thread worker=new Thread(c,"client-audio-playback");worker.setDaemon(true);worker.start();
                    }
                }
            } catch(Exception e){if(!closed)record("listener_error="+e);}
        },"client-audio-listener");listener.setDaemon(true);listener.start();
    }
    private synchronized void record(String text) {
        try {
            if(log.length()>256*1024)return;
            try(FileWriter out=new FileWriter(log,true)){out.write(java.time.Instant.now()+" "+text+"\n");}
        }catch(IOException ignored){}
    }
    private final class Connection implements Runnable,AudioPcmSession.Sink {
        final LocalSocket socket;AudioTrack track;int capacity;boolean ended;
        long submitted,nonzero,nextReport;boolean firstSignal;
        Connection(LocalSocket socket){this.socket=socket;}
        public void run(){
            AudioPcmSession session=new AudioPcmSession();
            try{session.run(socket.getInputStream(),socket.getOutputStream(),this);}
            catch(Exception e){if(!closed)record("stream_error="+e);}
            finally{close();synchronized(connections){connections.remove(this);}record("stream_closed frames="+session.frames+" nonzero_samples="+session.nonzeroSamples);}
        }
        public synchronized void configure(int frames)throws IOException{capacity=frames;reset();}
        public synchronized void reset()throws IOException {
            if(ended)throw new IOException("Audio stream closed");
            if(track!=null){track.release();track=null;}
            int minimum=AudioTrack.getMinBufferSize(48000,AudioFormat.CHANNEL_OUT_STEREO,AudioFormat.ENCODING_PCM_16BIT);
            if(minimum<=0)throw new IOException("Stereo audio format unavailable");
            track=new AudioTrack.Builder().setAudioAttributes(attributes)
                .setAudioFormat(new AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT).setSampleRate(48000).setChannelMask(AudioFormat.CHANNEL_OUT_STEREO).build())
                .setTransferMode(AudioTrack.MODE_STREAM).setBufferSizeInBytes(Math.max(minimum,capacity*4)).build();
            if(track.getState()!=AudioTrack.STATE_INITIALIZED)throw new IOException("Could not initialize Android audio");
            configureBuffer();submitted=nonzero=nextReport=0;firstSignal=false;
            track.setVolume(volume);
            record("stream_config producer_frames="+capacity+" minimum_bytes="+minimum+
                " buffer_frames="+track.getBufferSizeInFrames()+" allocated_frames="+track.getBufferCapacityInFrames()+
                " start_frames="+threshold());
        }
        private int threshold(){return Build.VERSION.SDK_INT>=31?track.getStartThresholdInFrames():track.getBufferSizeInFrames();}
        private void configureBuffer()throws IOException {
            AudioBufferPolicy.configure(new AudioBufferPolicy.Track(){
                public int resize(int frames){return track.setBufferSizeInFrames(frames);}
                public int startThreshold(int frames){return Build.VERSION.SDK_INT>=31?track.setStartThresholdInFrames(frames):track.getBufferSizeInFrames();}
            },capacity,Build.VERSION.SDK_INT>=31);
        }
        public synchronized void start()throws IOException{if(track!=null){configureBuffer();track.play();record("stream_start queued_frames="+submitted+" start_frames="+threshold());}}
        public synchronized void stop(){if(track!=null){report("stream_stop");track.pause();track.flush();submitted=nonzero=0;}}
        private void report(String event){record(event+" written="+submitted+" played="+Integer.toUnsignedLong(track.getPlaybackHeadPosition())+
            " nonzero_samples="+nonzero+" underruns="+track.getUnderrunCount()+" state="+track.getPlayState()+" volume="+volume);}
        public synchronized int position()throws IOException {
            if(track==null)throw new IOException("Audio stream closed");
            long now=android.os.SystemClock.elapsedRealtime();
            if(now>=nextReport){
                // Routing can enlarge Android's buffers after creation. Reapply the producer limit.
                if(track.getBufferSizeInFrames()>capacity||threshold()>capacity)configureBuffer();
                report("stream_progress");nextReport=now+5000;
            }
            return track.getPlaybackHeadPosition();
        }
        public synchronized int write(byte[] bytes,int length)throws IOException {
            if(track==null)throw new IOException("Audio stream closed");
            int accepted=track.write(bytes,0,length,AudioTrack.WRITE_NON_BLOCKING);
            if(accepted>0){submitted+=accepted/4;for(int i=0;i+1<accepted;i+=2)if(bytes[i]!=0||bytes[i+1]!=0)nonzero++;
                if(nonzero>0&&!firstSignal){firstSignal=true;record("stream_first_signal written="+submitted);}}
            return accepted;
        }
        synchronized void volume(float value){if(track!=null)track.setVolume(value);}
        public synchronized void close(){ended=true;if(track!=null){if(track.getState()==AudioTrack.STATE_INITIALIZED)report("stream_release");track.release();track=null;}try{socket.close();}catch(IOException ignored){}}
    }
    public void close() {
        if(closed)return;closed=true;
        try{if(server!=null)server.close();}catch(IOException ignored){}
        try{bound.close();}catch(IOException ignored){}
        synchronized(connections){for(Connection c:connections)c.close();connections.clear();}
        manager.abandonAudioFocusRequest(focus);path.delete();record("bridge_closed streams="+opened);
    }
}
