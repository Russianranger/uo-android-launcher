'use strict';
const setupSessionActions=new Set(['pull_compile','compile_server','session_backup','load_session_backups']);
let stagedServerSource=null,pendingSessionRestore=null,sessionBackupLoading=false;

function sourceOptions(strict=false){
    const source=$('source-kind').value,ref=$('source-ref').value.trim();
    const value={source,ref};
    if(strict&&(!ref||ref.length>160))throw Error('Enter a branch, tag or commit for the server source.');
    if(source==='custom'){
        value.repository=$('source-repository').value.trim();
        if(strict){
            let url;try{url=new URL(value.repository);}catch(_){throw Error('Enter an HTTPS Git repository URL, such as https://github.com/owner/repository.git.');}
            if(value.repository.length>2048||url.protocol!=='https:'||!url.hostname||url.username||url.password||url.search||url.hash||!url.pathname.replaceAll('/',''))throw Error('Use an HTTPS Git repository URL without credentials, a query or a fragment.');
        }
    }
    return value;
}
function saveSourceOptions(){localStorage.setItem('realm-source',JSON.stringify(sourceOptions()));}
function showSourceFields(){
    $('custom-source').hidden=$('source-kind').value!=='custom';
    $('source-repository').required=$('source-kind').value==='custom';
}
function applySourceOptions(value){
    if(!value||typeof value!=='object')return;
    $('source-kind').value=['upstream','fork','custom'].includes(value.source)?value.source:'upstream';
    $('source-ref').value=typeof value.ref==='string'&&value.ref?value.ref:'main';
    $('source-repository').value=typeof value.repository==='string'?value.repository:'';
    showSourceFields();saveSourceOptions();
}
try{applySourceOptions(JSON.parse(localStorage.getItem('realm-source')||'null'));}catch(_){}
showSourceFields();
$('source-kind').addEventListener('change',()=>{showSourceFields();saveSourceOptions();});
for(const id of ['source-repository','source-ref'])$(id).addEventListener('input',saveSourceOptions);

function renderServerSource(source){
    if(source!==undefined)stagedServerSource=source&&Object.keys(source).length?source:null;
    if(!stagedServerSource){
        $('server-source-info').textContent='Choose a source to download and compile.';
        $('offline-source-status').textContent='Import a source ZIP or pull a server source before compiling.';
        return;
    }
    const value=stagedServerSource,kind=value.source||value.kind||value.type;
    const label=kind==='zip'||kind==='offline'?'Imported ZIP':kind==='upstream'?'Upstream':kind==='fork'?'My source':kind==='custom'?'Custom source':'Staged source';
    const details=[value.repository||value.name||value.archive,value.ref,value.revision?.slice(0,12)].filter(Boolean);
    const text=label+(details.length?' · '+details.join(' · '):'');
    $('server-source-info').textContent='Staged: '+text;
    $('offline-source-status').textContent='Ready to compile: '+text+'. Compiling preserves your saves.';
}
function setupSessionControls(locked){
    for(const id of ['source-kind','source-ref','source-repository'])$(id).disabled=!!locked;
    document.querySelector('[data-action="compile_server"]').disabled=!!locked||!stagedServerSource;
    $('confirm-session-restore').disabled=!!locked||!pendingSessionRestore;
    $('cancel-session-restore').disabled=!!locked;
    for(const button of document.querySelectorAll('[data-session-backup-control]'))button.disabled=!!locked;
}
async function loadSessionBackups(){
    if(sessionBackupLoading)return;sessionBackupLoading=true;
    try{
        const inventory=await call('session_backups'),entries=inventory.entries||[];
        $('session-backup-summary').textContent=entries.length+' complete session backup'+(entries.length===1?'':'s')+' · '+sizeText(inventory.total_bytes||0)+'. Export remains available after closing the picker.';
        $('session-backup-list').replaceChildren();
        if(!entries.length)$('session-backup-list').textContent='No complete session backups yet.';
        for(const archive of entries){
            const row=document.createElement('article');row.className='backup-card';
            const title=document.createElement('h4');title.textContent=archive.reason||'Complete session backup';
            const info=document.createElement('p');info.className='small';info.textContent=(archive.created_at?dateText(archive.created_at)+' · ':'')+sizeText(archive.bytes||0);
            const name=document.createElement('p');name.className='small';name.textContent=archive.name||archive.file;
            const exported=document.createElement('p');exported.className='small '+(archive.exported_at?'exported':'not-exported');exported.textContent=archive.exported_at?'Export completed '+dateText(archive.exported_at)+'. Keep that external copy safe.':'App copy only · export outside the app for safekeeping.';
            const buttons=document.createElement('div');buttons.className='actions';
            for(const [label,work]of [['Export',()=>exportFile(archive.file)],['Preview / restore',async()=>showSessionRestorePreview(await call('session_backup_preview',{file:archive.file}))]]){
                const button=document.createElement('button');button.textContent=label;button.className='secondary';button.dataset.sessionBackupControl='true';button.addEventListener('click',()=>managedClick(button,work));buttons.append(button);
            }
            row.append(title,info,name,exported,buttons);$('session-backup-list').append(row);
        }
    }finally{sessionBackupLoading=false;updateControls();}
}
async function loadSessionUiPreferences(){
    const saved=await call('session_ui_preferences');
    if(saved.ui&&saved.revision&&localStorage.getItem('session-ui-revision')!==saved.revision){
        applySessionUi(saved.ui);localStorage.setItem('session-ui-revision',saved.revision);
    }
}
async function setupSessionAction(name){
    if(name==='load_session_backups')return loadSessionBackups();
    if(name==='session_backup'){
        notice('Saving and closing the session before making a complete backup…');
        const result=await awaitTask(await call(name,{ui:{launch:options(),source:sourceOptions()}}));
        notice(result.message||'Complete session backup created.');
        await loadSessionBackups();
        await exportFile(result.file);await refresh();return;
    }
    const args=name==='pull_compile'?sourceOptions(true):{};
    if(name==='pull_compile')saveSourceOptions();
    const result=await call(name,args);
    notice(result.message||(result.id?'Task started. Progress appears in the quest journal.':'Server ready.'));await refresh();
}

function showSessionRestorePreview(info){
    if(!info?.file)throw Error('The session backup preview did not include an archive to restore.');
    pendingSessionRestore=info;
    $('session-restore-status').hidden=true;$('session-restore-status').classList.remove('error');
    const details=[info.name||'Selected complete session ZIP'];
    if(info.created_at)details.push(dateText(info.created_at));
    details.push(sizeText(info.bytes||0),(info.files||0)+' files',sizeText(info.unpacked_bytes||0)+' unpacked');
    $('session-restore-info').textContent=details.join(' · ');
    const components=info.components||info.folders||[];
    const labels=Array.isArray(components)?components.map(component=>typeof component==='string'?component:component.label||component.name||component.path).filter(Boolean):Object.keys(components).filter(key=>components[key]);
    $('session-restore-components').textContent='Included: '+(labels.length?labels.join(', '):'components listed in the session manifest')+'. Archive contents and available storage are checked again during restoration.';
    $('session-restore-preview').showModal();updateControls();
}
function sessionRestoreProgress(message){
    if(!$('session-restore-preview').open||$('session-restore-status').classList.contains('error'))return;
    if(message||nativeState.session_busy||activeJob()){
        $('session-restore-status').hidden=false;
        $('session-restore-status').textContent=message||nativeState.session_status||activeJob()?.message||'Preparing complete session restore…';
    }
}
async function cancelSessionRestore(){
    const selected=pendingSessionRestore;pendingSessionRestore=null;$('session-restore-preview').close();
    if(selected?.file&&/^[0-9a-f-]{36}\.zip$/.test(selected.file))await call('discard_import',{file:selected.file});
    notice('Complete session restore cancelled. Your installation was kept.');
}
function applySessionUi(ui){
    if(!ui||typeof ui!=='object')return;
    const launch=ui.launch;
    if(launch&&typeof launch==='object'){
        for(const [key,id]of [['renderer','renderer'],['resolution','resolution'],['presentation_mode','presentation'],['display_fps','fps'],['audio_driver','audio-driver']]){
            if(launch[key]!==undefined&&[...$(id).options].some(option=>option.value===String(launch[key])))$(id).value=String(launch[key]);
        }
        for(const [key,id]of [['dirty_regions','dirty-regions'],['audio','audio'],['smooth_audio','smooth-audio'],['music_cache','music-cache'],['frame_budget','frame-budget'],['map_metadata_cache','map-metadata-cache'],['proot_acceleration','client-acceleration'],['gump_space','gump-space'],['managed_diagnostics','managed-diagnostics'],['render_trace','render-trace'],['sdl_graphics_fixes','sdl-graphics-fixes'],['cold_trace','cold-trace']])if(typeof launch[key]==='boolean')$(id).checked=launch[key];
        saveOptions();
    }
    if(ui.source)applySourceOptions(ui.source);
}
$('cancel-session-restore').addEventListener('click',()=>cancelSessionRestore().catch(error=>notice(error.message,true)));
$('session-restore-preview').addEventListener('cancel',event=>{event.preventDefault();if(!$('cancel-session-restore').disabled)cancelSessionRestore().catch(error=>notice(error.message,true));});
$('confirm-session-restore').addEventListener('click',()=>managedClick($('confirm-session-restore'),async()=>{
    const selected=pendingSessionRestore;if(!selected)return;
    $('session-restore-status').classList.remove('error');$('session-restore-status').hidden=false;
    $('session-restore-status').textContent='Saving and closing the session, then preserving a complete snapshot before replacement…';
    const result=await awaitTask(await call('session_restore',{file:selected.file,ui:{launch:options(),source:sourceOptions()}}));
    applySessionUi(result.ui||selected.ui);
    if(result.ui_revision)localStorage.setItem('session-ui-revision',result.ui_revision);
    pendingSessionRestore=null;$('session-restore-preview').close();
    stagedServerSource=null;
    settingsModel=null;settingInputs.clear();$('settings-editor').hidden=true;$('settings-status').textContent='Complete session restored. Reload server settings to inspect the restored values.';
    if($('server-settings').open)await loadSettings(true);
    notice(result.message||'Complete session restored.');
    await loadSessionBackups();
}));
updateControls();
loadSessionBackups().catch(error=>notice(error.message,true));
loadSessionUiPreferences().catch(error=>notice(error.message,true));
