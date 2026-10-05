const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const settingsFixture=JSON.parse(require('child_process').execFileSync('python3',['-c',"import json,sys;from pathlib import Path;sys.path.insert(0,'backend');from server_settings import fields;print(json.dumps({'revision':'first','fields':[f for f,_ in fields(Path('tests/fixtures/memento-settings.cs').read_text())],'can_undo':False,'running':False}))"],{cwd:path.join(__dirname,'..'),encoding:'utf8'}));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1280,height:850},deviceScaleFactor:1});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.route('https://app.memento.local/**',async route=>{
  const filename=path.basename(new URL(route.request().url()).pathname)||'index.html';
  const types={'.html':'text/html','.js':'application/javascript','.css':'text/css','.png':'image/png'};
  await route.fulfill({contentType:types[path.extname(filename)],body:fs.readFileSync(path.join(__dirname,'../app/src/main/assets/ui',filename))});
 });
 await page.addInitScript((settingsFixture)=>{
  window.settingsFixture=settingsFixture;window.mockJobs=[];window.backupReport=[{name:'memento-world-2.zip',file:'exports/memento-world-2.zip',bytes:2000,created_at:1790871000,reason:'Before restore'},{name:'memento-world-1.zip',file:'exports/memento-world-1.zip',bytes:1000,created_at:1790870000,reason:'Manual backup',exported_at:1790870100}];
  window.sessionBackupReport=JSON.parse(localStorage.getItem('mock-native-session-backups')||'[]');window.sessionPreview={file:'85e774ed-5192-4fd2-a402-19a9d1ae0f45.zip',name:'complete-session.zip',created_at:1790870200,bytes:9000,unpacked_bytes:18000,files:34,components:['realm runtime','FEX client runtime','server source','world saves','client','Wine prefix','controller mappings','launcher settings'],ui:{launch:{runtime_backend:'fex-arm64ec-1',pacing_revision:1,renderer:'virgl',resolution:'1024x768',presentation_mode:'rfb',display_fps:30,audio:true,smooth_audio:true,dirty_regions:true,gump_space:false},source:{source:'fork',ref:'restored-tag'}}};
  window.calls=[];window.Memento={call(id,op,args){window.calls.push({op,args:JSON.parse(args)});let result={};
   if(op==='session_play'&&window.holdSession){window.nativeReport={session_busy:true,session_cancellable:true,session_seconds:12,session_status:'Starting server · waiting for the world to be ready…'};window.heldSession=id;return;}
   if(op==='session_play'&&window.sessionFailure){setTimeout(()=>window.nativeReply(id,{ok:false,error:window.sessionFailure}),0);return;}
   if(op==='client_start'||op==='session_play')window.clientActive=true;
   if(op==='native_state')result={alive:true,installed:true,status:'Realm runtime ready',version:'0.2.16',free_bytes:24*1073741824,...window.nativeReport};
   if(op==='client_native_state')result={alive:!!window.clientActive,display_ready:!!window.clientActive,installed:true,status:'TazUO is ready to launch.',launch:{sdl_graphics:window.graphicsReport}};
   if(op==='state')result={running:false,ready:false,build:{revision:'916d1ec666376ef44366c986befa3200deb93eb0',ref:'main'},server_source:window.serverSource||null,client:{executable:'Client/TazUO.exe',architecture:'x64',dotnet_version:'10.0.0'},jobs:[],...window.realmReport};
   if(op==='state')result.jobs=[...result.jobs,...window.mockJobs];
   if(op==='backups')result={entries:window.backupReport,total_bytes:window.backupReport.reduce((sum,entry)=>sum+entry.bytes,0)};
   if(op==='backup_preview')result={name:JSON.parse(args).name,backup:JSON.parse(args).name,folders:['Info','Saves','Backups'],bytes:2000,files:12,unpacked_bytes:4000};
   if(op==='pull_compile'){window.serverSource={...JSON.parse(args),repository:JSON.parse(args).repository||(JSON.parse(args).source==='upstream'?'https://github.com/Jascen/ultima-memento.git':'https://github.com/Russianranger/ultima-memento.git'),revision:'916d1ec666376ef44366c986befa3200deb93eb0'};result={id:'pull-'+window.calls.length};window.mockJobs.push({...result,status:'done',message:'Server compiled',result:{message:'Server compiled'}});}
   if(op==='compile_server'){result={id:'compile-'+window.calls.length};window.mockJobs.push({...result,status:'done',message:'Imported server compiled',result:{message:'Imported server compiled'}});}
   if(op==='pick'&&JSON.parse(args).kind==='server'){window.serverSource={kind:'zip',name:'offline-server.zip'};result={id:'import-'+window.calls.length,message:'Server source imported. Compile next.'};window.mockJobs.push({...result,status:'done',result:{message:result.message}});}
   if(op==='pick'&&JSON.parse(args).kind==='session')result=structuredClone(window.sessionPreview);
   if(op==='session_backup_preview')result={...structuredClone(window.sessionPreview),file:JSON.parse(args).file};
   if(op==='session_backups')result={entries:window.sessionBackupReport,total_bytes:window.sessionBackupReport.reduce((sum,entry)=>sum+entry.bytes,0)};
   if(op==='session_ui_preferences')result=window.sessionUiPreferences||{};
   if(op==='session_backup'){window.clientActive=false;window.nativeReport={alive:false,session_busy:false};result={file:'exports/memento-session-1.zip',message:'Complete session backup created.'};window.sessionBackupReport.unshift({file:result.file,name:'memento-session-1.zip',bytes:9000,created_at:1790870200,reason:'Manual complete session backup'});localStorage.setItem('mock-native-session-backups',JSON.stringify(window.sessionBackupReport));}
   if(op==='session_restore'&&window.sessionRestoreFailure){setTimeout(()=>window.nativeReply(id,{ok:false,error:window.sessionRestoreFailure}),0);return;}
   if(op==='session_restore'){window.clientActive=false;window.nativeReport={alive:false,session_busy:false};window.serverSource={source:'fork',repository:'https://github.com/Russianranger/ultima-memento.git',ref:'restored-tag'};result={message:'Complete session restored.',ui:structuredClone(window.sessionPreview.ui),ui_revision:'restored-ui-1',rollback_backup:'exports/memento-session-before-restore.zip'};window.sessionUiPreferences={ui:result.ui,revision:result.ui_revision};window.sessionBackupReport.unshift({file:result.rollback_backup,name:'memento-session-before-restore.zip',bytes:10000,created_at:1790870300,reason:'Before complete session restore'});localStorage.setItem('mock-native-session-backups',JSON.stringify(window.sessionBackupReport));}
   if(op==='export'&&window.exportFailure){setTimeout(()=>window.nativeReply(id,{ok:false,error:window.exportFailure}),0);return;}
   if(op==='export'){const archive=window.sessionBackupReport.find(entry=>entry.file===JSON.parse(args).path);if(archive){archive.exported_at=1790870400;localStorage.setItem('mock-native-session-backups',JSON.stringify(window.sessionBackupReport));}}
   if(op==='restore_world'&&window.restoreFailure){setTimeout(()=>window.nativeReply(id,{ok:false,error:window.restoreFailure}),0);return;}
   if(op==='settings_read')result=structuredClone(window.settingsFixture);
   if(['settings_save','settings_undo','save_backup','delete_backup','prune_backups','restore_world'].includes(op)){
    if(op==='settings_save'){window.previousSettings=structuredClone(window.settingsFixture);for(const field of window.settingsFixture.fields)if(Object.hasOwn(JSON.parse(args).changes,field.name))field.value=JSON.parse(args).changes[field.name];window.settingsFixture.revision+='x';window.settingsFixture.can_undo=true;}
    if(op==='settings_undo')window.settingsFixture=window.previousSettings;
    if(op==='delete_backup')window.backupReport=window.backupReport.filter(entry=>entry.name!==JSON.parse(args).name);
    if(op==='restore_world')window.nativeReport={alive:true,session_busy:false};
    result={id:'task-'+(window.mockJobs.length+1)};window.mockJobs.push({...result,status:'done',message:'Complete',result:{message:'Complete',file:op==='save_backup'?'exports/memento-world-2.zip':undefined}});
   }
   if(op==='session_close'||op==='session_cancel'){window.clientActive=false;window.nativeReport={alive:false,session_busy:false};result={message:'Session saved and closed.'};if(window.heldSession){window.nativeReply(window.heldSession,{ok:false,error:'Launch cancelled. Saving and closing the session…'});window.heldSession=null;window.holdSession=false;}}
   if(op==='logs')result={text:'Memento: ready\n',names:['runtime.log','server.log']};
   setTimeout(()=>window.nativeReply(id,{ok:true,result}),0);
  }};
 },settingsFixture);
 await page.goto('https://app.memento.local/index.html');await page.waitForTimeout(200);
 if(await page.title()!=='UO Memento Mobile')throw Error('App name missing from launcher');
 // Source selection defaults upstream, persists independently, and sends only the selected source.
 await page.locator('#realm-setup > summary').click();
 if(await page.locator('#source-kind').inputValue()!=='upstream'||await page.locator('#custom-source').isVisible())throw Error('Upstream must be the default source');
 if(!await page.locator('[data-action="compile_server"]').isDisabled())throw Error('Compilation is enabled without staged server source');
 await page.locator('[data-action="pull_compile"]').click();
 await page.waitForFunction(()=>window.calls.some(call=>call.op==='pull_compile'&&call.args.source==='upstream'&&call.args.ref==='main'&&!Object.hasOwn(call.args,'repository')));
 await page.locator('#source-kind').selectOption('fork');await page.locator('#source-ref').fill('my-tag');
 await page.locator('[data-action="pull_compile"]').click();
 await page.waitForFunction(()=>window.calls.some(call=>call.op==='pull_compile'&&call.args.source==='fork'&&call.args.ref==='my-tag'&&!Object.hasOwn(call.args,'repository')));
 await page.locator('#source-kind').selectOption('custom');
 if(!await page.locator('#custom-source').isVisible())throw Error('Custom repository input is hidden');
 await page.locator('#source-repository').fill('http://github.com/example/server');
 const pullsBeforeInvalid=await page.evaluate(()=>window.calls.filter(call=>call.op==='pull_compile').length);
 await page.locator('[data-action="pull_compile"]').click();
 await page.waitForFunction(()=>document.getElementById('notice').classList.contains('error'));
 if(await page.evaluate(()=>window.calls.filter(call=>call.op==='pull_compile').length)!==pullsBeforeInvalid)throw Error('Invalid custom source dispatched a native pull');
 await page.locator('#source-repository').fill('https://github.com/example/offline-memento.git');await page.locator('#source-ref').fill('custom-branch');
 await page.locator('[data-action="pull_compile"]').click();
 await page.waitForFunction(()=>window.calls.some(call=>call.op==='pull_compile'&&call.args.repository==='https://github.com/example/offline-memento.git'&&call.args.ref==='custom-branch'&&call.args.source==='custom'));
 await page.locator('#source-repository').fill('https://gitlab.com/example/group/memento.git');
 await page.locator('[data-action="pull_compile"]').click();
 await page.waitForFunction(()=>window.calls.some(call=>call.op==='pull_compile'&&call.args.repository==='https://gitlab.com/example/group/memento.git'&&call.args.source==='custom'));
 await page.locator('#source-repository').fill('https://github.com/example/offline-memento.git');
 await page.reload();await page.locator('#realm-setup > summary').click();
 if(await page.locator('#source-kind').inputValue()!=='custom'||await page.locator('#source-ref').inputValue()!=='custom-branch'||await page.locator('#source-repository').inputValue()!=='https://github.com/example/offline-memento.git')throw Error('Server source preferences did not persist');
 // Importing offline server source stages it; compilation is an explicit separate operation.
 await page.locator('#server-offline > summary').click();
 await page.evaluate(()=>{window.calls=[];window.serverSource=null;});
 await page.locator('[data-pick="server"]').click();
 await page.waitForFunction(()=>document.getElementById('offline-source-status').textContent.includes('offline-server.zip'));
 if(await page.evaluate(()=>window.calls.some(call=>call.op==='compile_server'||call.op==='pull_compile')))throw Error('Offline import compiled or downloaded without the separate step');
 await page.locator('[data-action="compile_server"]').click();
 await page.waitForFunction(()=>window.calls.some(call=>call.op==='compile_server'&&Object.keys(call.args).length===0));
 if(!await page.locator('#build-info').textContent().then(text=>text.includes('916d1ec66637')))throw Error('Source controls lost the installed build report');
 await page.locator('#realm-setup > summary').click();
 fs.mkdirSync('ui-reports',{recursive:true});
 await page.screenshot({path:'ui-reports/realm-landscape.png',fullPage:true});
 await page.locator('[data-tab="client"]').click();
 if(await page.locator('#client-options').evaluate(node=>node.open))throw Error('Client options must start collapsed');
 if(!await page.evaluate(()=>['renderer','resolution','presentation','dirty-regions','fps','gump-space','audio','audio-driver','smooth-audio','client-acceleration','frame-budget','map-metadata-cache','music-cache','sdl-graphics-fixes','render-trace','managed-diagnostics','cold-trace'].every(id=>document.getElementById(id).closest('#client-options'))))throw Error('Client controls escaped the options dropdown');
 await page.locator('#client-options > summary').click();
 await page.locator('[data-action="controller_open"]').click();
 if(!await page.evaluate(()=>window.calls.some(c=>c.op==='controller_open')))throw Error('Controller action not connected');
 if(!await page.locator('#gump-space').isChecked())throw Error('Requested world layout must default on');
 if(await page.locator('#fps').inputValue()!=='30')throw Error('Cooler frame target must default to 30');
 if(await page.locator('#audio-driver').inputValue()!=='wasapi'||!await page.locator('#client-acceleration').isChecked())throw Error('Optimized launch defaults missing');
 if(!await page.locator('#smooth-audio').isChecked())throw Error('Smooth audio must default on');
 if(!await page.locator('#dirty-regions').isChecked())throw Error('Region delivery must default on');
 if(!await page.locator('#frame-budget').isChecked())throw Error('Frame budget must default on');
 if(!await page.locator('#map-metadata-cache').isChecked())throw Error('Map metadata cache must default on');
 if(!await page.locator('#music-cache').isChecked())throw Error('Music cache must default on');
 if(await page.locator('#render-trace').isChecked())throw Error('Render tracing must default off');
 if(await page.locator('#cold-trace').isChecked())throw Error('Cold-load diagnostics must default off');
 if(await page.locator('#managed-diagnostics').isChecked())throw Error('Managed diagnostics must default off');
 if(await page.locator('#sdl-graphics-fixes').isChecked())throw Error('FEX must start with original graphics libraries');
 await page.evaluate(async()=>{window.graphicsReport={active_version:'3.4.16',action:'updated_known_tazuo_5.2_pair'};await refresh();});
 await page.waitForFunction(()=>document.getElementById('sdl-graphics-status').textContent.includes('3.4.16 active'));
 await page.evaluate(async()=>{window.graphicsReport={active_version:'3.2.27 (TazUO 5.2)',action:'restored_original',original_for_diagnostics:true};await refresh();});
 await page.waitForFunction(()=>document.getElementById('sdl-graphics-status').textContent.includes('original graphics library for cold-load timing'));
 await page.evaluate(async()=>{window.graphicsReport={active_version:'unrecognized',action:'unchanged_unrecognized_libraries'};await refresh();});
 await page.waitForFunction(()=>document.getElementById('sdl-graphics-status').textContent.includes('left as imported'));
 await page.evaluate(()=>localStorage.setItem('launch',JSON.stringify({cold_trace:true,managed_diagnostics:true,render_trace:true,sdl_graphics_fixes:true,client_memory_compatibility:true,renderer:'turnip',resolution:'1280x720',presentation_mode:'native_surface',display_fps:60,audio:false,gump_space:true})));
 await page.reload();await page.locator('[data-tab="client"]').click();
 if(await page.locator('#client-options').evaluate(node=>node.open))throw Error('Client options must start collapsed');
 await page.locator('#client-options > summary').click();
 if(await page.locator('#cold-trace').isChecked()||await page.locator('#render-trace').isChecked()||await page.locator('#managed-diagnostics').isChecked()||await page.locator('#sdl-graphics-fixes').isChecked())throw Error('Legacy runtime experiments must reset');
 if(await page.locator('#fps').inputValue()!=='30')throw Error('Old transport-only 60 target must migrate to cooler default');
 if(await page.locator('#audio').isChecked()||await page.locator('#presentation').inputValue()!=='native_surface'||!await page.locator('#gump-space').isChecked())throw Error('Upgrade must preserve unrelated options');
 await page.locator('#resolution').selectOption('800x600');
 if(await page.locator('#gump-space').isChecked())throw Error('Other resolutions must opt out of fixed layout');
 await page.locator('#gump-space').check();
 if(await page.locator('#resolution').inputValue()!=='1280x720')throw Error('Gump space must select full 1280 canvas');
 await page.reload();await page.locator('[data-tab="client"]').click();
 if(await page.locator('#client-options').evaluate(node=>node.open))throw Error('Client options must start collapsed');
 await page.locator('#client-options > summary').click();
 if(!await page.locator('#gump-space').isChecked())throw Error('Layout selection did not persist');
 await page.locator('[data-action="client_start"]').click();await page.waitForTimeout(50);
 if(!await page.evaluate(()=>window.calls.some(c=>c.op==='client_start'&&c.args.runtime_backend==='fex-arm64ec-1'&&c.args.cold_trace===false&&c.args.managed_diagnostics===false&&c.args.render_trace===false&&c.args.sdl_graphics_fixes===false&&c.args.audio_driver==='wasapi'&&c.args.proot_acceleration===true&&c.args.music_cache===true&&c.args.frame_budget===true&&c.args.map_metadata_cache===true&&c.args.smooth_audio===true&&c.args.dirty_regions===true)))throw Error('Default options missing from native launch');
 await page.locator('#fps').selectOption('60');
 await page.locator('#audio-driver').selectOption('directsound');
 await page.locator('#client-acceleration').uncheck();
 await page.locator('#music-cache').uncheck();
 await page.locator('#frame-budget').uncheck();
 await page.locator('#map-metadata-cache').uncheck();
 await page.locator('#smooth-audio').uncheck();
 await page.locator('#dirty-regions').uncheck();
 await page.locator('#render-trace').check();
 await page.locator('#managed-diagnostics').check();
 await page.locator('#cold-trace').check();
 await page.locator('#sdl-graphics-fixes').uncheck();
 await page.reload();await page.locator('[data-tab="client"]').click();
 if(await page.locator('#client-options').evaluate(node=>node.open))throw Error('Client options must start collapsed');
 await page.locator('#client-options > summary').click();
 if(await page.locator('#sdl-graphics-fixes').isChecked())throw Error('Original graphics library choice did not persist');
 if(await page.locator('#fps').inputValue()!=='60')throw Error('Explicit 60 FPS choice must persist');
 if(await page.locator('#dirty-regions').isChecked())throw Error('Full-frame comparison choice did not persist');
 if(!await page.locator('#cold-trace').isChecked())throw Error('Cold-load timing choice did not persist');
 if(await page.locator('#map-metadata-cache').isChecked())throw Error('Map metadata comparison choice did not persist');
 if(!await page.locator('#render-trace').isChecked())throw Error('Render trace choice did not persist');
 await page.locator('[data-action="client_start"]').click();await page.waitForTimeout(50);
 if(!await page.evaluate(()=>window.calls.some(c=>c.op==='client_start'&&c.args.runtime_backend==='fex-arm64ec-1'&&c.args.cold_trace===true&&c.args.managed_diagnostics===true&&c.args.render_trace===true&&c.args.sdl_graphics_fixes===false&&c.args.audio_driver==='directsound'&&c.args.proot_acceleration===false&&c.args.music_cache===false&&c.args.frame_budget===false&&c.args.map_metadata_cache===false&&c.args.smooth_audio===false&&c.args.dirty_regions===false)))throw Error('Selected options missing from native launch');
 if(!await page.evaluate(()=>JSON.parse(localStorage.getItem('launch')).gump_space))throw Error('Launch option missing');
 await page.screenshot({path:'ui-reports/client-landscape.png',fullPage:true});
 await page.setViewportSize({width:412,height:915});await page.screenshot({path:'ui-reports/client-phone.png',fullPage:true});
 for(const tab of ['realm','client','saves','journal']){
  await page.locator(`[data-tab="${tab}"]`).click();
  if(!await page.evaluate(tab=>document.body.dataset.scene===tab&&getComputedStyle(document.querySelector('#'+tab+' .scene-card')).backgroundImage.includes('background-'+tab+'.png'),tab))throw Error(tab+' background missing');
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error(tab+' overflows narrow viewport');
 }
 // A held native Play request owns startup; every competing mutation stays disabled.
 await page.locator('[data-tab="realm"]').click();
 await page.evaluate(()=>{window.calls=[];window.holdSession=true;window.nativeReport={session_busy:false};});
 await page.locator('[data-action="session_play"]').click();
 await page.waitForFunction(()=>!!window.heldSession);
 if(!await page.locator('[data-action="session_play"]').isDisabled()||!await page.locator('[data-action="server_start"]').isDisabled())throw Error('Concurrent launch controls remain enabled');
 await page.evaluate(async()=>{await refresh();document.querySelector('[data-action="server_start"]').click();});
 await page.waitForFunction(()=>document.getElementById('session-status').textContent.includes('waiting for the world'));
 if(!await page.locator('[data-action="session_cancel"]').isEnabled()||!await page.locator('[data-action="session_cancel"]').isVisible())throw Error('Launch cancellation is unavailable while Play owns the session');
 if(await page.evaluate(()=>window.calls.some(c=>c.op==='server_start'||c.op==='client_start')))throw Error('UI dispatched competing native startup');
 if(!await page.evaluate(()=>window.calls.some(c=>c.op==='session_play'&&c.args.runtime_backend==='fex-arm64ec-1'&&c.args.display_fps===60&&c.args.smooth_audio===false&&c.args.dirty_regions===false)))throw Error('Play did not preserve selected launch options');
 await page.evaluate(()=>{window.holdSession=false;window.nativeReport={session_busy:false};window.nativeReply(window.heldSession,{ok:true,result:{message:'Your world is ready.'}});});
 await page.waitForFunction(()=>!document.querySelector('[data-action="session_play"]').disabled);
 // Failed prerequisites reveal the right setup section and never try to open a display.
 await page.evaluate(()=>{window.calls=[];window.sessionFailure='Open Client setup and install the FEX client runtime first';});
 await page.locator('[data-action="session_play"]').click();
 await page.waitForFunction(()=>document.getElementById('client-setup').open&&document.getElementById('notice').classList.contains('error'));
 if(!await page.locator('#client').evaluate(node=>node.classList.contains('active')))throw Error('Client setup error did not select Client tab');
 if(await page.evaluate(()=>window.calls.some(c=>c.op==='client_view'||c.op==='client_start')))throw Error('Failed startup opened the client');
 await page.evaluate(()=>{window.sessionFailure='';window.realmReport={running:true,ready:false};});
 await page.waitForFunction(async()=>{await refresh();return document.getElementById('server-badge').textContent==='SERVER STARTING';});
 await page.evaluate(()=>{window.realmReport={running:true,ready:true};});
 await page.waitForFunction(async()=>{await refresh();return document.getElementById('server-badge').textContent==='SERVER ONLINE';});
 // The archive catalog survives an empty job list and a closed runtime.
 await page.evaluate(()=>{window.realmReport={running:false,ready:false,jobs:[]};window.nativeReport={alive:false,session_busy:false};});
 await page.locator('[data-tab="saves"]').click();
 await page.waitForFunction(()=>document.querySelectorAll('.backup-card').length===2);
 await page.evaluate(async()=>{await refresh();await refresh();});
 if(await page.locator('.backup-card').count()!==2)throw Error('Persistent archive inventory lost or duplicated');
 if(!await page.locator('.backup-card .exported').count()||!await page.locator('.backup-card .not-exported').count())throw Error('Export status missing');
 await page.locator('.backup-card').first().getByRole('button',{name:'Preview / restore'}).click();
 await page.locator('#restore-preview').waitFor({state:'visible'});
 if(!await page.locator('#restore-preview').isVisible()||!await page.locator('#restore-folders').textContent().then(text=>text.includes('Info, Saves, Backups')))throw Error('Restore preview missing');
 await page.screenshot({path:'ui-reports/restore-phone.png',fullPage:true});
 await page.locator('#cancel-restore').click();
 if(await page.evaluate(()=>window.calls.some(call=>call.op==='restore_world')))throw Error('Preview cancellation changed the world');
 await page.evaluate(()=>{window.settingsFixture.fields.find(field=>field.name==='S_WebsiteName').value=null;window.settingsFixture.fields.find(field=>field.name==='S_WebsiteLink').value='Existing\nmultiline text';});
 await page.locator('[data-tab="realm"]').click();await page.locator('#server-settings > summary').click();
 await page.waitForSelector('#setting-S_ServerSaveMinutes');
 if(await page.locator('#settings-dirty').textContent()!=='No unsaved changes.')throw Error('Loading settings modified untouched nullable or multiline text');
 await page.locator('#setting-S_ServerSaveMinutes').fill('45');
 await page.waitForFunction(()=>document.getElementById('settings-dirty').textContent.includes('1 unsaved'));
 await page.locator('[data-action="settings_save"]').click();
 await page.waitForFunction(()=>window.calls.some(call=>call.op==='settings_save'&&call.args.changes.S_ServerSaveMinutes===45));
 if(!await page.evaluate(()=>window.calls.filter(call=>call.op==='settings_save').every(call=>Object.keys(call.args.changes).length===1)))throw Error('Saving edited settings rewrote untouched values');
 await page.waitForFunction(()=>document.getElementById('settings-dirty').textContent==='No unsaved changes.');
 if(!await page.locator('[data-action="settings_undo"]').isEnabled())throw Error('Undo not available after settings save');
 await page.locator('#settings-search').fill('skill');
 if(await page.locator('.setting-field:not([hidden])').count()===0)throw Error('Settings search has no results');
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Settings editor overflows phone viewport');
 await page.screenshot({path:'ui-reports/settings-phone.png',fullPage:true});
 await page.evaluate(()=>{window.nativeReport={alive:true,session_busy:false};window.realmReport={running:true,ready:true,jobs:[]};});
 await page.locator('#settings-search').fill('');await page.locator('#setting-S_ServerSaveMinutes').fill('50');
 await page.waitForFunction(async()=>{await refresh();return document.querySelector('[data-action="settings_save"]').disabled;});
 if(!await page.locator('[data-action="settings_save"]').isDisabled())throw Error('Settings can be applied while server is running');
 await page.locator('[data-action="settings_reset"]').click();
 await page.locator('[data-tab="saves"]').click();await page.screenshot({path:'ui-reports/saves-phone.png',fullPage:true});
 await page.locator('.backup-card').first().getByRole('button',{name:'Preview / restore'}).click();
 await page.locator('#restore-preview').waitFor({state:'visible'});
 await page.evaluate(()=>window.restoreFailure='Save acknowledgement failed; world was kept.');
 await page.locator('#confirm-restore').click();
 await page.waitForFunction(()=>document.getElementById('restore-status').textContent.includes('world was kept')&&!document.getElementById('confirm-restore').disabled);
 if(!await page.locator('#restore-status').isVisible())throw Error('Restore failure is hidden behind the dialog');
 await page.evaluate(()=>window.restoreFailure='');
 await page.locator('#confirm-restore').click();await page.waitForFunction(()=>window.calls.some(call=>call.op==='restore_world'));
 if(!await page.evaluate(()=>{const close=window.calls.findIndex(call=>call.op==='session_close'),restore=window.calls.findIndex(call=>call.op==='restore_world');return close>=0&&restore>close;}))throw Error('Restore did not save and close the session first');
 await page.waitForFunction(()=>!document.getElementById('restore-preview').open);
 // Complete session backups retain an export link after a cancelled external picker.
 await page.locator('[data-tab="journal"]').click();
 await page.evaluate(()=>{window.calls=[];window.exportFailure='Export cancelled. The app copy was kept.';});
 await page.locator('[data-action="session_backup"]').click();
 await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('app copy was kept'));
 if(!await page.evaluate(()=>{const backup=window.calls.find(call=>call.op==='session_backup'),exported=window.calls.find(call=>call.op==='export');return backup?.args.ui.launch.display_fps===60&&backup.args.ui.source.source==='custom'&&backup.args.ui.source.ref==='custom-branch'&&exported?.args.path==='exports/memento-session-1.zip';}))throw Error('Complete session backup missed source/launch preferences or export');
 if(await page.locator('#session-backup-list .backup-card').count()!==1)throw Error('Cancelled export lost the complete session backup link');
 await page.evaluate(()=>window.exportFailure='');
 await page.locator('#session-backup-list').getByRole('button',{name:'Export',exact:true}).click();
 await page.waitForFunction(()=>window.calls.filter(call=>call.op==='export').length===2);
 await page.waitForFunction(()=>!!document.querySelector('#session-backup-list .exported'));
 if(await page.evaluate(()=>window.calls.filter(call=>call.op==='session_backup').length)!==1)throw Error('Retrying export recreated the complete session archive');
 // Preview and cancellation are available while the runtimes are closed, without replacing data.
 await page.evaluate(()=>{window.calls=[];window.nativeReport={alive:false,installed:false,session_busy:false};window.clientActive=true;});
 await page.evaluate(async()=>await refresh());
 await page.locator('[data-pick="session"]').click();
 await page.locator('#session-restore-preview').waitFor({state:'visible'});
 if(!await page.locator('#session-restore-components').textContent().then(text=>text.includes('Wine prefix')&&text.includes('launcher settings')))throw Error('Complete session preview is missing its component list');
 if(!await page.locator('#session-restore-preview').textContent().then(text=>text.includes('Components absent from the backup are removed')&&text.includes('snapshot')))throw Error('Complete replacement and snapshot confirmation are unclear');
 await page.setViewportSize({width:360,height:800});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Complete session dialog overflows 360px viewport');
 await page.screenshot({path:'ui-reports/session-restore-phone.png',fullPage:true});
 await page.locator('#cancel-session-restore').click();
 if(await page.evaluate(()=>window.calls.some(call=>call.op==='session_restore')))throw Error('Cancelling complete session preview restored data');
 if(!await page.evaluate(()=>window.calls.some(call=>call.op==='discard_import'&&call.args.file==='85e774ed-5192-4fd2-a402-19a9d1ae0f45.zip')))throw Error('Cancelled complete session import was kept in staging');
 // Native restore errors stay visible; successful restoration restores preferences and settings.
 await page.locator('[data-pick="session"]').click();await page.locator('#session-restore-preview').waitFor({state:'visible'});
 await page.evaluate(()=>window.sessionRestoreFailure='Snapshot could not be created; installation was kept.');
 await page.locator('#confirm-session-restore').click();
 await page.waitForFunction(()=>document.getElementById('session-restore-status').textContent.includes('installation was kept')&&!document.getElementById('confirm-session-restore').disabled);
 if(!await page.locator('#session-restore-status').isVisible())throw Error('Complete session restore error is hidden behind its dialog');
 const settingsReadsBeforeSessionRestore=await page.evaluate(()=>window.calls.filter(call=>call.op==='settings_read').length);
 await page.evaluate(()=>window.sessionRestoreFailure='');
 await page.locator('#confirm-session-restore').click();
 await page.waitForFunction(()=>!document.getElementById('session-restore-preview').open);
 if(!await page.evaluate(()=>window.calls.some(call=>call.op==='session_restore'&&call.args.file==='85e774ed-5192-4fd2-a402-19a9d1ae0f45.zip'&&call.args.ui.source.source==='custom'&&call.args.ui.launch.display_fps===60)))throw Error('Restore did not pass current preferences for the pre-restore snapshot');
 if(await page.locator('#source-kind').inputValue()!=='fork'||await page.locator('#source-ref').inputValue()!=='restored-tag'||await page.locator('#custom-source').isVisible())throw Error('Complete session restore lost source preferences');
 if(await page.locator('#renderer').inputValue()!=='virgl'||await page.locator('#resolution').inputValue()!=='1024x768'||await page.locator('#fps').inputValue()!=='30'||!await page.locator('#audio').isChecked())throw Error('Complete session restore lost launch preferences');
 if(await page.evaluate(()=>window.calls.filter(call=>call.op==='settings_read').length)<=settingsReadsBeforeSessionRestore)throw Error('Complete session restore kept stale server settings');
 if(!await page.evaluate(()=>localStorage.getItem('session-ui-revision')==='restored-ui-1'&&JSON.parse(localStorage.getItem('realm-source')).ref==='restored-tag'&&JSON.parse(localStorage.getItem('launch')).renderer==='virgl'))throw Error('Restored UI preferences did not persist');
 await page.waitForFunction(()=>document.querySelectorAll('#session-backup-list .backup-card').length===2);
 if(!await page.locator('#session-backup-list').textContent().then(text=>text.includes('Before complete session restore')))throw Error('Automatic pre-restore snapshot lacks an export link');
 await page.locator('#session-backup-list .backup-card').first().getByRole('button',{name:'Preview / restore'}).click();await page.locator('#session-restore-preview').waitFor({state:'visible'});await page.locator('#cancel-session-restore').click();
 if(!await page.evaluate(()=>window.calls.some(call=>call.op==='session_backup_preview'&&call.args.file==='exports/memento-session-before-restore.zip')))throw Error('Stored complete session backup cannot be previewed');
 if(!await page.evaluate(()=>window.calls.every(call=>call.op!=='discard_import'||!call.args.file.startsWith('exports/'))))throw Error('Cancelling catalog preview tried to discard an app session backup');
 if(!await page.locator('#notice').textContent().then(text=>text.includes('restore cancelled')))throw Error('Cancelling a catalog preview reported an error');
 for(const tab of ['realm','client','saves','journal']){
  await page.locator(`[data-tab="${tab}"]`).click();
  if(tab==='realm'){await page.locator('#realm-setup').evaluate(node=>node.open=true);await page.locator('#source-kind').selectOption('custom');await page.locator('#source-repository').fill('https://github.com/example/a-long-server-repository-name-for-mobile-layout.git');}
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error(tab+' overflows 360px viewport with source/session controls');
 }
 // A recovered native transaction applies its saved preferences once, preserving later edits.
 await page.addInitScript(()=>{window.sessionUiPreferences={ui:{launch:{renderer:'software',resolution:'800x600',display_fps:30,audio:false,gump_space:false},source:{source:'upstream',ref:'recovered-tag'}},revision:'recovered-ui-2'};});
 await page.reload();
 await page.waitForFunction(()=>localStorage.getItem('session-ui-revision')==='recovered-ui-2');
 if(await page.locator('#source-ref').inputValue()!=='recovered-tag'||await page.locator('#renderer').inputValue()!=='software')throw Error('Recovered native session restore did not apply its UI preferences');
 await page.locator('[data-tab="journal"]').click();await page.waitForFunction(()=>document.querySelectorAll('#session-backup-list .backup-card').length===2);
 if(!await page.locator('#session-backup-list .exported').count())throw Error('Reopening the app lost complete session export status');
 await page.locator('[data-tab="realm"]').click();
 await page.locator('#realm-setup').evaluate(node=>node.open=true);await page.locator('#source-ref').fill('after-recovery');
 await page.locator('[data-tab="client"]').click();await page.locator('#client-options > summary').click();await page.locator('#renderer').selectOption('virgl');
 await page.reload();
 if(await page.locator('#source-ref').inputValue()!=='after-recovery'||await page.locator('#renderer').inputValue()!=='virgl')throw Error('Native restore preference revision overwrote later user edits');
 await page.locator('[data-tab="realm"]').click();
 // Cancel Play uses the dedicated shutdown action while ordinary mutations stay locked.
 await page.evaluate(()=>{window.holdSession=true;window.nativeReport={alive:true,session_busy:false};window.realmReport={running:false,ready:false,jobs:[]};window.mockJobs=[];});
 await page.locator('[data-action="session_play"]').click();
 await page.waitForFunction(async()=>{await refresh();return !document.querySelector('[data-action="session_cancel"]').hidden;});
 await page.locator('[data-action="session_cancel"]').click();
 await page.waitForFunction(()=>window.calls.some(call=>call.op==='session_cancel')&&!document.querySelector('[data-action="session_play"]').disabled);
 await page.evaluate(()=>{window.realmReport={running:false,ready:false,jobs:[]};document.getElementById('client-options').open=false;document.getElementById('client-setup').open=false;});
 await page.locator('[data-tab="client"]').click();await page.screenshot({path:'ui-reports/client-phone-collapsed.png',fullPage:true});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Collapsed client view overflows phone viewport');
 if(errors.length)throw Error(errors.join('\n'));
 console.log('Client options, guarded Play, source selection and offline compile, save-data backups, complete session backup/restore and recovery, settings, and 360px/phone/landscape layouts passed');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
