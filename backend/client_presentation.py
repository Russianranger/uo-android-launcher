"""Optional native Surface transport; the working RFB path stays available."""
import hashlib
import json
from pathlib import Path
import time


def options(request):
    mode, fps = request.get('presentation_mode', 'rfb'), request.get('display_fps', 30)
    if mode not in ('rfb', 'native_surface') or type(fps) is not int or fps not in (30, 60):
        raise ValueError('Unsupported display presentation option')
    return mode, fps


def start(supervisor):
    mode, fps = options(supervisor.request)
    result = {'presentation_requested': mode, 'presentation_active': 'rfb', 'display_target_fps': fps}
    if mode == 'rfb': return result
    # A missing/failed prototype does not prevent the game using its current display.
    try:
        root = Path(__file__).parent
        binary = root/'x11-frame-bridge'
        manifest = json.loads((root/'presentation-bundle.json').read_text())
        if manifest.get('format') != 1 or binary.is_symlink() or hashlib.sha256(binary.read_bytes()).hexdigest() != manifest['sha256']:
            raise ValueError('Presentation helper failed verification')
        sock = Path(supervisor.env['XAUTHORITY']).parent/'frames.sock'
        sock.unlink(missing_ok=True)
        process = supervisor.spawn([str(binary), str(sock), str(fps)], 'client-frame-bridge.log')
        for _ in range(30):
            if process.poll() is not None: raise RuntimeError('Presentation helper exited; see client-frame-bridge.log')
            if sock.exists():
                result['presentation_active'] = 'native_surface'
                return result
            time.sleep(.1)
        process.terminate()
        raise RuntimeError('Presentation helper did not become ready')
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        result['presentation_fallback'] = str(error)
        return result


def start_input(supervisor):
    """XTest relative input also works with the Current/RFB display path."""
    try:
        root = Path(__file__).parent
        binary = root/'x11-frame-bridge'
        manifest = json.loads((root/'presentation-bundle.json').read_text())
        if binary.is_symlink() or hashlib.sha256(binary.read_bytes()).hexdigest() != manifest['sha256']:
            raise ValueError('Relative input helper failed verification')
        sock = Path(supervisor.env['XAUTHORITY']).parent/'input.sock'
        sock.unlink(missing_ok=True)
        process = supervisor.spawn([str(binary),'--input',str(sock)],'client-input.log')
        for _ in range(30):
            if process.poll() is not None: raise RuntimeError('Relative input helper exited')
            if sock.exists(): return {'pointer_transport':'relative_xtest'}
            time.sleep(.1)
        process.terminate()
        raise RuntimeError('Relative input helper did not become ready')
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        return {'pointer_transport':'absolute_rfb','pointer_fallback':str(error)}
