package io.github.russianranger.trasc;

public final class ClientReadinessHostTest {
    private static void check(boolean condition,String message){if(!condition)throw new AssertionError(message);}
    public static void main(String[] args){
        // Reported race: Xvnc socket exists before either helper is configured.
        check(!ClientReadiness.ready(true,false,false,true,"",false,"",false),"Xvnc alone opened the display early");
        check(!ClientReadiness.ready(true,false,false,true,"native_surface",true,"",false),"Native setup bypassed input readiness");
        check(!ClientReadiness.ready(true,true,false,true,"native_surface",false,"relative_xtest",true),"Missing native socket accepted");
        check(!ClientReadiness.ready(true,true,false,true,"native_surface",true,"relative_xtest",false),"Missing input socket accepted");
        check(ClientReadiness.ready(true,true,false,true,"native_surface",true,"relative_xtest",true),"Fully prepared native display rejected");
        check(ClientReadiness.ready(true,true,false,true,"rfb",false,"absolute_rfb",false),"Intentional helper fallback rejected");
        check(ClientReadiness.ready(true,true,false,true,"rfb",false,"relative_xtest",true),"Standard display with relative input rejected");
        check(!ClientReadiness.ready(false,true,false,true,"native_surface",true,"relative_xtest",true),"Stale sockets accepted after stop");
        check(!ClientReadiness.ready(true,true,true,true,"native_surface",true,"relative_xtest",true),"Failed launch accepted");
        check(!ClientReadiness.ready(true,true,false,true,"rfb",false,"",true),"Unresolved input accepted");
        System.out.println("Display readiness: early socket race, native/input helpers, fallback and stopped sessions passed");
    }
}
