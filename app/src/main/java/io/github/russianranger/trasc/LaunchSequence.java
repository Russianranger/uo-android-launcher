package io.github.russianranger.trasc;

/** Every stage must report ready before the next stage may run. */
final class LaunchSequence {
    interface Host {
        void checkSetup(boolean withClient)throws Exception;
        void progress(String message)throws Exception;
        void openRuntime()throws Exception;
        void awaitServer()throws Exception;
        void awaitClient()throws Exception;
    }
    static void run(Host host,boolean withClient)throws Exception {
        host.checkSetup(withClient);
        host.progress("Opening realm runtime…");
        host.openRuntime();
        host.progress("Starting server · waiting for the world to be ready…");
        host.awaitServer();
        if(withClient){
            host.progress("Starting client · preparing display and controls…");
            host.awaitClient();
        }
        host.progress(withClient?"Your world is ready.":"Server ready · 127.0.0.1:2593");
    }
}
