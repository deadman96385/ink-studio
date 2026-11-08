from pathlib import Path

config = Path('/defaults/default.conf')
source = config.read_text()
location = '''  location /design-files/ {
    alias /designs/;
    autoindex on;
    autoindex_format json;
    add_header Cache-Control "no-store";
    add_header Content-Disposition "attachment";
    add_header X-Content-Type-Options "nosniff";
  }
'''
assert source.count('  error_page 500') == 2
config.write_text(source.replace('  error_page 500', location + '  error_page 500'))
