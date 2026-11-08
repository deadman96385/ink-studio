"""Release identity without importing an engine or inspecting user documents."""
import json
import os
from pathlib import Path


def current():
    root = Path(__file__).absolute().parent.parent
    package = root / 'package.json'
    if package.is_file():
        return json.loads(package.read_text(encoding='utf-8'))['version']
    version = root / 'VERSION'
    if version.is_file():
        return version.read_text(encoding='utf-8').strip()
    return os.environ.get('STUDIO_APP_VERSION', 'development')
