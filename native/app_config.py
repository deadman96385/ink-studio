"""Installed/portable layouts, separate from the source and Linux entry points."""
import json
import os
from pathlib import Path
import platform
import uuid


def app_root():
    return Path(__file__).absolute().parent.parent


def packaged():
    return (app_root() / 'package.json').is_file()


def state_home():
    override = os.environ.get('STUDIO_STATE_HOME')
    if override:
        return Path(override).expanduser().absolute()
    if (app_root() / 'portable.txt').is_file():
        return app_root()
    if platform.system() == 'Windows':
        return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Ink Studio'
    return Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'ink-studio'


def settings_path():
    if platform.system() != 'Windows' and not os.environ.get('STUDIO_STATE_HOME') and not (app_root() / 'portable.txt').is_file():
        return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'ink-studio/settings.json'
    return state_home() / 'config' / 'settings.json'


def load_settings():
    path = settings_path()
    value = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    if not isinstance(value, dict):
        raise ValueError('Ink Studio settings must be a JSON object.')
    port = value.get('port', 8801)
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('Choose a port from 1024 to 65535 in Ink Studio Settings.')
    for key in ('inkscape', 'inkstitch', 'dataDirectory'):
        if not isinstance(value.get(key, ''), str):
            raise ValueError('Check the ' + key + ' setting in Ink Studio Settings.')
    return value


def save_settings(changes):
    value = load_settings()
    value.update(changes)
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


def prepare_environment():
    """Set only this process's environment; never edit system/profile settings."""
    settings = load_settings()
    home = state_home()
    windows = platform.system() == 'Windows'
    default_data = home / 'data' if windows else Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'ink-studio'
    os.environ.setdefault('STUDIO_DATA', settings.get('dataDirectory') or str(default_data))
    os.environ.setdefault('STUDIO_ENGINE_CONFIG', str(Path(os.environ['STUDIO_DATA']) / 'config' / 'inkstitch'))
    os.environ.setdefault('STUDIO_PORT', str(settings.get('port', 8801)))
    for key, setting in [('STUDIO_INKSCAPE', 'inkscape'), ('STUDIO_INKSTITCH', 'inkstitch')]:
        if settings.get(setting):
            os.environ.setdefault(key, settings[setting])

