using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using SDL3;

// Real pinned FNA, SDL and FNA3D. Model TazUO's FillGameObjectList followed by
// DrawRenderList, injecting window exposure while the list is being drawn.
sealed class PaintGame : Game
{
    readonly List<int> renderList = new List<int>();
    int depth;
    public int NestedDraws, Draws, Exposures;

    public PaintGame()
    {
        new GraphicsDeviceManager(this) {
            PreferredBackBufferWidth = 640, PreferredBackBufferHeight = 480,
            SynchronizeWithVerticalRetrace = false
        };
        IsFixedTimeStep = false;
    }

    protected override void Draw(GameTime time)
    {
        depth++;
        try
        {
            Draws++;
            if (depth > 1) NestedDraws++;
            renderList.Clear();
            renderList.AddRange(new[] { 1, 2, 3 });
            GraphicsDevice.Clear(Color.CornflowerBlue);
            foreach (int item in renderList)
            {
                if (item == 1 && depth == 1 && Draws > 2 && Exposures < 64)
                {
                    Exposures++;
                    var evt = new SDL.SDL_Event();
                    evt.type = (uint) SDL.SDL_EventType.SDL_EVENT_WINDOW_EXPOSED;
                    evt.window.windowID = SDL.SDL_GetWindowID(Window.Handle);
                    // With the filter enabled this synchronously redraws and
                    // consumes the event. With it disabled the loop polls it.
                    SDL.SDL_PushEvent(ref evt);
                }
            }
            if (Draws >= 160) Exit();
        }
        finally { depth--; }
    }
}

static class Program
{
    static int Main()
    {
        bool fixedPolicy = Environment.GetEnvironmentVariable("FNA_WIN32_IGNORE_WM_PAINT") == "1";
        using var game = new PaintGame();
        try { game.Run(); }
        catch (InvalidOperationException e)
        {
            Console.WriteLine(e);
            if (!fixedPolicy && game.NestedDraws > 0 && e.StackTrace.Contains("MoveNext"))
            {
                Console.WriteLine("FNA_PAINT_REENTRANCY_REPRODUCED nested=" + game.NestedDraws);
                return 23;
            }
            return 2;
        }
        if (fixedPolicy && game.NestedDraws == 0 && game.Exposures == 64 && game.Draws >= 160)
        {
            Console.WriteLine("FNA_PAINT_SERIALIZED_OK exposures=" + game.Exposures + " draws=" + game.Draws);
            return 0;
        }
        Console.WriteLine("Unexpected result: nested=" + game.NestedDraws + " exposures=" + game.Exposures + " draws=" + game.Draws);
        return 3;
    }
}
