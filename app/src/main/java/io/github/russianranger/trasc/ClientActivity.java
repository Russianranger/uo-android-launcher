package io.github.russianranger.trasc;

import android.app.*;
import android.content.res.ColorStateList;
import android.graphics.*;
import android.graphics.drawable.*;
import android.net.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.JSONObject;
import java.io.*;
import java.util.concurrent.*;

/** The embedded Wine display. Android Back returns to management without killing the server. */
public final class ClientActivity extends Activity {
    private ClientRuntime runtime;
    private ControllerManager controller;
    private ClientView display;
    private NativePresentation nativeDisplay;
    private volatile boolean nativeActive;
    private String presentationFallback="";
    private TextView status,layerBanner;
    private final Runnable hideLayer=()->{if(layerBanner!=null)layerBanner.animate().alpha(0f).setDuration(250).start();};
    private FrameLayout menuLayer;
    private LinearLayout menu;
    private ImageButton gear;
    private boolean menuOpen, keyboardOpen, mappingsOpen;
    private String displayError;
    private boolean failureShown;
    private int commandGeneration;
    private boolean commandPending;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable refresh=new Runnable(){@Override public void run(){
        try {
            JSONObject state=runtime.state(),launch=state.optJSONObject("launch");
            String phase=launch==null?runtime.status:launch.optString("phase").replace('_',' ');
            if(!runtime.alive())phase="Client stopped · return to Client tab to launch again";
            if(launch!=null&&launch.has("error"))phase=launch.optString("error");
            if(displayError!=null&&(launch==null||!launch.has("error")))phase=displayError;
            status.setText(phase+(launch!=null&&launch.optBoolean("native_loaded")?" · native dinput8 loaded":"")+
                (launch!=null&&launch.optBoolean("system_dinput8_loaded")?" · system DirectInput loaded":"")+"\nLayer "+controller.layerLabel()+display.measure(launch));
            if(launch!=null&&launch.has("error")&&!failureShown&&hasWindowFocus()&&!isFinishing()) {
                failureShown=true;controller.capture(false);display.input.releaseAll();setMenuOpen(true);
                new AlertDialog.Builder(ClientActivity.this).setTitle("Client startup failed").setMessage(launch.optString("error"))
                    .setPositiveButton("Back to Client",(dialog,which)->finish()).setCancelable(false).show();
            }
        }catch(Exception e){status.setText(e.getMessage());}
        handler.postDelayed(this,1000);
    }};
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);setVolumeControlStream(android.media.AudioManager.STREAM_MUSIC);runtime=ClientRuntime.get(this);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        FrameLayout layout=new FrameLayout(this);layout.setBackgroundColor(Color.BLACK);
        display=new ClientView();
        try{JSONObject state=runtime.state(),launch=state.optJSONObject("launch");nativeActive=launch!=null&&launch.optString("presentation_active").equals("native_surface");if(launch!=null)presentationFallback=launch.optString("presentation_fallback","");}catch(Exception ignored){}
        if(nativeActive){
            nativeDisplay=new NativePresentation(this,runtime.frameSocket(),new NativePresentation.Events(){
                public void failed(String reason){fallbackPresentation(reason);}
                public void size(int width,int height){display.frameWidth=width;display.frameHeight=height;display.input.size(width,height);display.arrangeSurface();}
            });layout.addView(nativeDisplay,new FrameLayout.LayoutParams(-1,-1,Gravity.CENTER));
        }
        layout.addView(display,new FrameLayout.LayoutParams(-1,-1));
        // A separate overlay never changes the framebuffer's size or touch map.
        menuLayer=new FrameLayout(this);menuLayer.setVisibility(View.GONE);
        menuLayer.setOnClickListener(v->setMenuOpen(false));
        layout.addView(menuLayer,new FrameLayout.LayoutParams(-1,-1));
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(false);
        menu=new LinearLayout(this);menu.setOrientation(LinearLayout.VERTICAL);menu.setPadding(dp(12),dp(8),dp(12),dp(12));
        menu.setBackground(panelBackground(0xd010191c));menu.setOnClickListener(v->{});
        addMenuButton("Back to Client",v->finish());
        addMenuButton("Keyboard",v->textDialog());
        addMenuButton("Controller mappings",v->controllerDialog());
        addMenuButton("Capture external mouse",v->{setMenuOpen(false);display.post(()->display.requestPointerCapture());});
        addMenuButton("Esc",v->{setMenuOpen(false);display.input.key("escape",0xff1b,true);display.input.key("escape",0xff1b,false);});
        status=new TextView(this);status.setTextColor(0xffe2eded);status.setTextSize(12);status.setPadding(dp(4),dp(10),dp(4),0);
        menu.addView(status);scroll.addView(menu);
        FrameLayout.LayoutParams panel=new FrameLayout.LayoutParams(dp(280),-2,Gravity.TOP|Gravity.RIGHT);
        panel.setMargins(dp(12),dp(68),dp(12),dp(12));menuLayer.addView(scroll,panel);
        gear=new ImageButton(this);gear.setImageResource(R.drawable.ic_client_gear);gear.setPadding(dp(12),dp(12),dp(12),dp(12));
        gear.setContentDescription("Open client controls");gear.setTooltipText("Client controls");
        gear.setBackground(new RippleDrawable(ColorStateList.valueOf(0x55ffffff),panelBackground(0x6010191c),null));
        gear.setOnClickListener(v->setMenuOpen(!menuOpen));
        FrameLayout.LayoutParams gearPosition=new FrameLayout.LayoutParams(dp(48),dp(48),Gravity.TOP|Gravity.RIGHT);
        gearPosition.setMargins(dp(12),dp(12),dp(12),0);layout.addView(gear,gearPosition);
        layerBanner=new TextView(this);layerBanner.setTextColor(0xb3ffffff);layerBanner.setTextSize(16);layerBanner.setGravity(Gravity.CENTER);layerBanner.setPadding(dp(12),dp(6),dp(12),dp(6));
        layerBanner.setBackground(panelBackground(0x28081010));layerBanner.setShadowLayer(dp(2),0,dp(1),0x66000000);layerBanner.setAlpha(0f);layerBanner.setMaxLines(1);layerBanner.setEllipsize(android.text.TextUtils.TruncateAt.END);
        layerBanner.setClickable(false);layerBanner.setFocusable(false);
        FrameLayout.LayoutParams layerPosition=new FrameLayout.LayoutParams(-2,-2,Gravity.TOP|Gravity.CENTER_HORIZONTAL);layerPosition.topMargin=dp(12);layout.addView(layerBanner,layerPosition);
        // Keep controls clear of display cutouts and temporarily revealed bars.
        layout.setOnApplyWindowInsetsListener((view,insets)->{
            int left=insets.getSystemWindowInsetLeft(),top=insets.getSystemWindowInsetTop(),right=insets.getSystemWindowInsetRight(),bottom=insets.getSystemWindowInsetBottom();
            if(Build.VERSION.SDK_INT>=28&&insets.getDisplayCutout()!=null){DisplayCutout cutout=insets.getDisplayCutout();left=Math.max(left,cutout.getSafeInsetLeft());top=Math.max(top,cutout.getSafeInsetTop());right=Math.max(right,cutout.getSafeInsetRight());bottom=Math.max(bottom,cutout.getSafeInsetBottom());}
            gearPosition.setMargins(dp(12)+left,dp(12)+top,dp(12)+right,0);gear.setLayoutParams(gearPosition);
            panel.setMargins(dp(12)+left,dp(68)+top,dp(12)+right,dp(12)+bottom);scroll.setLayoutParams(panel);
            layerPosition.topMargin=dp(12)+top;layerBanner.setMaxWidth(Math.max(dp(100),getResources().getDisplayMetrics().widthPixels-dp(140)-left-right));layerBanner.setLayoutParams(layerPosition);
            return insets;
        });
        setContentView(layout);immersive();
        controller=new ControllerManager(this,runtime.server.work,event->{
            switch(event.optString("type")) {
                case "button":if(event.optString("action").equals("ClientMenu")){setMenuOpen(true);break;}display.input.action(event.optString("action"),event.optBoolean("down"));break;
                case "pointer":display.input.move((float)event.optDouble("x"),(float)event.optDouble("y"));break;
                case "wheel":display.input.wheel(event.optInt("y"));break;
                case "layer":showLayer(event.optInt("x")+1,event.optString("action"));break;
            }
        });
        setMenuOpen(false);display.connect();handler.post(refresh);
    }
    private void showLayer(int index,String name){handler.removeCallbacks(hideLayer);layerBanner.animate().cancel();layerBanner.setText("Layer "+index+" · "+name);layerBanner.setAlpha(1f);handler.postDelayed(hideLayer,1500);}
    private int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private GradientDrawable panelBackground(int color){GradientDrawable background=new GradientDrawable();background.setColor(color);background.setCornerRadius(0);background.setStroke(dp(2),0xff9f7738);return background;}
    private void addMenuButton(String title,View.OnClickListener action){Button button=new Button(this);button.setText(title);button.setAllCaps(false);button.setTextColor(Color.WHITE);button.setMinHeight(dp(48));button.setBackground(new RippleDrawable(ColorStateList.valueOf(0x44ffffff),panelBackground(0x18ffffff),null));button.setOnClickListener(action);LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,dp(48));params.topMargin=dp(4);menu.addView(button,params);}
    private void immersive(){
        if(Build.VERSION.SDK_INT>=30){
            getWindow().setDecorFitsSystemWindows(false);
            WindowInsetsController insets=getWindow().getInsetsController();
            if(insets!=null){insets.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);insets.hide(WindowInsets.Type.systemBars());}
        }else getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY|View.SYSTEM_UI_FLAG_FULLSCREEN|View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_LAYOUT_STABLE|View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
    }
    private boolean gameInputActive(){return hasWindowFocus()&&!menuOpen&&!keyboardOpen&&!mappingsOpen&&!commandPending&&!failureShown;}
    private void setMenuOpen(boolean open){
        menuOpen=open;menuLayer.setVisibility(open?View.VISIBLE:View.GONE);
        gear.setContentDescription(open?"Close client controls":"Open client controls");gear.setAlpha(open?1f:.78f);
        if(controller!=null)controller.capture(gameInputActive());
        if(open){cancelCommand();display.releasePointerCapture();menu.getChildAt(0).requestFocus();}else display.requestFocus();
    }
    private void fallbackPresentation(String reason){
        if(!nativeActive)return;nativeActive=false;presentationFallback=reason;
        if(nativeDisplay!=null){nativeDisplay.close();nativeDisplay.setVisibility(View.GONE);}
        display.resize(display.frameWidth,display.frameHeight);
        display.send(r->r.request(false));display.invalidate();
        Toast.makeText(this,"Using current display: "+reason,Toast.LENGTH_LONG).show();
    }
    private void controllerDialog(){
        mappingsOpen=true;controller.capture(false);display.input.releaseAll();
        new ControllerDialog(this,controller,()->{mappingsOpen=false;controller.capture(gameInputActive());}).show();
    }
    private void cancelCommand(){commandGeneration++;commandPending=false;if(display!=null)display.input.releaseAll();}
    private void textDialog() {
        keyboardOpen=true;setMenuOpen(false);controller.capture(false);display.input.releaseAll();
        EditText text=new EditText(this);text.setSingleLine(true);text.setHint("Type into the focused client field");
        text.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(4096)});
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("Client keyboard").setView(text)
            .setPositiveButton("Type",(d,w)->display.input.text(text.getText().toString(),false))
            .setNeutralButton("Send + Enter",(d,w)->display.input.text(text.getText().toString(),true))
            .setNegativeButton("Cancel",null).create();
        dialog.setOnDismissListener(d->{keyboardOpen=false;display.requestFocus();immersive();controller.capture(gameInputActive());});dialog.show();
        text.requestFocus();dialog.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_VISIBLE);
    }
    @Override public boolean dispatchKeyEvent(KeyEvent event) {
        if(gameInputActive()&&controller!=null&&controller.key(event))return true;
        if(display!=null&&gameInputActive()&&event.getKeyCode()!=KeyEvent.KEYCODE_BACK&&
                (event.getSource()&InputDevice.SOURCE_KEYBOARD)==InputDevice.SOURCE_KEYBOARD) {
            int symbol=physicalSymbol(event);
            if(symbol!=0&&(event.getAction()==KeyEvent.ACTION_DOWN||event.getAction()==KeyEvent.ACTION_UP)) {
                display.input.key("physical:"+event.getKeyCode(),symbol,event.getAction()==KeyEvent.ACTION_DOWN);return true;
            }
        }
        return super.dispatchKeyEvent(event);
    }
    static int physicalSymbol(KeyEvent event) {
        switch(event.getKeyCode()) {
            case KeyEvent.KEYCODE_ENTER:return 0xff0d;case KeyEvent.KEYCODE_ESCAPE:return 0xff1b;case KeyEvent.KEYCODE_TAB:return 0xff09;case KeyEvent.KEYCODE_DEL:return 0xff08;
            case KeyEvent.KEYCODE_DPAD_LEFT:return 0xff51;case KeyEvent.KEYCODE_DPAD_UP:return 0xff52;case KeyEvent.KEYCODE_DPAD_RIGHT:return 0xff53;case KeyEvent.KEYCODE_DPAD_DOWN:return 0xff54;
            case KeyEvent.KEYCODE_SHIFT_LEFT:return 0xffe1;case KeyEvent.KEYCODE_SHIFT_RIGHT:return 0xffe2;case KeyEvent.KEYCODE_CTRL_LEFT:return 0xffe3;case KeyEvent.KEYCODE_CTRL_RIGHT:return 0xffe4;
            case KeyEvent.KEYCODE_ALT_LEFT:return 0xffe9;case KeyEvent.KEYCODE_ALT_RIGHT:return 0xffea;
            case KeyEvent.KEYCODE_MOVE_HOME:return 0xff50;case KeyEvent.KEYCODE_MOVE_END:return 0xff57;case KeyEvent.KEYCODE_PAGE_UP:return 0xff55;case KeyEvent.KEYCODE_PAGE_DOWN:return 0xff56;case KeyEvent.KEYCODE_INSERT:return 0xff63;case KeyEvent.KEYCODE_FORWARD_DEL:return 0xffff;
        }
        if(event.getKeyCode()>=KeyEvent.KEYCODE_F1&&event.getKeyCode()<=KeyEvent.KEYCODE_F12)return 0xffbe+event.getKeyCode()-KeyEvent.KEYCODE_F1;
        // Ignore Ctrl/Alt when resolving the symbol; modifiers are sent separately.
        int code=event.getUnicodeChar(event.getMetaState()&(KeyEvent.META_SHIFT_ON|KeyEvent.META_CAPS_LOCK_ON));
        return code<=255?code:code<=0x10ffff?0x01000000|code:0;
    }
    @Override public boolean dispatchGenericMotionEvent(MotionEvent event){return gameInputActive()&&controller!=null&&controller.motion(event)||super.dispatchGenericMotionEvent(event);}
    @Override public void onBackPressed(){if(display.hasPointerCapture()){display.releasePointerCapture();setMenuOpen(true);return;}if(menuOpen)setMenuOpen(false);else super.onBackPressed();}
    @Override public void onWindowFocusChanged(boolean focus){super.onWindowFocusChanged(focus);if(focus&&!keyboardOpen)immersive();if(controller!=null)controller.capture(gameInputActive());if(!focus&&display!=null){cancelCommand();}}
    @Override protected void onPause(){cancelCommand();if(controller!=null)controller.capture(false);if(display!=null)display.input.releaseAll();super.onPause();}
    @Override protected void onDestroy(){cancelCommand();handler.removeCallbacksAndMessages(null);if(layerBanner!=null)layerBanner.animate().cancel();if(controller!=null)controller.close();if(nativeDisplay!=null)nativeDisplay.close();if(display!=null)display.close();super.onDestroy();}

    private final class ClientView extends View implements RfbConnection.Screen {
        private final Object pixelsLock=new Object();
        private Bitmap bitmap;
        private int[] copyBuffer=new int[0];
        private long measuredAt=System.nanoTime();
        private double displayRate;
        private String displayCost="";
        private int frameWidth=800,frameHeight=600;
        private final Paint paint=new Paint(Paint.FILTER_BITMAP_FLAG);
        private final RectF bounds=new RectF();
        private final ExecutorService writer=Executors.newSingleThreadExecutor();
        private volatile LocalSocket socket;
        private volatile RfbConnection connection;
        private volatile LocalSocket inputSocket;
        private volatile RelativeInput relative;
        private volatile boolean closed;
        final DisplayInput input=new DisplayInput(new DisplayInput.Sink(){
            public void key(int sym,boolean down){send(r->r.key(sym,down));}
            public void pointer(int x,int y,int buttons){if(!sendRelative(0,x,y,buttons))send(r->r.pointer(x,y,buttons));}
            public boolean relative(int dx,int dy,int buttons){return sendRelative(1,dx,dy,buttons);}
            public boolean buttons(int buttons){return sendRelative(2,0,0,buttons);}
        });
        interface Send {void write(RfbConnection connection)throws IOException;}
        ClientView(){super(ClientActivity.this);setFocusable(true);setFocusableInTouchMode(true);}
        void send(Send send){if(!closed)writer.execute(()->{try{RfbConnection r=connection;if(r!=null)send.write(r);}catch(IOException e){failure(e);}});}
        boolean sendRelative(int type,int x,int y,int mask){
            if(closed||relative==null)return false;
            writer.execute(()->{try{RelativeInput target=relative;if(target!=null)target.send(type,x,y,mask);}catch(IOException e){closeInput();post(()->Toast.makeText(ClientActivity.this,"Relative input disconnected; reopen the display to restore mouse look",Toast.LENGTH_LONG).show());}});return true;
        }
        void closeInput(){relative=null;try{if(inputSocket!=null)inputSocket.close();}catch(IOException ignored){}inputSocket=null;}
        void connect(){new Thread(()->{
            try {
                LocalSocket local=new LocalSocket();socket=local;
                if(closed)return;
                local.connect(new LocalSocketAddress(runtime.displaySocket().getPath(),LocalSocketAddress.Namespace.FILESYSTEM));
                local.setSoTimeout(15000);
                RfbConnection r=new RfbConnection(local.getInputStream(),local.getOutputStream(),this);boolean frames=!nativeActive;r.handshake(frames);
                local.setSoTimeout(0);connection=r;
                try{
                    LocalSocket control=new LocalSocket();inputSocket=control;
                    control.connect(new LocalSocketAddress(new File(runtime.run,"input.sock").getPath(),LocalSocketAddress.Namespace.FILESYSTEM));control.setSoTimeout(3000);
                    relative=new RelativeInput(control.getInputStream(),control.getOutputStream());control.setSoTimeout(0);
                }catch(IOException inputError){closeInput();runtime.server.recordFailure("client_relative_input",inputError);}
                // A native failure can happen during the input-only handshake.
                if(!frames&&!nativeActive){resize(r.width,r.height);r.request(false);}
                while(!closed)r.readUpdate();
            }catch(IOException e){if(!closed)failure(e);}
            finally {closeInput();try{if(socket!=null)socket.close();}catch(IOException ignored){}connection=null;}
        },"TRASC client display").start();}
        void failure(Exception error){if(closed)return;runtime.server.recordFailure("client_display",error);post(()->{displayError="Display disconnected: "+error.getMessage()+" · Back to Client to reconnect";if(!isDestroyed()){status.setText(displayError);setMenuOpen(true);}});}
        @Override public void resize(int w,int h){frameWidth=w;frameHeight=h;synchronized(pixelsLock){if(!nativeActive)bitmap=Bitmap.createBitmap(w,h,Bitmap.Config.ARGB_8888);}post(()->{input.size(w,h);arrangeSurface();});}
        void arrangeSurface(){
            if(!nativeActive||nativeDisplay==null||getWidth()==0||getHeight()==0)return;
            float scale=Math.min((float)getWidth()/frameWidth,(float)getHeight()/frameHeight);
            int w=Math.round(frameWidth*scale),h=Math.round(frameHeight*scale);bounds.set((getWidth()-w)/2f,(getHeight()-h)/2f,(getWidth()+w)/2f,(getHeight()+h)/2f);
            android.view.ViewGroup.LayoutParams old=nativeDisplay.getLayoutParams();
            if(old.width!=w||old.height!=h)nativeDisplay.setLayoutParams(new FrameLayout.LayoutParams(w,h,Gravity.CENTER));
        }
        @Override protected void onSizeChanged(int w,int h,int oldw,int oldh){super.onSizeChanged(w,h,oldw,oldh);arrangeSurface();}
        @Override public void pixels(int x,int y,int w,int h,int[] colors){synchronized(pixelsLock){bitmap.setPixels(colors,0,w,x,y,w,h);}}
        @Override public void copy(int x,int y,int w,int h,int sx,int sy){synchronized(pixelsLock){if(copyBuffer.length<w*h)copyBuffer=new int[w*h];bitmap.getPixels(copyBuffer,0,w,sx,sy,w,h);bitmap.setPixels(copyBuffer,0,w,x,y,w,h);}}
        @Override public void updated(){postInvalidateOnAnimation();}
        @Override protected void onDraw(Canvas canvas) {
            if(nativeActive)return;
            long started=System.nanoTime();
            canvas.drawColor(Color.BLACK);
            synchronized(pixelsLock){if(bitmap!=null){float scale=Math.min((float)getWidth()/bitmap.getWidth(),(float)getHeight()/bitmap.getHeight());float w=bitmap.getWidth()*scale,h=bitmap.getHeight()*scale;bounds.set((getWidth()-w)/2,(getHeight()-h)/2,(getWidth()+w)/2,(getHeight()+h)/2);canvas.drawBitmap(bitmap,null,bounds,paint);}}
            RfbConnection r=connection;if(r!=null)r.stats.drawn(System.nanoTime()-started);
        }
        String measure(JSONObject launch) {
            RfbConnection r=connection;if(r==null||closed)return "";
            JSONObject wine=launch==null?null:launch.optJSONObject("wine_present");
            boolean fresh=wine!=null&&System.currentTimeMillis()/1000.0-wine.optDouble("sampled_at",0)<5;
            long now=System.nanoTime();
            if(now-measuredAt>=TimeUnit.SECONDS.toNanos(5)) {
                measuredAt=now;double[] sample=r.stats.sample(now);
                if(sample!=null)try {
                    displayRate=sample[2];
                    JSONObject info=new JSONObject().put("created_utc",java.time.Instant.now().toString());
                    info.put("presentation_active",nativeActive?"native_surface":"rfb").put("presentation_fallback",presentationFallback);
                    if(nativeActive&&nativeDisplay!=null){JSONObject surface=nativeDisplay.sample(now);info.put("native_surface",surface);displayRate=surface.optDouble("surface_posts_per_second");displayCost=String.format(java.util.Locale.ROOT,"\nCapture %.2f ms · copy %.2f ms · Surface wait/post %.2f ms",surface.optDouble("capture_ms_per_frame"),surface.optDouble("native_copy_ms_per_frame"),surface.optDouble("surface_lock_ms_per_frame")+surface.optDouble("surface_post_ms_per_frame"));}
                    info.put("view_width",getWidth()).put("view_height",getHeight()).put("controls_open",menuOpen).put("keyboard_open",keyboardOpen).put("window_focused",hasWindowFocus());
                    // Read Android's reported state; no scheduling/power policy changes.
                    PowerManager power=getSystemService(PowerManager.class);
                    try{if(power!=null){info.put("power_save",power.isPowerSaveMode());if(Build.VERSION.SDK_INT>=29)info.put("thermal_status",power.getCurrentThermalStatus());}}catch(RuntimeException unavailable){info.put("power_state_unavailable",true);}
                    String[] keys={"window_seconds","rfb_updates_per_second","new_bitmap_draws_per_second","receive_ms_per_update","decode_apply_ms_per_update","canvas_submit_ms_per_draw","raw_pixels_per_second","last_update_age_seconds","pixel_conversion_ms_per_update","bitmap_apply_ms_per_update","raw_bytes_per_second"};
                    for(int i=0;i<keys.length;i++)info.put(keys[i],sample[i]);
                    if(!nativeActive)displayCost=String.format(java.util.Locale.ROOT,"\nConvert %.2f ms · Bitmap %.2f ms · Canvas submit %.2f ms",sample[8],sample[9],sample[5]);
                    if(fresh)info.put("wine_present",wine);
                    if(launch!=null)info.put("graphics_threading",launch.optString("graphics_threading_observed","unknown"))
                        .put("graphics_threading_requested",launch.optString("graphics_threading","multi"))
                        .put("mesa_glthread_observed",launch.optBoolean("mesa_glthread_observed",false))
                        .put("graphics_backend",launch.optString("graphics_backend"))
                        .put("cpu_affinity",launch.optString("cpu_affinity")).put("game_fullscreen",launch.optBoolean("fullscreen")).put("display_target_fps",launch.optInt("display_target_fps",30));
                    String line=info.toString()+"\n";
                    writer.execute(()->{
                        try {
                            File log=new File(runtime.server.work,"logs/client-presentation.log");
                            if(log.length()>1024*1024)java.nio.file.Files.move(log.toPath(),new File(log.getParentFile(),"client-presentation.overflow.log").toPath(),java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                            try(FileOutputStream out=new FileOutputStream(log,true)){out.write(line.getBytes(java.nio.charset.StandardCharsets.UTF_8));}
                        }catch(IOException error){android.util.Log.w("TRASC","Could not record display measurements",error);}
                    });
                }catch(org.json.JSONException ignored){}
            }
            if(launch!=null&&launch.optString("graphics_backend").equals("turnip")) return String.format(java.util.Locale.ROOT," · DXVK HUD "+(launch.optBoolean("dxvk_hud",true)?"on":"off")+" · %s %.1f/s",nativeActive?"Native Surface":"Current display",displayRate)+displayCost;
            return String.format(java.util.Locale.ROOT," · Wine %s/s · Display %.1f/s",fresh?String.format(java.util.Locale.ROOT,"%.1f",wine.optDouble("per_second")):"—",displayRate)+displayCost;
        }
        private boolean position(MotionEvent event) {
            if((bitmap==null&&!nativeActive)||bounds.width()==0||!bounds.contains(event.getX(),event.getY()))return false;
            input.position((event.getX()-bounds.left)*frameWidth/bounds.width(),(event.getY()-bounds.top)*frameHeight/bounds.height());return true;
        }
        @Override public boolean onTouchEvent(MotionEvent event) {
            if(!gameInputActive())return true;
            boolean mouse=event.isFromSource(InputDevice.SOURCE_MOUSE);
            if(event.getActionMasked()==MotionEvent.ACTION_CANCEL){input.releaseAll();return true;}
            if(event.getActionMasked()==MotionEvent.ACTION_UP){input.mouse("touch",1,false);if(mouse)mouseButtons(event);performClick();return true;}
            if(!position(event))return true;
            if(mouse)mouseButtons(event);else if(event.getActionMasked()==MotionEvent.ACTION_DOWN){requestFocus();input.mouse("touch",1,true);}
            return true;
        }
        private void mouseButtons(MotionEvent event){int mask=event.getButtonState();input.mouse("mouse-left",1,(mask&MotionEvent.BUTTON_PRIMARY)!=0);input.mouse("mouse-right",4,(mask&MotionEvent.BUTTON_SECONDARY)!=0);input.mouse("mouse-middle",2,(mask&MotionEvent.BUTTON_TERTIARY)!=0);}
        @Override public boolean onGenericMotionEvent(MotionEvent event) {
            if(!gameInputActive())return true;
            if(event.isFromSource(InputDevice.SOURCE_MOUSE)){position(event);mouseButtons(event);if(event.getAction()==MotionEvent.ACTION_SCROLL)input.wheel(Math.round(event.getAxisValue(MotionEvent.AXIS_VSCROLL)));return true;}
            return super.onGenericMotionEvent(event);
        }
        @Override public boolean onCapturedPointerEvent(MotionEvent event){
            if(!gameInputActive()){releasePointerCapture();return true;}
            input.move(event.getX()*frameWidth/Math.max(1,getWidth()),event.getY()*frameHeight/Math.max(1,getHeight()));
            mouseButtons(event);if(event.getActionMasked()==MotionEvent.ACTION_SCROLL)input.wheel(Math.round(event.getAxisValue(MotionEvent.AXIS_VSCROLL)));return true;
        }
        @Override public void onPointerCaptureChange(boolean captured){super.onPointerCaptureChange(captured);if(!captured)input.releaseAll();}
        @Override public boolean performClick(){super.performClick();return true;}
        private void closeSocket(){closeInput();try{if(socket!=null)socket.close();}catch(IOException ignored){}}
        void close(){input.releaseAll();closed=true;writer.execute(this::closeSocket);writer.shutdown();handler.postDelayed(this::closeSocket,250);}
    }
}
