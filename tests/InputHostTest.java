package io.github.russianranger.trasc;
import java.util.*;
public final class InputHostTest {
    static void check(boolean condition,String message){if(!condition)throw new AssertionError(message);}
    public static void main(String[] args){
        Set<String> held=new HashSet<>();List<String> events=new ArrayList<>();
        ControllerInput input=new ControllerInput(new ControllerInput.Sink(){public void button(String action,boolean down){events.add(action+":"+down);if(down)held.add(action);else held.remove(action);}public void pointer(float x,float y){}public void wheel(int n){}});
        input.activate(true);
        input.value("X",1);check(held.contains("Digit1"),"Main mapping");
        input.value("L2",1);check(input.currentLayer()==1,"LT cycles");
        input.value("X",0);input.value("L2",0);check(held.isEmpty(),"Layer changes release held outputs");
        input.value("X",1);check(held.contains("Digit8"),"Second layer mapping");
        input.activate(false);check(held.isEmpty(),"Focus loss releases keys");
        check(ControllerInput.defaults().get("LeftUp").equals("ArrowUp"),"TazUO arrow movement default");
        System.out.println("Controller layer and focus-loss checks passed");
    }
}
