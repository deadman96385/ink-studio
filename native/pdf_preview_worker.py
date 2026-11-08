"""Render one bounded PDF preview on Windows without a Poppler installation."""
import sys
import pypdfium2 as pdfium


def main():
    source, number, target = sys.argv[1:]
    with pdfium.PdfDocument(source) as document:
        index = int(number) - 1
        if not 0 <= index < len(document):
            raise ValueError('Choose an available print page.')
        page = document[index]
        try:
            scale = 1400 / max(page.get_size())
            bitmap = page.render(scale=scale)
            try:
                image = bitmap.to_pil()
                try:image.save(target, format='PNG')
                finally:image.close()
            finally:bitmap.close()
        finally:page.close()


if __name__ == '__main__':
    main()
