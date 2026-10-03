using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using Memento;

if(args.Length!=2)throw new ArgumentException("fixture-folder native-shim");
var folder=Path.GetFullPath(args[0]);
AssemblyLoadContext.Default.Resolving+=(_,name)=>{var p=Path.Combine(folder,name.Name+".dll");return File.Exists(p)?AssemblyLoadContext.Default.LoadFromAssemblyPath(p):null;};
var fna=AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(folder,"FNA.dll"));
var native=NativeLibrary.Load(Path.GetFullPath(args[1]));NativeLibrary.SetDllImportResolver(fna,(_,_,_)=>native);
var type=fna.GetType("Microsoft.Xna.Framework.Graphics.FNA3D",true)!;
const BindingFlags Static=BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic;
var count=Marshal.GetDelegateForFunctionPointer<Count>(NativeLibrary.GetExport(native,"TestCount"));
var arg=Marshal.GetDelegateForFunctionPointer<Arg>(NativeLibrary.GetExport(native,"TestArg"));
void Check(bool ok,string why){if(!ok)throw new Exception(why);}
object Call(string name,params object[] values)=>type.GetMethod("FNA3D_"+name,Static)!.Invoke(null,values)!;
var texture=type.GetMethod("FNA3D_CreateTexture2D",Static)!;var format=Enum.ToObject(texture.GetParameters()[1].ParameterType,7);
var result=(IntPtr)Call("CreateTexture2D",new IntPtr(0x10000),format,24,32,3,(byte)1);
Check(result.ToInt64()==0x87654321&&count()==1&&arg(0,0)==0x10000&&arg(0,1)==7&&arg(0,2)==24&&arg(0,3)==32&&arg(0,4)==3&&arg(0,5)==1,"Return value/texture native ABI changed");
object[] effectArgs={new IntPtr(0x10001),new byte[]{11,22,33,44},4,IntPtr.Zero,IntPtr.Zero};Call("CreateEffect",effectArgs);
Check(count()==2&&arg(1,0)==0x10001&&arg(1,1)==11&&arg(1,2)==44&&arg(1,3)==4&&(IntPtr)effectArgs[3]==new IntPtr(0x12345678)&&(IntPtr)effectArgs[4]==new IntPtr(0xabcdef12),"Array marshalling/out handles changed");
object[] cloneArgs={new IntPtr(0x10002),effectArgs[3],IntPtr.Zero,IntPtr.Zero};Call("CloneEffect",cloneArgs);
Check(count()==3&&arg(2,0)==0x10002&&arg(2,1)==0x12345678&&(IntPtr)cloneArgs[2]==new IntPtr(0x12345679)&&(IntPtr)cloneArgs[3]==new IntPtr(0xabcdef13),"Clone effect out handles changed");
Check(ColdTrace.Enabled,"Diagnostic observer was not activated");
Console.WriteLine("GRAPHICS_BOUNDARY_OK actual_fna=true calls_once=true return_value=true byte_array=true out_handles=true");
[UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int Count();
[UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Arg(int call,int index);
