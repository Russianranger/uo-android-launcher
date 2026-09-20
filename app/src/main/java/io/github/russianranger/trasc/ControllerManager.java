package io.github.russianranger.trasc;

import android.content.Context;
import android.hardware.input.InputManager;
import android.os.*;
import android.view.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Android gamepad adapter. Captures only while the client surface has focus. */
final class ControllerManager implements InputManager.InputDeviceListener {
    interface Events {void emit(JSONObject event);}
    private final File profile;
    private final Events events;
    private final InputManager manager;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final ControllerInput input;
    private List<ControllerInput.Layer> layers=ControllerInput.defaultLayers();
    private long lastTick;
    private String loadError="";
    private int device=-1;
    private final Map<String,Float> digital=new HashMap<>(),analog=new HashMap<>();
    private final Runnable tick=new Runnable(){@Override public void run(){long now=SystemClock.uptimeMillis();input.tick((now-lastTick)/1000f);lastTick=now;handler.postDelayed(this,16);}};
    ControllerManager(Context context,File work,Events events) {
        this.events=events;profile=new File(work,"client/controller.json");
        input=new ControllerInput(new ControllerInput.Sink(){
            public void button(String action,boolean down){emit("button",action,down,0,0);}
            public void pointer(float dx,float dy){emit("pointer","",false,dx,dy);}
            public void wheel(int amount){emit("wheel","",false,0,amount);}
            public void layer(int index,String name){emit("layer",name,false,index,0);}
        });
        reload();
        manager=(InputManager)context.getSystemService(Context.INPUT_SERVICE);manager.registerInputDeviceListener(this,handler);
    }
    private void emit(String type,String action,boolean down,float x,float y) {
        try{events.emit(new JSONObject().put("type",type).put("action",action).put("down",down).put("x",x).put("y",y));}catch(JSONException ignored){}
    }
    void reload() {
        capture(false);layers=ControllerInput.defaultLayers();input.configure(layers,.20f,700);loadError="";
        if(profile.isFile())try {
            if(profile.length()>131072)throw new IOException("Controller profile exceeds limits");
            configure(new JSONObject(new String(Files.readAllBytes(profile.toPath()),StandardCharsets.UTF_8)),false);
        } catch(Exception e){loadError="Saved controller profile could not be loaded: "+e.getMessage();}
    }
    private static JSONObject serialize(List<ControllerInput.Layer> layers,float deadzone,float speed)throws JSONException {
        JSONArray array=new JSONArray();for(ControllerInput.Layer layer:layers)array.put(new JSONObject().put("name",layer.name).put("bindings",new JSONObject(layer.bindings)));
        return new JSONObject().put("format",2).put("layers",array).put("deadzone",deadzone).put("sensitivity",speed);
    }
    JSONObject state()throws JSONException {
        return serialize(layers,input.deadzone,input.sensitivity).put("sources",new JSONArray(ControllerInput.SOURCES))
            .put("actions",new JSONArray(ControllerInput.ACTIONS)).put("presets",presets()).put("active",input.active()).put("error",loadError)
            .put("current_layer",input.currentLayer()).put("current_layer_name",input.layerName()).put("max_layers",ControllerInput.MAX_LAYERS);
    }
    String layerLabel(){return (input.currentLayer()+1)+"/"+input.layerCount()+" · "+input.layerName();}
    static JSONObject preset(String name)throws JSONException {
        if(name.equals("thor"))return serialize(ControllerInput.defaultLayers(),.2f,700);
        return serialize(ControllerInput.legacyLayers(ControllerInput.preset(name,false),ControllerInput.preset(name,true),name.equals("legacy")?"None":"L1"),.2f,name.equals("inventory")?450:700);
    }
    private JSONObject presets()throws JSONException {JSONObject p=new JSONObject();for(String name:new String[]{"thor","legacy","adventure","spells","inventory"})p.put(name,preset(name));return p;}
    private static Map<String,String> bindings(JSONObject raw)throws JSONException {
        Map<String,String> result=new LinkedHashMap<>();for(String key:ControllerInput.SOURCES)result.put(key,raw.getString(key));return result;
    }
    void configure(JSONObject data,boolean save)throws Exception {
        List<ControllerInput.Layer> next=new ArrayList<>();
        if(data.has("layers")){
            if(data.optInt("format",2)!=2)throw new IOException("Unsupported controller profile version");
            JSONArray array=data.getJSONArray("layers");
            for(int i=0;i<array.length();i++){JSONObject layer=array.getJSONObject(i);next.add(new ControllerInput.Layer(layer.getString("name").trim(),bindings(layer.getJSONObject("bindings"))));}
        }else{
            Map<String,String> alternate=data.has("shifted")?bindings(data.getJSONObject("shifted")):ControllerInput.inherited();
            next=ControllerInput.legacyLayers(bindings(data.getJSONObject("bindings")),alternate,data.optString("modifier","None"));
        }
        float deadzone=(float)data.getDouble("deadzone"),speed=(float)data.getDouble("sensitivity");
        // Validate before changing disk or the active profile. Older saved maps migrate without replacing custom keys.
        ControllerInput check=new ControllerInput(new ControllerInput.Sink(){public void button(String a,boolean b){}public void pointer(float x,float y){}public void wheel(int v){}});
        check.configure(next,deadzone,speed);
        if(save){
            byte[] encoded=serialize(next,deadzone,speed).toString(2).getBytes(StandardCharsets.UTF_8);
            if(encoded.length>131072)throw new IOException("Controller profile exceeds limits");
            profile.getParentFile().mkdirs();File temp=new File(profile.getParentFile(),"controller.json.new");
            try(FileOutputStream out=new FileOutputStream(temp)){out.write(encoded);out.getFD().sync();}
            Files.move(temp.toPath(),profile.toPath(),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
        }
        capture(false);input.configure(next,deadzone,speed);layers=next;loadError="";
    }
    void capture(boolean active){input.activate(false);digital.clear();analog.clear();input.activate(active);device=-1;handler.removeCallbacks(tick);if(active){lastTick=SystemClock.uptimeMillis();handler.post(tick);}emit("capture","",active,0,0);}
    boolean active(){return input.active();}
    boolean accepts(InputEvent event) {
        if(!input.active())return false;
        if(!event.isFromSource(InputDevice.SOURCE_GAMEPAD)&&!event.isFromSource(InputDevice.SOURCE_JOYSTICK)&&!event.isFromSource(InputDevice.SOURCE_DPAD))return false;
        if(device<0)device=event.getDeviceId();return device==event.getDeviceId();
    }
    boolean key(KeyEvent event) {
        if(!accepts(event))return false;
        String source;
        switch(event.getKeyCode()) {
            case KeyEvent.KEYCODE_BUTTON_A:source="A";break;case KeyEvent.KEYCODE_BUTTON_B:source="B";break;
            case KeyEvent.KEYCODE_BUTTON_X:source="X";break;case KeyEvent.KEYCODE_BUTTON_Y:source="Y";break;
            case KeyEvent.KEYCODE_BUTTON_L1:source="L1";break;case KeyEvent.KEYCODE_BUTTON_R1:source="R1";break;
            case KeyEvent.KEYCODE_BUTTON_L2:source="L2";break;case KeyEvent.KEYCODE_BUTTON_R2:source="R2";break;
            case KeyEvent.KEYCODE_BUTTON_THUMBL:source="L3";break;case KeyEvent.KEYCODE_BUTTON_THUMBR:source="R3";break;
            case KeyEvent.KEYCODE_BUTTON_START:source="Start";break;case KeyEvent.KEYCODE_BUTTON_SELECT:source="Select";break;
            case KeyEvent.KEYCODE_DPAD_UP:source="DpadUp";break;case KeyEvent.KEYCODE_DPAD_DOWN:source="DpadDown";break;
            case KeyEvent.KEYCODE_DPAD_LEFT:source="DpadLeft";break;case KeyEvent.KEYCODE_DPAD_RIGHT:source="DpadRight";break;
            default:return false;
        }
        if(event.getAction()==KeyEvent.ACTION_DOWN||event.getAction()==KeyEvent.ACTION_UP){digital.put(source,event.getAction()==KeyEvent.ACTION_DOWN?1f:0f);input.value(source,Math.max(digital.get(source),analog.getOrDefault(source,0f)));}
        return true;
    }
    boolean motion(MotionEvent event) {
        if(event.getAction()!=MotionEvent.ACTION_MOVE||!accepts(event))return false;
        input.axis("LeftLeft","LeftRight",event.getAxisValue(MotionEvent.AXIS_X));input.axis("LeftUp","LeftDown",event.getAxisValue(MotionEvent.AXIS_Y));
        InputDevice pad=event.getDevice();boolean alternate=pad!=null&&pad.getMotionRange(MotionEvent.AXIS_Z)==null&&pad.getMotionRange(MotionEvent.AXIS_RX)!=null;
        input.axis("RightLeft","RightRight",event.getAxisValue(alternate?MotionEvent.AXIS_RX:MotionEvent.AXIS_Z));input.axis("RightUp","RightDown",event.getAxisValue(alternate?MotionEvent.AXIS_RY:MotionEvent.AXIS_RZ));
        analogValue("DpadLeft",Math.max(0,-event.getAxisValue(MotionEvent.AXIS_HAT_X)));analogValue("DpadRight",Math.max(0,event.getAxisValue(MotionEvent.AXIS_HAT_X)));
        analogValue("DpadUp",Math.max(0,-event.getAxisValue(MotionEvent.AXIS_HAT_Y)));analogValue("DpadDown",Math.max(0,event.getAxisValue(MotionEvent.AXIS_HAT_Y)));
        analogValue("L2",Math.max(event.getAxisValue(MotionEvent.AXIS_LTRIGGER),event.getAxisValue(MotionEvent.AXIS_BRAKE)));
        analogValue("R2",Math.max(event.getAxisValue(MotionEvent.AXIS_RTRIGGER),event.getAxisValue(MotionEvent.AXIS_GAS)));
        return true;
    }
    private void analogValue(String source,float value){analog.put(source,value);input.value(source,Math.max(value,digital.getOrDefault(source,0f)));}
    @Override public void onInputDeviceAdded(int id){}
    @Override public void onInputDeviceChanged(int id){if(device==id)capture(false);}
    @Override public void onInputDeviceRemoved(int id){if(device==id)capture(false);}
    void close(){capture(false);manager.unregisterInputDeviceListener(this);}
}
