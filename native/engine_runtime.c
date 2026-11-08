/* Host the Python runtime already shipped with the pinned Ink/Stitch bundle.
 * No second Python installation or replacement embroidery implementation. */
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>
#include <string.h>
#include <locale.h>

int main(int argc, char **argv) {
    setlocale(LC_ALL, "");
    const char *engine = getenv("STUDIO_INKSTITCH");
    if (!engine) engine = "/opt/inkstitch/bin/inkstitch";
    char *bundle = strdup(engine);
    if (!bundle) return 3;
    char *slash = strrchr(bundle, '/');
    if (!slash) { free(bundle); return 2; }
    *slash = '\0';
    size_t capacity = strlen(bundle) * 3 + 256;
    char *path = malloc(capacity);
    if (!path) { free(bundle); return 3; }
    snprintf(path, capacity, "%s/libpython3.11.so.1.0", bundle);
    void *lib = dlopen(path, RTLD_NOW | RTLD_GLOBAL);
    if (!lib) { fprintf(stderr, "Ink/Stitch Python: %s\n", dlerror()); return 1; }
    void (*set_path)(const wchar_t *) = dlsym(lib, "Py_SetPath");
    void (*initialize)(void) = dlsym(lib, "Py_Initialize");
    void (*set_args)(int, wchar_t **, int) = dlsym(lib, "PySys_SetArgvEx");
    int (*run)(const char *) = dlsym(lib, "PyRun_SimpleString");
    int (*finish)(void) = dlsym(lib, "Py_FinalizeEx");
    if (!set_path || !initialize || !set_args || !run || !finish) return 2;
    *(int *)dlsym(lib, "Py_IgnoreEnvironmentFlag") = 1;
    *(int *)dlsym(lib, "Py_NoSiteFlag") = 1;
    snprintf(path, capacity, "%s/base_library.zip:%s/python3.11/lib-dynload:%s", bundle, bundle, bundle);
    size_t path_size = mbstowcs(NULL, path, 0);
    if (path_size == (size_t)-1) { free(path); free(bundle); return 4; }
    wchar_t *search = calloc(path_size + 1, sizeof(wchar_t));
    if (!search) { free(path); free(bundle); return 3; }
    mbstowcs(search, path, path_size + 1);
    set_path(search);
    initialize();
    wchar_t **wide = calloc(argc + 1, sizeof(wchar_t *));
    if (!wide) return 3;
    for (int i = 0; i < argc; i++) {
        size_t size = mbstowcs(NULL, argv[i], 0);
        if (size == (size_t)-1) return 4;
        wide[i] = calloc(size + 1, sizeof(wchar_t));
        if (!wide[i]) return 3;
        mbstowcs(wide[i], argv[i], size + 1);
    }
    set_args(argc, wide, 0);
    int status = run("import os; p=os.environ.get('STUDIO_ENGINE_BOOTSTRAP','/native/engine_runtime.py'); __file__=p; exec(compile(open(p,'rb').read(),p,'exec'))");
    int finalized = finish();
    for (int i = 0; i < argc; i++) free(wide[i]);
    free(wide);
    free(search); free(path); free(bundle);
    return status || finalized < 0 ? 1 : 0;
}
