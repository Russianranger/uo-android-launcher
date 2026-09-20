package io.github.russianranger.trasc;

import android.app.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.util.*;

/** Edits the same named-layer profile as the Client tab without closing the game. */
final class ControllerDialog {
    private final Activity activity;
    private final ControllerManager controller;
    private final Runnable dismissed;
    private JSONObject draft;
    private LinearLayout root,rows;
    private Spinner layer;
    private EditText layerName,deadzone,speed;
    private int editing;
    ControllerDialog(Activity activity,ControllerManager controller,Runnable dismissed){this.activity=activity;this.controller=controller;this.dismissed=dismissed;}
    private void label(String text){TextView v=new TextView(activity);v.setText(text);v.setPadding(8,12,8,4);root.addView(v);}
    private Spinner spinner(List<String> choices){Spinner s=new Spinner(activity);s.setAdapter(new ArrayAdapter<>(activity,android.R.layout.simple_spinner_dropdown_item,choices));root.addView(s);return s;}
    private void button(String text,Runnable action){Button b=new Button(activity);b.setText(text);b.setOnClickListener(v->action.run());root.addView(b);}
    private JSONArray layers(){return draft.optJSONArray("layers");}
    void show(){
        try{draft=controller.state();}catch(JSONException e){dismissed.run();return;}
        root=new LinearLayout(activity);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(20,8,20,12);
        label("Thor defaults: LT cycles Main → Hotbar 2 → Spells → Inventory. Bind Next/Previous, Go to layer, or Hold layer to any button. Hold returns to the selected layer when released. Inherit uses Main. Changes apply only on Save.");
        Spinner preset=spinner(Arrays.asList("Thor defaults / cycling","Alternate hotbars","Alternate spell keys","Alternate inventory / cursor","Original bindings"));
        button("Apply preset to editor",()->{try{draft=ControllerManager.preset(new String[]{"thor","adventure","spells","inventory","legacy"}[preset.getSelectedItemPosition()]);editing=0;fill();}catch(JSONException ignored){}});
        label("Edit layer");layer=spinner(Collections.singletonList("Main"));
        layer.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onItemSelected(AdapterView<?> p,View v,int pos,long id){if(pos<layers().length()){editing=pos;render();}}public void onNothingSelected(AdapterView<?> p){}});
        layerName=new EditText(activity);layerName.setSingleLine(true);layerName.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(24)});root.addView(layerName);
        button("Rename layer",()->{try{layers().getJSONObject(editing).put("name",layerName.getText().toString().trim());fillLayers();}catch(JSONException ignored){}});
        button("Add layer (up to 6)",()->{try{
            if(layers().length()>=ControllerInput.MAX_LAYERS){Toast.makeText(activity,"Maximum 6 layers",Toast.LENGTH_SHORT).show();return;}
            int number=layers().length()+1;String name="Layer "+number;while(hasName(name))name="Layer "+(++number);layers().put(new JSONObject().put("name",name).put("bindings",new JSONObject(ControllerInput.inherited())));editing=layers().length()-1;fillLayers();
        }catch(JSONException ignored){}});
        button("Remove selected layer",()->{try{
            if(editing==0){Toast.makeText(activity,"Main provides inherited bindings and cannot be removed",Toast.LENGTH_SHORT).show();return;}
            int removed=editing;layers().remove(removed);
            for(int i=0;i<layers().length();i++){JSONObject map=layers().getJSONObject(i).getJSONObject("bindings");for(String source:ControllerInput.SOURCES){String action=map.getString(source);int target=ControllerInput.layerTarget(action);if(target==removed)map.put(source,"None");else if(target>removed)map.put(source,(action.startsWith("Hold")?"HoldLayer":"Layer")+target);}}
            editing=Math.min(editing,layers().length()-1);fillLayers();
        }catch(JSONException ignored){}});
        label("Stick deadzone (0.05–0.80)");deadzone=new EditText(activity);deadzone.setInputType(8194);root.addView(deadzone);
        label("Pointer speed (50–2500 pixels/sec)");speed=new EditText(activity);speed.setInputType(2);root.addView(speed);
        rows=new LinearLayout(activity);rows.setOrientation(LinearLayout.VERTICAL);root.addView(rows);fill();
        ScrollView scroll=new ScrollView(activity);scroll.addView(root);
        AlertDialog dialog=new AlertDialog.Builder(activity).setTitle("Controller mappings").setView(scroll).setPositiveButton("Save",null).setNegativeButton("Cancel",null).create();
        dialog.setOnDismissListener(d->dismissed.run());dialog.show();
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{try{
            layers().getJSONObject(editing).put("name",layerName.getText().toString().trim());
            draft.put("deadzone",Double.parseDouble(deadzone.getText().toString())).put("sensitivity",Double.parseDouble(speed.getText().toString()));controller.configure(draft,true);dialog.dismiss();
        }catch(Exception e){Toast.makeText(activity,e.getMessage(),Toast.LENGTH_LONG).show();}});
    }
    private boolean hasName(String name){for(int i=0;i<layers().length();i++)if(name.equalsIgnoreCase(layers().optJSONObject(i).optString("name")))return true;return false;}
    private void fill(){deadzone.setText(draft.optString("deadzone"));speed.setText(draft.optString("sensitivity"));fillLayers();}
    private void fillLayers(){List<String> names=new ArrayList<>();for(int i=0;i<layers().length();i++)names.add((i+1)+" · "+layers().optJSONObject(i).optString("name"));layer.setAdapter(new ArrayAdapter<>(activity,android.R.layout.simple_spinner_dropdown_item,names));layer.setSelection(editing);render();}
    private String actionLabel(String action){
        int target=ControllerInput.layerTarget(action);
        if(target>=0)return (action.startsWith("Hold")?"Hold: ":"Go to: ")+layers().optJSONObject(target).optString("name");
        if(action.equals("LayerNext"))return "Next layer";if(action.equals("LayerPrevious"))return "Previous layer";
        return action.replace("ShiftLeft+","Shift + ").replace("ControlLeft+","Ctrl + ").replace("AltLeft+","Alt + ").replace("Digit","Number ").replace("Key","Key ");
    }
    private void render(){
        if(rows==null||layerName==null)return;rows.removeAllViews();JSONObject selected=layers().optJSONObject(editing);if(selected==null)return;layerName.setText(selected.optString("name"));JSONObject map=selected.optJSONObject("bindings");
        List<String> choices=new ArrayList<>();if(editing>0)choices.add("Inherit");for(String a:ControllerInput.ACTIONS)if(ControllerInput.layerTarget(a)<layers().length())choices.add(a);
        List<String> labels=new ArrayList<>();for(String a:choices)labels.add(actionLabel(a));
        for(String source:ControllerInput.SOURCES){TextView label=new TextView(activity);label.setText(ControllerInput.sourceLabel(source));rows.addView(label);
            Spinner s=new Spinner(activity);s.setContentDescription(source+" layer "+(editing+1)+" binding");s.setAdapter(new ArrayAdapter<>(activity,android.R.layout.simple_spinner_dropdown_item,labels));s.setSelection(Math.max(0,choices.indexOf(map.optString(source))));rows.addView(s);
            s.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onItemSelected(AdapterView<?> p,View v,int pos,long id){try{map.put(source,choices.get(pos));}catch(JSONException ignored){}}public void onNothingSelected(AdapterView<?> p){}});
        }
    }
}
