'use strict';
const $=id=>document.getElementById(id),pending=new Map();let sequence=0,polling=false,currentTab='realm',lastExport='',nativeState={},clientState={};
function call(operation,args={}){return new Promise((resolve,reject)=>{const id=String(++sequence);pending.set(id,{resolve,reject});if(window.Memento)Memento.call(id,operation,JSON.stringify(args));else{pending.delete(id);reject(new Error('Open this screen inside UO Memento.'));}});}
window.nativeReply=(id,value)=>{const p=pending.get(id);if(!p)return;pending.delete(id);value.ok?p.resolve(value.result):p.reject(new Error(value.error));};
function notice(text,error=false){$('notice').textContent=text;$('notice').classList.toggle('error',error);}
function options(mode='client'){return{runtime_backend:'fex-arm64ec-1',mode,renderer:$('renderer').value,resolution:$('resolution').value,presentation_mode:$('presentation').value,display_fps:Number($('fps').value),audio:$('audio').checked,gump_space:$('gump-space').checked,managed_diagnostics:$('managed-diagnostics').checked,render_trace:$('render-trace').checked,sdl_graphics_fixes:$('sdl-graphics-fixes').checked};}
function saveOptions(){localStorage.setItem('launch',JSON.stringify(options()));}
try{const v=JSON.parse(localStorage.getItem('launch')||'{}');for(const [key,id]of[['renderer','renderer'],['resolution','resolution'],['presentation_mode','presentation'],['display_fps','fps']])if(v[key]&&(key!=='renderer'||v.runtime_backend==='fex-arm64ec-1'))$(id).value=v[key];if(typeof v.audio==='boolean')$('audio').checked=v.audio;}catch(_){}
try{const v=JSON.parse(localStorage.getItem('launch')||'{}');$('gump-space').checked=$('resolution').value==='1280x720'&&v.gump_space!==false;}catch(_){}
try{const v=JSON.parse(localStorage.getItem('launch')||'{}');$('render-trace').checked=v.runtime_backend==='fex-arm64ec-1'&&v.render_trace===true;}catch(_){}
try{const v=JSON.parse(localStorage.getItem('launch')||'{}');$('managed-diagnostics').checked=v.runtime_backend==='fex-arm64ec-1'&&v.managed_diagnostics===true;}catch(_){}
try{const v=JSON.parse(localStorage.getItem('launch')||'{}');$('sdl-graphics-fixes').checked=v.runtime_backend==='fex-arm64ec-1'&&v.sdl_graphics_fixes===true;}catch(_){}
$('gump-space').addEventListener('change',()=>{if($('gump-space').checked)$('resolution').value='1280x720';saveOptions();});
$('resolution').addEventListener('change',()=>{if($('resolution').value!=='1280x720')$('gump-space').checked=false;saveOptions();});
for(const id of['renderer','presentation','fps','audio','sdl-graphics-fixes','render-trace','managed-diagnostics'])$(id).addEventListener('change',saveOptions);
document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{currentTab=button.dataset.tab;document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.id===currentTab));document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('selected',b===button));if(currentTab==='journal')readLog().catch(e=>notice(e.message,true));}));
async function exportFile(path){await call('export',{path});notice('File exported.');}
async function readLog(){const r=await call('logs',{name:$('log-name').value});const selected=$('log-name').value;$('log-name').replaceChildren();for(const name of r.names){const o=document.createElement('option');o.textContent=name;$('log-name').append(o);}if(r.names.includes(selected))$('log-name').value=selected;$('log-text').textContent=r.text||'No log output yet.';}
async function action(name){
    if(name==='read_log')return readLog();
    if(name==='export_logs'){const result=await call(name);return exportFile(result.file);}
    const args=name==='pull_compile'?{ref:$('source-ref').value.trim()}:name==='client_start'?options():name==='desktop'?options('desktop'):{};
    const result=await call(name==='desktop'?'client_start':name,args);
    if(result&&result.id)notice('Task started. Progress appears in the quest journal.');else notice(result.message||result.status||'Ready.');
    if(name==='client_start'||name==='desktop'){
        for(let i=0;i<60;i++){await new Promise(r=>setTimeout(r,500));const state=await call('client_native_state');if(state.launch?.error)throw new Error(state.launch.error);if(state.display_ready){await call('client_view');break;}if(!state.alive)throw new Error('Client stopped. Open the Journal for logs.');}
    }
    await refresh();
}
document.querySelectorAll('[data-action]').forEach(button=>button.addEventListener('click',async()=>{button.disabled=true;try{await action(button.dataset.action);}catch(e){notice(e.message,true);}finally{button.disabled=false;}}));
document.querySelectorAll('[data-pick]').forEach(button=>button.addEventListener('click',async()=>{
    if(button.dataset.pick==='world'&&!confirm('Restore this world backup? Your current world will be backed up first.'))return;
    button.disabled=true;try{const r=await call('pick',{kind:button.dataset.pick});notice(r.message||'Import queued. Watch the quest journal.');await refresh();}catch(e){notice(e.message,true);}finally{button.disabled=false;}
}));
const seenErrors=new Set();
async function refresh(){
    if(polling||document.hidden)return;polling=true;
    try{
        [nativeState,clientState]=await Promise.all([call('native_state'),call('client_native_state')]);
        $('runtime-status').textContent=nativeState.status;$('storage').textContent=(nativeState.free_bytes/1073741824).toFixed(1)+' GB free';
        $('client-status').textContent=clientState.launch?.error||(clientState.alive?(clientState.launch?.phase||clientState.status):clientState.status);
        const trace=clientState.launch?.render_trace;
        $('render-trace-status').textContent=!trace?'':trace.active?'Last launch: render crash tracing active.':trace.action==='restored_original'?'Last launch: original client DLL restored.':trace.requested?'Last launch: tracing unavailable for this client build.':'Last launch: render tracing off.';
        const graphics=clientState.launch?.sdl_graphics;
        $('sdl-graphics-status').textContent=!graphics?'':graphics.active_version==='3.4.16'?'Last launch: SDL 3.4.16 active.':graphics.action==='restored_original'?'Last launch: original graphics library restored.':graphics.action==='unchanged_unrecognized_libraries'?'Last launch: this client’s graphics libraries were left as imported.':'Last launch: original graphics library active.';
        if(nativeState.alive){
            const state=await call('state');$('server-badge').textContent=state.running?'ONLINE':'OFFLINE';$('server-badge').classList.toggle('online',state.running);
            if(state.build)$('build-info').textContent='Built '+state.build.revision.slice(0,12)+' · '+state.build.ref;
            if(state.client)$('client-info').textContent=state.client.executable+' · '+state.client.architecture+' · '+(state.client.self_contained?'Bundled .NET':'.NET '+state.client.dotnet_version);
            $('tasks').replaceChildren();
            for(const job of state.jobs.slice().reverse()){
                const row=document.createElement('div');row.className='task '+job.status;row.textContent=job.status.toUpperCase()+' · '+job.message;$('tasks').append(row);
                if(job.status==='error'&&!seenErrors.has(job.id)){seenErrors.add(job.id);notice(job.error,true);}
                if(job.result?.file&&job.result.file!==lastExport){lastExport=job.result.file;const button=document.createElement('button');button.textContent='Export '+job.result.file.split('/').pop();button.addEventListener('click',()=>exportFile(job.result.file).catch(e=>notice(e.message,true)));$('exports').prepend(button);}
            }
            if(!state.jobs.length)$('tasks').textContent='No tasks yet.';
        }else{$('server-badge').textContent='OFFLINE';$('server-badge').classList.remove('online');}
    }catch(e){notice(e.message,true);}finally{polling=false;}
}
setInterval(refresh,2000);refresh();
