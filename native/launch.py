"""Run the same editor on Windows or Linux with an installed engine."""
import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--data', type=Path)
    parser.add_argument('--inkscape', type=Path)
    parser.add_argument('--inkstitch', type=Path)
    parser.add_argument('--check', action='store_true', help='Check the installations without starting the server')
    parser.add_argument('--diagnostics', type=Path, help='Save a report without personal paths, logs or designs')
    parser.add_argument('--report', type=Path, help='Save the --check report')
    parser.add_argument('--setup-tools', action='store_true', help='Prepare private Inkscape on Windows; Linux uses installed tools')
    parser.add_argument('--offline', action='store_true', help='Never download tool inputs')
    parser.add_argument('--configure', action='store_true', help='Save supplied tool/folder/port choices without starting the editor')
    parser.add_argument('--open-browser', action='store_true', help='Open the editor after this server becomes ready')
    parser.add_argument('--instance-id', default='', help=argparse.SUPPRESS)
    options = parser.parse_args()
    if options.port is not None:
        os.environ['STUDIO_PORT'] = str(options.port)
    os.environ['STUDIO_HOST'] = options.host
    os.environ['STUDIO_INSTANCE_ID'] = options.instance_id
    for key, value in [('STUDIO_DATA', options.data), ('STUDIO_INKSCAPE', options.inkscape), ('STUDIO_INKSTITCH', options.inkstitch)]:
        if value is not None:
            os.environ[key] = str(value.expanduser().absolute())
    import app_config
    import setup_check
    setup_check.enable_private_log()
    if options.configure:
        changes = {name: str(value.expanduser().absolute()) for name, value in
                   [('inkscape', options.inkscape), ('inkstitch', options.inkstitch), ('dataDirectory', options.data)] if value is not None}
        if options.port is not None:
            if not 1024 <= options.port <= 65535:
                parser.error('Choose a port from 1024 to 65535.')
            changes['port'] = options.port
        app_config.save_settings(changes)
    checking = options.check or options.diagnostics or options.setup_tools or options.configure
    report, runtime = setup_check.check(prepare_tools=options.setup_tools, apply=not checking, offline=options.offline)
    if checking or not report['ready']:
        setup_check.emit(report, options.diagnostics or options.report)
        return 0 if report['ready'] else 2
    if options.open_browser:
        import json
        import threading
        import time
        import urllib.request
        import webbrowser
        def open_when_ready():
            url = 'http://127.0.0.1:' + str(runtime.port)
            for _ in range(240):
                try:
                    with urllib.request.urlopen(url + '/api/health', timeout=1) as response:
                        health = json.load(response)
                    if health.get('pid') == os.getpid():
                        webbrowser.open(url + '/')
                        return
                except OSError:
                    pass
                time.sleep(.25)
        threading.Thread(target=open_when_ready, daemon=True).start()
    # Explicit UTF-8 file encodings are used for persisted JSON. The launchers
    # additionally use -X utf8 for third-party libraries and remaining IO.
    import server
    server.main()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError):
        import setup_check
        setup_check.emit(setup_check.failure('configuration-failed', 'Setup or diagnostics could not be completed.', 'Check settings and choose a writable diagnostics filename. Existing non-diagnostic files are never overwritten.'))
        raise SystemExit(2)
