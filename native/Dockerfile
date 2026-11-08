FROM web-ink:3.3.0
USER root
RUN /lsiopy/bin/pip install --no-cache-dir pystitch==1.0.0 tinycss2==1.4.0 cssselect==1.3.0 webencodings==0.6.1 shapely==2.1.2 pillow-heif==1.8.1 diskcache==5.6.3 fonttools==4.68.0 weasyprint==66.0
COPY engine_runtime.c /tmp/native-engine-runtime.c
RUN cc -O2 -Wall -Wextra -o /usr/local/bin/native-inkstitch-info /tmp/native-engine-runtime.c -ldl && rm /tmp/native-engine-runtime.c
ENV HOME=/tmp/native-home XDG_CONFIG_HOME=/tmp/native-home/.config
USER 1000:1000
ENTRYPOINT ["/usr/bin/xvfb-run", "-a", "-s", "-screen 0 1600x1200x24", "/lsiopy/bin/python3", "/native/server.py"]
