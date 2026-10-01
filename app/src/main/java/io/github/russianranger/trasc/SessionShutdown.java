package io.github.russianranger.trasc;

/** One shutdown order for launcher controls and the Android notification. */
final class SessionShutdown {
    interface Host {
        void progress(String message)throws Exception;
        void stopClient()throws Exception;
        void awaitRealmTask()throws Exception;
        void closeRuntime()throws Exception;
    }
    static void run(Host host)throws Exception {
        host.progress("Closing the client…");host.stopClient();
        host.progress("Waiting for server tasks before saving…");host.awaitRealmTask();
        host.progress("Saving the world and closing the realm…");host.closeRuntime();
        host.progress("Session saved and closed.");
    }
}
