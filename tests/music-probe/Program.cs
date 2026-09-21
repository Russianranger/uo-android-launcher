using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;

if (args.Length != 2) throw new ArgumentException("original-folder patched-folder");
string root=Path.Combine(Path.GetTempPath(),"memento-music-"+Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
void Check(bool condition,string why){if(!condition)throw new Exception(why);}
string MakeData(string name){
    string path=Path.Combine(root,name);Directory.CreateDirectory(Path.Combine(path,"Music","A"));Directory.CreateDirectory(Path.Combine(path,"Music","B"));
    foreach(var file in new[]{"A/Stones.mp3","B/stones.mp3","A/stone1.mp3","B/stone2.mp3","A/sailing.mp3","B/seaa.mp3"})
        File.WriteAllBytes(Path.Combine(path,"Music",file),new byte[]{1});
    File.WriteAllBytes(Path.Combine(path,"sound.mul"),new byte[64]);
    using(var index=new BinaryWriter(File.Create(Path.Combine(path,"soundidx.mul")))){index.Write(0);index.Write(64);index.Write(0);}
    File.WriteAllText(Path.Combine(path,"Music","Config.txt"),"0 StOnEs loop\n1 sailing\n2 missing\n3 stone[12]\n4 sea+\n");
    return path;
}
// Both assemblies see the same directory enumeration order. No game process,
// native audio or graphics library is initialized by this lookup probe.
string assets=MakeData("assets");
var original=new Fixture(args[0],assets);var updated=new Fixture(args[1],assets);
original.Load();updated.Load();
foreach(string name in new[]{"StOnEs","sailing","missing","stone[12]","sea+","stone1"})
    Check(original.Lookup(name)==updated.Lookup(name),"Changed lookup semantics: "+name);
for(int i=0;i<5;i++)Check(original.Music(i)==updated.Music(i),"Config result differs: "+i);
object cached=updated.Cache();Check(cached is string[],"No enumeration cache created");
for(int i=0;i<200;i++)updated.Lookup(i%2==0?"sailing":"stone1");
Check(ReferenceEquals(cached,updated.Cache()),"Repeated lookup replaced the cached enumeration");
File.WriteAllBytes(Path.Combine(assets,"Music","A","Fresh.mp3"),new byte[]{1});
Check(original.Lookup("fresh")=="Fresh.mp3"&&updated.Lookup("fresh")=="fresh","Lookup rescanned within one load");
updated.Clear();Check(updated.Cache()==null,"ClearResources retained the cache");
Check(updated.Lookup("fresh")=="Fresh.mp3","Cleared cache did not refresh");
File.WriteAllBytes(Path.Combine(assets,"Music","A","NewTrack.mp3"),new byte[]{1});
updated.Load();Check(!ReferenceEquals(cached,updated.Cache()),"Load reused an old enumeration");
Check(updated.Lookup("newtrack")=="NewTrack.mp3","Reload missed a newly added track");
string other=MakeData("other");File.WriteAllBytes(Path.Combine(other,"Music","A","OtherTrack.mp3"),new byte[]{1});
updated.BasePath(other);updated.Load();Check(updated.Lookup("othertrack")=="OtherTrack.mp3","Reload failed to use the new asset path");
updated.Clear();Directory.Move(Path.Combine(other,"Music"),Path.Combine(other,"Music-hidden"));
try{updated.Lookup("missing");throw new Exception("Missing-directory failure was swallowed");}catch(TargetInvocationException e)when(e.InnerException is DirectoryNotFoundException){}
Console.WriteLine("MUSIC_CACHE_OK actual_assembly=true config_matching=true regex_semantics=true cached_enumeration=true reload=true clear=true missing_directory=true");

sealed class ClientContext(string root):AssemblyLoadContext(true){
    protected override Assembly Load(AssemblyName name){string file=Path.Combine(root,name.Name+".dll");return File.Exists(file)?LoadFromAssemblyPath(file):null;}
}
sealed class Fixture {
    readonly object sounds,manager;readonly Type type,managerType;
    public Fixture(string folder,string assets){
        var context=new ClientContext(Path.GetFullPath(folder));var assembly=context.LoadFromAssemblyPath(Path.GetFullPath(Path.Combine(folder,"ClassicUO.Assets.dll")));
        type=assembly.GetType("ClassicUO.Assets.SoundsLoader",true);managerType=assembly.GetType("ClassicUO.Assets.UOFileManager",true);
        manager=RuntimeHelpers.GetUninitializedObject(managerType);BasePath(assets);
        var map=managerType.GetField("_overrideMap",BindingFlags.Instance|BindingFlags.NonPublic);
        map.SetValue(manager,Activator.CreateInstance(map.FieldType,true));
        sounds=Activator.CreateInstance(type,manager);
    }
    public void BasePath(string path)=>managerType.GetField("<BasePath>k__BackingField",BindingFlags.Instance|BindingFlags.NonPublic).SetValue(manager,path);
    public string Lookup(string name)=>(string)type.GetMethod("GetTrueFileName",BindingFlags.Instance|BindingFlags.NonPublic).Invoke(sounds,new object[]{name});
    public void Load(){type.GetMethod("Load").Invoke(sounds,null);}
    public void Clear(){type.GetMethod("ClearResources").Invoke(sounds,null);}
    public object Cache()=>type.GetField("_mementoMusicFiles",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(sounds);
    public string Music(int index){object[] args={index,null,false};var found=type.GetMethod("TryGetMusicData").Invoke(sounds,args);return $"{found}|{args[1]}|{args[2]}";}
}
