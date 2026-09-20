package io.github.russianranger.trasc;

import java.io.*;

/** Bounded playback protocol shared by the Android sink and JVM regression. */
final class AudioPcmSession {
    interface Sink extends AutoCloseable {
        void configure(int frames) throws IOException;
        void start() throws IOException;
        void stop() throws IOException;
        void reset() throws IOException;
        int position() throws IOException;
        int write(byte[] bytes,int length) throws IOException;
        void close();
    }
    long frames, nonzeroSamples;
    private static int read(DataInputStream in)throws IOException{return Integer.reverseBytes(in.readInt());}
    private static void reply(DataOutputStream out,int value)throws IOException{out.writeInt(Integer.reverseBytes(value));out.flush();}
    void run(InputStream input,OutputStream output,Sink sink)throws IOException {
        DataInputStream in=new DataInputStream(input);DataOutputStream out=new DataOutputStream(output);
        try {
            if(read(in)!=0x50414c54||read(in)!=1||read(in)!=48000||read(in)!=2)throw new IOException("Unsupported audio stream");
            int capacity=read(in);if(capacity<64||capacity>48000)throw new IOException("Invalid audio buffer size");
            sink.configure(capacity);reply(out,0);
            byte[] pcm=new byte[4096*4];
            for(;;) {
                int command;
                try{command=read(in);}catch(EOFException end){return;}
                switch(command) {
                    case 1:sink.start();reply(out,0);break;
                    case 2:sink.stop();reply(out,0);break;
                    case 3:reply(out,sink.position());break;
                    case 4:
                        int count=read(in);if(count<1||count>4096)throw new IOException("Invalid PCM frame count");
                        in.readFully(pcm,0,count*4);
                        int accepted=sink.write(pcm,count*4);
                        if(accepted<0||accepted>count*4||accepted%4!=0)throw new IOException("Android audio write failed: "+accepted);
                        frames+=accepted/4;
                        for(int i=0;i<accepted;i+=2)if(pcm[i]!=0||pcm[i+1]!=0)nonzeroSamples++;
                        reply(out,accepted/4);break;
                    case 5:sink.reset();reply(out,0);break;
                    default:throw new IOException("Unknown audio command");
                }
            }
        } finally {sink.close();}
    }
}
