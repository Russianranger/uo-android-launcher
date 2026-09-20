package io.github.russianranger.trasc;

import java.util.*;

/** Shared held-state for touch, physical keys/mouse and saved controller bindings. */
final class DisplayInput {
    interface Sink {
        void key(int symbol,boolean down);void pointer(int x,int y,int buttons);
        default boolean relative(int dx,int dy,int buttons){return false;}
        default boolean buttons(int buttons){return false;}
    }
    private final Sink sink;
    private final Map<String,Integer> keys=new HashMap<>(),buttons=new HashMap<>();
    private final Map<Integer,Integer> keyCounts=new HashMap<>();
    private float x=400,y=300;
    private int width=800,height=600;
    private float remainderX,remainderY;
    DisplayInput(Sink sink){this.sink=sink;}
    void size(int w,int h){width=w;height=h;x=Math.min(x,w-1);y=Math.min(y,h-1);}
    static int symbol(String action) {
        if(action.matches("Key[A-Z]"))return action.charAt(3)+32;
        if(action.matches("Digit[0-9]"))return action.charAt(5);
        if(action.matches("F([1-9]|1[0-2])"))return 0xffbd+Integer.parseInt(action.substring(1));
        switch(action) {
            case "NumLock":return 0xff7f;case "Space":return 32;case "Enter":return 0xff0d;case "Escape":return 0xff1b;case "Tab":return 0xff09;case "Backspace":return 0xff08;
            case "ArrowLeft":return 0xff51;case "ArrowUp":return 0xff52;case "ArrowRight":return 0xff53;case "ArrowDown":return 0xff54;
            case "ShiftLeft":return 0xffe1;case "ControlLeft":return 0xffe3;case "AltLeft":return 0xffe9;
            case "Home":return 0xff50;case "End":return 0xff57;case "PageUp":return 0xff55;case "PageDown":return 0xff56;case "Insert":return 0xff63;case "Delete":return 0xffff;
            case "Minus":return '-';case "Equal":return '=';case "BracketLeft":return '[';case "BracketRight":return ']';case "Semicolon":return ';';case "Quote":return '\'';
            case "Comma":return ',';case "Period":return '.';case "Slash":return '/';case "Backslash":return '\\';case "Backquote":return '`';default:return 0;
        }
    }
    void action(String action,boolean down) {
        if(action.startsWith("Mouse")){mouse("pad:"+action,action.equals("MouseLeft")?1:action.equals("MouseRight")?4:2,down);return;}
        int sym=symbol(action);
        if(sym>='a'&&sym<='z'&&keyCounts.containsKey(0xffe1))sym-=32;
        key("pad:"+action,sym,down);
    }
    void key(String source,int symbol,boolean down) {
        if(down) {
            if(symbol==0||keys.containsKey(source))return;
            keys.put(source,symbol);int count=keyCounts.getOrDefault(symbol,0)+1;keyCounts.put(symbol,count);if(count==1)sink.key(symbol,true);
        } else {
            Integer held=keys.remove(source);if(held==null)return;
            int count=keyCounts.get(held)-1;
            if(count==0){keyCounts.remove(held);sink.key(held,false);}else keyCounts.put(held,count);
        }
    }
    private int mask(){int mask=0;for(int button:buttons.values())mask|=button;return mask;}
    void mouse(String source,int button,boolean down){if(down)buttons.put(source,button);else buttons.remove(source);sendPointer(mask());}
    void move(float dx,float dy){
        float tx=remainderX+dx,ty=remainderY+dy;int ix=(int)tx,iy=(int)ty;
        if(sink.relative(ix,iy,mask())){remainderX=tx-ix;remainderY=ty-iy;x=Math.max(0,Math.min(width-1,x+dx));y=Math.max(0,Math.min(height-1,y+dy));}
        else{remainderX=remainderY=0;position(x+dx,y+dy);}
    }
    void position(float px,float py){x=Math.max(0,Math.min(width-1,px));y=Math.max(0,Math.min(height-1,py));sink.pointer(Math.round(x),Math.round(y),mask());}
    private void sendPointer(int mask){if(!sink.buttons(mask))sink.pointer(Math.round(x),Math.round(y),mask);}
    void wheel(int amount){for(int i=0;i<Math.min(10,Math.abs(amount));i++){sendPointer(mask()|(amount>0?8:16));sendPointer(mask());}}
    void text(String value,boolean enter) {
        value.codePoints().forEach(cp->{int sym=cp=='\n'?0xff0d:cp=='\t'?0xff09:cp<=255?cp:0x01000000|cp;sink.key(sym,true);sink.key(sym,false);});
        if(enter){sink.key(0xff0d,true);sink.key(0xff0d,false);}
    }
    void releaseAll(){for(int sym:new ArrayList<>(keyCounts.keySet()))sink.key(sym,false);keys.clear();keyCounts.clear();buttons.clear();remainderX=remainderY=0;sendPointer(0);}
}
