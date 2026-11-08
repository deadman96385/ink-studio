"""Capture installed stitch classification without a desktop IPC receiver."""
import io
import json
import sys
from lib.extensions.select_elements import SelectElements


def main():
    result = {}
    class Capture(SelectElements):
        def effect(self):
            result['ids'] = [value for value in self._get_id_list().split(',') if value]
    Capture().run(sys.argv[1:], output=io.BytesIO())
    print(json.dumps(result))
