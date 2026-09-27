"""Page modules. build.py loads pages/core.py first, then every other pages/<name>.py in alphabetical order —
adding a module is the whole registration (docs/PLUGINS.md). A module provides:

  register(site) -> Plugin | list[Page]   its pages, data files, sitemap entries, nav items, slots, page_js
  CSS = ("name", …)       src/css/<name>.css appended to /assets/cinema.css, in module order
  JS = ("name", …)        src/js/<name>.js into the main bundle (before main.js; it calls feature(fn))
  LAZY_JS = ("name", …)   src/js/<name>.js as /assets/<name>.<hash>.js, loaded only on pages that ask for it
  DIRS = ("name", …)      top-level out/ folders the module owns (cleared before each build)
  ASSET_DIR               optional: where its CSS/JS files are, instead of src/css and src/js (tests)

CSS/JS/LAZY_JS/DIRS are read without calling register: the client bundle is built before any page."""
import importlib, importlib.util, os

HERE = os.path.dirname(os.path.abspath(__file__))


def names():
    """core, then the other modules alphabetically (a leading underscore keeps a file out)."""
    rest = sorted(f[:-3] for f in os.listdir(HERE) if f.endswith(".py") and not f.startswith("_") and f != "core.py")
    return ["core"] + rest


def discover(only=None, extra=()):
    """The page modules, loaded, in build order. `only`: a subset by name (the golden test builds core alone);
    `extra`: paths of modules outside the package, appended last (tests, docs examples)."""
    mods = [importlib.import_module("pages." + n) for n in names() if only is None or n in only]
    for path in extra:
        name = "pages_extra_" + os.path.splitext(os.path.basename(path))[0]
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mods.append(mod)
    return mods
