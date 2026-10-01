package io.github.russianranger.trasc;

import java.io.IOException;
import java.util.*;

public final class SessionShutdownHostTest {
    public static void main(String[] args)throws Exception {
        for(int failing=-1;failing<3;failing++){
            List<String> events=new ArrayList<>();final int failure=failing;
            SessionShutdown.Host host=new SessionShutdown.Host(){
                void step(int index,String name)throws Exception {events.add(name);if(index==failure)throw new IOException(name+" failed");}
                public void progress(String message){}
                public void stopClient()throws Exception {step(0,"client");}
                public void awaitRealmTask()throws Exception {step(1,"wait");}
                public void closeRuntime()throws Exception {step(2,"save-close");}
            };
            try{SessionShutdown.run(host);if(failure>=0)throw new AssertionError("Failure swallowed");}
            catch(IOException expected){if(failure<0)throw expected;}
            List<String> order=Arrays.asList("client","wait","save-close");
            if(!events.equals(order.subList(0,failure<0?3:failure+1)))throw new AssertionError("Shutdown continued after a failed stage: "+events);
        }
        SessionActions actions=new SessionActions();actions.beginShutdown();
        try{try{actions.beginShutdown();throw new AssertionError("Duplicate shutdown accepted");}catch(IOException expected){}actions.progress("Still closing");}
        finally{actions.finish();}
        actions.begin("New session");actions.finish();
        System.out.println("Session shutdown: ordered close, save failure preservation and duplicate shutdown rejection passed");
    }
}
