"""Run an installed extension with Studio's private settings and binary stdout."""
import argparse
import sys


def main():
    from lib import extensions
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--extension', required=True)
    options, remaining = parser.parse_known_args(sys.argv[1:])
    name = options.extension.title().replace('_', '')
    extension = getattr(extensions, name, None)
    if extension is None:
        raise ValueError('The installed Ink/Stitch does not provide ' + options.extension)
    if sys.platform=='win32' and options.extension=='letters_to_font':
        # The installed tool searches both *.SVG and *.svg. Windows matches
        # both patterns case-insensitively, returning every input twice.
        class UniqueLetters(extension):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs)
                self._studio_glyph_files=set()
            def get_glyph_element(self,glyph):
                key=str(glyph.absolute()).casefold()
                if key in self._studio_glyph_files:return None
                self._studio_glyph_files.add(key)
                return super().get_glyph_element(glyph)
        extension=UniqueLetters
    extension().run(args=remaining)
