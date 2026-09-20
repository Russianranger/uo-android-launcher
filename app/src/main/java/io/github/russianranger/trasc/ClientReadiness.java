package io.github.russianranger.trasc;

/** A display socket alone does not mean presentation and input are configured. */
final class ClientReadiness {
    static boolean ready(boolean alive, boolean publishedReady, boolean failed,
                         boolean displaySocket, String presentation, boolean frameSocket,
                         String pointer, boolean inputSocket) {
        if (!alive || !publishedReady || failed || !displaySocket) return false;
        if ("native_surface".equals(presentation)) {
            if (!frameSocket) return false;
        } else if (!"rfb".equals(presentation)) return false;
        if ("relative_xtest".equals(pointer)) return inputSocket;
        return "absolute_rfb".equals(pointer);
    }
}
