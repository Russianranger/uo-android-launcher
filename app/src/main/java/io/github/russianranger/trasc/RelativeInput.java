package io.github.russianranger.trasc;

import java.io.*;
import java.nio.charset.StandardCharsets;

/** Small private-socket XTest protocol, separate from RFB's absolute pointer. */
final class RelativeInput {
    private final DataOutputStream out;
    RelativeInput(InputStream input,OutputStream output)throws IOException {
        byte[] hello=new byte[8];new DataInputStream(input).readFully(hello);
        if(!new String(hello,StandardCharsets.US_ASCII).equals("TRASCIN1"))throw new IOException("Unsupported relative input protocol");
        out=new DataOutputStream(output);
    }
    synchronized void send(int type,int x,int y,int mask)throws IOException {
        if(type<0||type>2||Math.abs((long)x)>4096||Math.abs((long)y)>4096||mask<0||mask>31)throw new IOException("Invalid pointer event");
        out.writeInt(type);out.writeInt(x);out.writeInt(y);out.writeInt(mask);out.flush();
    }
}
