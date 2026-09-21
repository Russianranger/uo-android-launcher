"""Compose reversible scheduling and render probes for the exact supported DLL."""
import base64
import hashlib
from pathlib import Path

import client_render_trace as trace
from client_graphics import digest
from uo_content import confined

BUDGET = '03177f03654e5bea7aafedc93876ec34d81ad1c0f0c89c852526019cf5aa8585'
COMBINED = '433f40da7280f1a3e379eb5716561cac21d94d6e5574e3e4e09b44f770298e71'
PATCH = 'tazuo-5.2-frame-budget.patch.b64'
COMBINED_PATCH = 'tazuo-5.2-frame-budget-render.patch.b64'
HELPER = 'Memento.FrameBudget.dll'
BACKUP = 'TazUO.dll.before-memento-frame-budget'


def prepare(root, metadata, runtime_assets, enabled=True, render_enabled=False):
    if not isinstance(enabled, bool) or not isinstance(render_enabled, bool):raise ValueError('Invalid client scheduling option')
    folder = confined(root, metadata['executable']).parent
    def library(name):
        matches = [p for p in folder.iterdir() if p.name.lower() == name.lower()]
        if len(matches) > 1:raise ValueError('Duplicate client library: '+name)
        candidate = matches[0] if matches else folder/name
        if candidate.is_symlink():raise ValueError('Client library must not be a symbolic link')
        return confined(root, candidate.relative_to(root))
    target, fna = library('TazUO.dll'), library('FNA.dll')
    current, fna_hash = digest(target), digest(fna)
    frame = {'requested':enabled, 'active':False, 'revision':1, 'budget_ms':5, 'packet_limit':1000, 'before_sha256':current}
    render = {'requested':render_enabled, 'active':False, 'diagnostic_only':True, 'before_sha256':current, 'fna_sha256':fna_hash}
    known = (trace.ORIGINAL, trace.INSTRUMENTED, BUDGET, COMBINED)
    if current not in known:
        for report in (frame, render):report.update(action='unchanged_unrecognized_client', active_sha256=current)
        return {'frame_budget':frame, 'render_trace':render}
    assets = Path(runtime_assets)
    use_frame, use_render = enabled and fna_hash == trace.FNA, render_enabled and fna_hash == trace.FNA
    desired = COMBINED if use_frame and use_render else BUDGET if use_frame else trace.INSTRUMENTED if use_render else trace.ORIGINAL
    backups = []
    if current in (BUDGET, COMBINED):backups.append(folder/BACKUP)
    if current in (trace.INSTRUMENTED, COMBINED):backups.append(folder/trace.BACKUP)
    for backup in backups:
        if backup.is_symlink() or digest(backup) != trace.ORIGINAL:
            raise ValueError('Original client backup is missing or changed: '+backup.name+'; restore TazUO.dll from the original client package')
    for active, name in ((use_frame, HELPER), (use_render, trace.HELPER)):
        if active and not (assets/name).is_file():raise ValueError('Client timing component is missing; reinstall the current APK')
    new_backups = ([folder/BACKUP] if use_frame else []) + ([folder/trace.BACKUP] if use_render else [])
    for backup in new_backups:
        if backup.is_symlink() or (backup.exists() and digest(backup) != trace.ORIGINAL):
            raise ValueError('Original client backup has changed: '+backup.name)
    action = 'already_active' if desired != trace.ORIGINAL else 'unchanged_original'
    if desired != current:
        original = target.read_bytes() if current == trace.ORIGINAL else backups[0].read_bytes()
        if hashlib.sha256(original).hexdigest() != trace.ORIGINAL:raise ValueError('Original client checksum mismatch')
        updated = original
        if desired != trace.ORIGINAL:
            name = COMBINED_PATCH if desired == COMBINED else PATCH if desired == BUDGET else trace.PATCH
            raw = (assets/name).read_bytes()
            if len(raw) > trace.LIMIT:raise ValueError('Client patch is too large')
            updated = trace.apply_delta(original, base64.b64decode(raw.strip(), validate=True))
            if hashlib.sha256(updated).hexdigest() != desired:raise ValueError('Client scheduling output checksum mismatch')
        for backup in new_backups:
            if not backup.exists():trace.atomic_write(backup, original, trace.ORIGINAL)
        trace.atomic_write(target, updated, desired)
        action = 'restored_original' if desired == trace.ORIGINAL else 'updated_known_client'
    for report, active, helper in ((frame,use_frame,HELPER),(render,use_render,trace.HELPER)):
        report.update(active=active, action=action, active_sha256=desired)
        if active:report['helper_sha256']=digest(assets/helper)
    return {'frame_budget':frame, 'render_trace':render}
