"""Private backend entry point used by the packaged Windows launcher."""
import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8801)
    parser.add_argument('--instance-id', default='')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--diagnostics', type=Path)
    parser.add_argument('--setup-tools', action='store_true')
    parser.add_argument('--offline', action='store_true')
    options = parser.parse_args()
    # The embedded runtime ignores ambient PYTHON* variables. Configure UTF-8
    # explicitly for third-party code, redirected logs and standalone workers.
    sys.dont_write_bytecode = True
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    os.environ['STUDIO_HOST'] = '127.0.0.1'
    os.environ['STUDIO_PORT'] = str(options.port)
    os.environ['STUDIO_INSTANCE_ID'] = options.instance_id
    import app_config
    import setup_check
    setup_check.enable_private_log()
    checking = options.check or options.diagnostics or options.setup_tools
    report, _ = setup_check.check(prepare_tools=options.setup_tools or not checking, apply=not checking, offline=options.offline)
    destination = options.diagnostics or options.report or (app_config.state_home() / 'logs/setup-check.json')
    try:
        setup_check.emit(report, destination)
    except (OSError, ValueError):
        print('The diagnostics report could not be saved. Choose a writable, new JSON filename.', file=sys.stderr)
        return 2
    if checking or not report['ready']:
        return 0 if report['ready'] else 2
    import server
    server.main()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        import traceback
        traceback.print_exc()
        print('Ink Studio could not start: ' + str(error), file=sys.stderr, flush=True)
        raise SystemExit(1)
