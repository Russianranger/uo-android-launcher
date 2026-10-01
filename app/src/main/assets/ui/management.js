'use strict';
const managementActions=new Set(['load_backups','load_settings','settings_save','settings_reset','settings_undo','save_backup','prune_backups']);
let backupInventory=[],backupSignature='',backupLoading=false,settingsModel=null,settingsLoading=false,pendingRestore=null;
const settingInputs=new Map();
function sizeText(bytes){return bytes>=1073741824?(bytes/1073741824).toFixed(2)+' GB':bytes>=1048576?(bytes/1048576).toFixed(1)+' MB':bytes>=1024?(bytes/1024).toFixed(1)+' KB':bytes+' bytes';}
function dateText(seconds){return new Date(seconds*1000).toLocaleString();}

async function awaitTask(job){
    if(!job?.id)return job;
    const deadline=Date.now()+20*60*1000;
    while(Date.now()<deadline){
        const state=await call('state');realmState=state;
        const current=state.jobs.find(j=>j.id===job.id);
        if(!current)throw Error('Task is no longer available. Check the Journal before retrying.');
        if(current.status==='error')throw Error(current.error||current.message);
        if(current.status==='done')return current.result;
        $('session-status').textContent=current.message;restoreProgress(current.message);updateControls();
        await new Promise(resolve=>setTimeout(resolve,500));
    }
    throw Error('The task is still running. Check the Journal; it has been left running.');
}
async function managedClick(button,work){
    if(busy())return;
    activeActions.add(button);updateControls();
    try{await work();await refresh();}
    catch(error){notice(error.message,true);showSetupForError(error.message);if($('restore-preview').open){$('restore-status').hidden=false;$('restore-status').textContent=error.message;$('restore-status').classList.add('error');}}
    finally{activeActions.delete(button);updateControls();}
}
async function loadBackups(){
    if(backupLoading)return;backupLoading=true;
    try{
        const inventory=await call('backups');backupInventory=inventory.entries||[];
        $('backup-summary').textContent=backupInventory.length+' app backup'+(backupInventory.length===1?'':'s')+' · '+sizeText(inventory.total_bytes||0)+'. Available even with the runtime closed.';
        const signature=JSON.stringify(backupInventory);if(signature===backupSignature)return;backupSignature=signature;
        $('backup-list').replaceChildren();
        if(!backupInventory.length){$('backup-list').textContent='No app backups yet. Save & export creates your first one.';return;}
        for(const archive of backupInventory){
            const row=document.createElement('article');row.className='backup-card';
            const title=document.createElement('h4');title.textContent=archive.reason||'Save-data backup';
            const info=document.createElement('p');info.className='small';info.textContent=dateText(archive.created_at)+' · '+sizeText(archive.bytes);
            const name=document.createElement('p');name.className='small';name.textContent=archive.name;
            const exported=document.createElement('p');exported.className='small '+(archive.exported_at?'exported':'not-exported');exported.textContent=archive.exported_at?'Export completed '+dateText(archive.exported_at)+'. Keep that external copy safe.':'App copy only · export it outside the app for safekeeping.';
            const buttons=document.createElement('div');buttons.className='actions';
            for(const [label,kind,work]of[
                ['Export','secondary',()=>exportFile(archive.file)],
                ['Preview / restore','secondary',async()=>showRestorePreview(await call('backup_preview',{name:archive.name}))],
                ['Delete app copy','danger',async()=>{if(!confirm('Delete this app backup from '+dateText(archive.created_at)+'? '+(archive.exported_at?'Exported copies outside the app are separate.':'This backup has not been exported through the app.')))return;const result=await awaitTask(await call('delete_backup',{name:archive.name}));notice(result.message);await loadBackups();}]
            ]){const button=document.createElement('button');button.textContent=label;button.className=kind;button.dataset.backupControl='true';button.addEventListener('click',()=>managedClick(button,work));buttons.append(button);}
            row.append(title,info,name,exported,buttons);$('backup-list').append(row);
        }
    }finally{backupLoading=false;updateControls();}
}
function showRestorePreview(info){
    pendingRestore=info;
    $('restore-status').hidden=true;$('restore-status').classList.remove('error');
    $('restore-info').textContent=(info.backup?info.name:'Selected save-data ZIP')+' · '+sizeText(info.bytes)+' · '+info.files+' files · '+sizeText(info.unpacked_bytes)+' unpacked';
    $('restore-folders').textContent='Included: '+info.folders.join(', ')+'.'+(info.legacy?' Legacy Data content will be skipped.':'')+' ZIP contents are validated again during restoration.';
    $('restore-preview').showModal();updateControls();
}
function restoreProgress(message){
    if(!$('restore-preview').open||$('restore-status').classList.contains('error'))return;
    if(message||nativeState.session_busy||activeJob()){
        $('restore-status').hidden=false;$('restore-status').textContent=message||nativeState.session_status||activeJob()?.message||'Preparing restoration…';
    }
}
async function cancelRestore(){
    const selected=pendingRestore;pendingRestore=null;$('restore-preview').close();
    if(selected?.file)await call('discard_import',{file:selected.file});
    notice('Restore cancelled. Your world was kept.');
}
$('cancel-restore').addEventListener('click',()=>cancelRestore().catch(e=>notice(e.message,true)));
$('restore-preview').addEventListener('cancel',event=>{event.preventDefault();if(!$('cancel-restore').disabled)cancelRestore().catch(e=>notice(e.message,true));});
$('confirm-restore').addEventListener('click',()=>managedClick($('confirm-restore'),async()=>{
    const selected=pendingRestore;if(!selected)return;
    $('restore-status').classList.remove('error');$('restore-status').hidden=false;$('restore-status').textContent='Saving the current session before restoring…';
    if(nativeState.alive||clientState.alive)await call('session_close');
    const result=await awaitTask(await call('restore_world',selected.backup?{backup:selected.backup}:{file:selected.file}));
    pendingRestore=null;$('restore-preview').close();notice(result.message);await loadBackups();
    // Restored Info may contain different settings; reload explicitly to avoid a stale draft.
    settingsModel=null;settingInputs.clear();$('settings-editor').hidden=true;$('settings-status').textContent='Save data restored. Reload server settings to inspect the imported values.';
}));

function fieldValue(field,input){
    if(field.type==='bool')return input.checked;
    if(field.type==='string')return input.value;
    if(field.type==='int[]'){
        if(!input.value.trim())return [];
        const values=input.value.split(',').map(value=>value.trim());
        if(values.some(value=>!/^[-+]?\d+$/.test(value)))throw Error(field.label+': enter whole numbers separated by commas.');
        return values.map(Number);
    }
    if(!input.value.trim()||!input.checkValidity())throw Error(field.label+': enter a value within the shown range.');
    const value=Number(input.value);if(!Number.isFinite(value))throw Error(field.label+': enter a finite number.');
    return value;
}
function settingsChanges(strict=false){
    const changes={};
    for(const [name,{field,input}]of settingInputs){
        if(input.dataset.touched!=='true')continue;
        try{const value=fieldValue(field,input);input.closest('.setting-field').classList.remove('invalid');if(JSON.stringify(value)!==JSON.stringify(field.value))changes[name]=value;}
        catch(error){input.closest('.setting-field').classList.add('invalid');if(strict)throw error;changes[name]=null;}
        input.closest('.setting-field').classList.toggle('edited',Object.hasOwn(changes,name));
    }
    return changes;
}
function renderSettings(model){
    settingsModel=model;settingInputs.clear();$('settings-fields').replaceChildren();$('settings-category').replaceChildren();
    const all=document.createElement('option');all.value='';all.textContent='All categories';$('settings-category').append(all);
    const groups=new Map();
    for(const field of model.fields){
        if(!groups.has(field.section)){
            const group=document.createElement('details');group.className='setting-group';group.open=groups.size===0;
            const summary=document.createElement('summary');summary.textContent=field.section;
            const grid=document.createElement('div');grid.className='setting-grid';group.append(summary,grid);$('settings-fields').append(group);groups.set(field.section,{group,grid});
            const option=document.createElement('option');option.value=field.section;option.textContent=field.section;$('settings-category').append(option);
        }
        const row=document.createElement('div');row.className='setting-field';row.dataset.category=field.section;row.dataset.search=(field.label+' '+field.name+' '+field.description).toLowerCase();
        const label=document.createElement('label');label.textContent=field.label;row.append(label);
        if(field.read_only){const value=document.createElement('p');value.className='setting-value small';value.textContent=field.value===null?'Custom override':Array.isArray(field.value)?field.value.join(', '):String(field.value);const reason=document.createElement('p');reason.className='small';reason.textContent=field.reason;row.append(value,reason);}
        else{
            const input=document.createElement(field.choices?'select':'input');input.id='setting-'+field.name;label.htmlFor=input.id;
            if(field.choices){for(const value of field.choices){const option=document.createElement('option');option.value=String(value);option.textContent=String(value);input.append(option);}input.value=String(field.value);}
            else if(field.type==='bool'){input.type='checkbox';input.checked=field.value;label.className='check';}
            else{input.type=['int','double'].includes(field.type)?'number':'text';input.value=Array.isArray(field.value)?field.value.join(', '):field.value??'';if(input.type==='number'){input.step=field.type==='int'?'1':'any';if(field.min!==undefined)input.min=field.min;if(field.max!==undefined)input.max=field.max;}else input.maxLength=field.type==='string'?2048:10000;}
            if(field.type==='bool')label.append(input);else row.append(input);
            const edited=()=>{input.dataset.touched='true';updateControls();};input.addEventListener('input',edited);input.addEventListener('change',edited);settingInputs.set(field.name,{field,input});
            if(field.min!==undefined){const range=document.createElement('p');range.className='small';range.textContent='Range: '+field.min+' – '+field.max;row.append(range);}
        }
        if(field.description){const help=document.createElement('details');const summary=document.createElement('summary');summary.textContent='What this changes';const text=document.createElement('p');text.textContent=field.description;help.append(summary,text);row.append(help);}
        const key=document.createElement('p');key.className='setting-key';key.textContent=field.name;row.append(key);groups.get(field.section).grid.append(row);
    }
    $('settings-editor').hidden=false;$('settings-search').value='';$('settings-status').textContent=model.fields.length+' settings loaded. '+(model.running?'Save and stop the server before applying changes.':'Changes apply on the next server start.');updateControls();
}
async function loadSettings(force=false){
    if(settingsLoading)return;
    if(!force&&settingsModel&&Object.keys(settingsChanges()).length&&!confirm('Discard your unsaved settings edits and reload?'))return;
    settingsLoading=true;$('settings-status').textContent='Loading server settings…';
    try{renderSettings(await call('settings_read'));}catch(error){$('settings-status').textContent=error.message;throw error;}finally{settingsLoading=false;updateControls();}
}
function filterSettings(){
    const query=$('settings-search').value.trim().toLowerCase(),category=$('settings-category').value;
    for(const row of document.querySelectorAll('.setting-field'))row.hidden=!!((category&&row.dataset.category!==category)||(query&&!row.dataset.search.includes(query)));
    for(const group of document.querySelectorAll('.setting-group')){group.hidden=!group.querySelector('.setting-field:not([hidden])');if(query||category)group.open=true;}
}
$('settings-search').addEventListener('input',filterSettings);$('settings-category').addEventListener('change',filterSettings);
$('server-settings').addEventListener('toggle',()=>{if($('server-settings').open&&!settingsModel&&!settingsLoading)loadSettings().catch(e=>notice(e.message,true));});
function managementControls(locked){
    const changes=settingsModel?Object.keys(settingsChanges()).length:0;
    for(const {input}of settingInputs.values())input.disabled=!!locked||settingsLoading;
    $('settings-dirty').textContent=changes?changes+' unsaved change'+(changes===1?'':'s')+'.':'No unsaved changes.';
    const serverRunning=nativeState.alive?(realmState?.running??settingsModel?.running):false;
    document.querySelector('[data-action="settings_save"]').disabled=locked||settingsLoading||!changes||!!serverRunning;
    document.querySelector('[data-action="settings_reset"]').disabled=locked||!changes;
    document.querySelector('[data-action="settings_undo"]').disabled=locked||settingsLoading||!settingsModel?.can_undo||!!serverRunning;
    document.querySelector('[data-action="prune_backups"]').disabled=locked||backupInventory.length<=Number($('backup-keep').value);
    for(const button of document.querySelectorAll('[data-backup-control]'))button.disabled=!!locked;
    $('confirm-restore').disabled=!!locked||!pendingRestore;$('cancel-restore').disabled=!!locked;
}
$('backup-keep').addEventListener('change',updateControls);
async function managementAction(name){
    if(name==='load_backups')return loadBackups();
    if(name==='load_settings')return loadSettings();
    if(name==='settings_reset'){renderSettings(settingsModel);return;}
    if(name==='settings_save'||name==='settings_undo'){
        if(name==='settings_undo'&&!confirm('Undo the last applied settings edit?'))return;
        const args={revision:settingsModel.revision};if(name==='settings_save')args.changes=settingsChanges(true);
        const result=await awaitTask(await call(name,args));await loadSettings(true);notice(result.message);return;
    }
    if(name==='prune_backups'){
        const keep=Number($('backup-keep').value),old=backupInventory.slice(keep),unexported=old.filter(backup=>!backup.exported_at).length;
        if(!old.length)return;
        if(!confirm('Remove '+old.length+' older app backups and keep the newest '+keep+'? '+unexported+' of those older backups have not been exported through the app.'))return;
        const result=await awaitTask(await call(name,{keep,names:old.map(archive=>archive.name)}));notice(result.message);await loadBackups();return;
    }
    if(name==='save_backup'){
        if((clientState.alive||realmState?.running)&&!confirm('Close the client, save and stop the server, then export your save data?'))return;
        const result=await awaitTask(await call(name));await loadBackups();notice(result.message);await exportFile(result.file);
    }
}
loadBackups().catch(e=>notice(e.message,true));
