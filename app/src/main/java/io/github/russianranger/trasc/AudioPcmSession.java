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
        default void transport(int stage,long nanos) {}
        void close();
    }
    long frames;
    private static int read(DataInputStream in)throws IOException{return Integer.reverseBytes(in.readInt());}
    private static void reply(DataOutputStream out,int value,Sink sink)throws IOException{long began=System.nanoTime();out.writeInt(Integer.reverseBytes(value));out.flush();sink.transport(3,System.nanoTime()-began);}
    void run(InputStream input,OutputStream output,Sink sink)throws IOException {
        DataInputStream in=new DataInputStream(input);DataOutputStream out=new DataOutputStream(output);
        try {
            if(read(in)!=0x50414c54||read(in)!=1||read(in)!=48000||read(in)!=2)throw new IOException("Unsupported audio stream");
            int capacity=read(in);if(capacity<64||capacity>48000)throw new IOException("Invalid audio buffer size");
            sink.configure(capacity);reply(out,0,sink);
            byte[] pcm=new byte[4096*4];
            for(;;) {
                int command;
                long began=System.nanoTime();
                try{command=read(in);}catch(EOFException end){return;}
                sink.transport(1,System.nanoTime()-began);
                switch(command) {
                    case 1:sink.start();reply(out,0,sink);break;
                    case 2:sink.stop();reply(out,0,sink);break;
                    case 3:reply(out,sink.position(),sink);break;
                    case 4:
                        began=System.nanoTime();
                        int count=read(in);if(count<1||count>4096)throw new IOException("Invalid PCM frame count");
                        in.readFully(pcm,0,count*4);
                        sink.transport(2,System.nanoTime()-began);
                        int accepted=sink.write(pcm,count*4);
                        if(accepted<0||accepted>count*4||accepted%4!=0)throw new IOException("Android audio write failed: "+accepted);
                        frames+=accepted/4;
                        reply(out,accepted/4,sink);break;
                    case 5:sink.reset();reply(out,0,sink);break;
                    default:throw new IOException("Unknown audio command");
                }
            }
        } finally {sink.close();}
    }
}
