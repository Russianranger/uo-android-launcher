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
    readonly bool replaceFilter;
    SDL.SDL_EventFilter clientFilter;
    public int FilterExposures;
    public int NestedDraws, Draws, Exposures;

    public PaintGame(bool replaceFilter)
    {
        this.replaceFilter = replaceFilter;
        new GraphicsDeviceManager(this) {
            PreferredBackBufferWidth = 640, PreferredBackBufferHeight = 480,
            SynchronizeWithVerticalRetrace = false
        };
        IsFixedTimeStep = false;
    }

    protected override unsafe void Initialize()
    {
        if (replaceFilter)
        {
            // TazUO GameController.Initialize replaces FNA's filter, rather
            // than chaining it. Its HandleSdlEvent has no EXPOSED case and
            // returns true. Model that exact exposure-event behavior here;
            // this fixture does not model the client's other input handlers.
            clientFilter = (_, evt) => {
                if (evt != null && evt->type == (uint) SDL.SDL_EventType.SDL_EVENT_WINDOW_EXPOSED)
                    FilterExposures++;
                return true;
            };
            SDL.SDL_SetEventFilter(clientFilter, IntPtr.Zero);
        }
        base.Initialize();
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
    static int Main(string[] args)
    {
        bool fixedPolicy = Environment.GetEnvironmentVariable("FNA_WIN32_IGNORE_WM_PAINT") == "1";
        bool replaceFilter = Array.IndexOf(args, "--tazuo-filter") >= 0;
        using var game = new PaintGame(replaceFilter);
        try { game.Run(); }
        catch (InvalidOperationException e)
        {
            Console.WriteLine(e);
            if (!replaceFilter && !fixedPolicy && game.NestedDraws > 0 && e.StackTrace.Contains("MoveNext"))
            {
                Console.WriteLine("FNA_PAINT_REENTRANCY_REPRODUCED nested=" + game.NestedDraws);
                return 23;
            }
            return 2;
        }
        if ((fixedPolicy || replaceFilter) && game.NestedDraws == 0 && game.Exposures == 64 && game.Draws >= 160)
        {
            if (replaceFilter)
            {
                if (game.FilterExposures < 64) return 4;
                Console.WriteLine("TAZUO_FILTER_REPLACEMENT_OK policy=" + (fixedPolicy ? "1" : "0") +
                    " filtered_exposures=" + game.FilterExposures + " nested=" + game.NestedDraws);
            }
            Console.WriteLine("FNA_PAINT_SERIALIZED_OK exposures=" + game.Exposures + " draws=" + game.Draws);
            return 0;
        }
        Console.WriteLine("Unexpected result: nested=" + game.NestedDraws + " exposures=" + game.Exposures + " draws=" + game.Draws);
        return 3;
    }
}
