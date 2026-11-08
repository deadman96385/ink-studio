"""Tune Selkies 2.1.0 direct-touch taps for desktop GTK/wx dialogs.

The upstream 250 ms tap limit leaves a dead zone before its 750 ms
right-click threshold. Deliberate iPad taps in that interval disappear.
Keep long press and drag intact, and give GTK a full 60 ms click pulse.
Anchors deliberately fail on an incompatible upstream update.
"""
from pathlib import Path

patches = {
    'this._TAP_THRESHOLD_DISTANCE_SQ=100,this._TAP_MAX_DURATION=250':
        'this._TAP_THRESHOLD_DISTANCE_SQ=196,this._TAP_MAX_DURATION=700',
    'setTimeout(()=>{this.buttonMask&=-2,this._sendMouseState()},10)':
        'setTimeout(()=>{this.buttonMask&=-2,this._sendMouseState()},60)',
}

def patch(path):
    source = path.read_text()
    for before, after in patches.items():
        if source.count(after) == 1:
            continue
        if source.count(before) != 1:
            raise RuntimeError(f'Selkies touch anchor changed: {path}: {before}')
        source = source.replace(before, after)
    path.write_text(source)

if __name__ == '__main__':
    patch(Path('/usr/share/selkies/selkies-dashboard/src/selkies-core.js'))
    bundles = list(Path('/usr/share/selkies/selkies-dashboard/assets').glob('selkies-core-*.js'))
    if not bundles:
        raise RuntimeError('Selkies dashboard core bundle missing')
    for bundle in bundles:
        patch(bundle)
