"""Golden: the page plug-ins (pages/, site_kit.py) changed how the site is generated, not what it is.

The phase-1 generator is taken from git (GOLDEN_REF, the last commit before the plug-ins) and both it and
the current one build the same inputs — the synthetic fixtures, and data/latest.json when this checkout has
one. The core-only build (pages/core.py alone) must write the same files with the same bytes once asset hashes
are normalised: every HTML page, every /data JSON, the sitemap, robots, the service worker, the stylesheet.
The one file allowed to differ is the client bundle (cinema.<hash>.js): it gained the feature registry.
The full build (every module under pages/) may only ADD files: phase-1 output is always a subset.

No git, or a clone without GOLDEN_REF (a shallow CI checkout): skipped."""
import io, json, os, re, shutil, subprocess, sys, zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402

GOLDEN_REF = os.environ.get("CINEMA_GOLDEN_REF", "c7ff237")   # docs: phase 2 spec and plan — phase-1 build.py
GIT = shutil.which("git")
CASES = [("sample", os.path.join(ROOT, "fixtures", "sample_latest.json"), os.path.join(ROOT, "fixtures", "sample_discounts.yaml")),
         ("latest", os.path.join(ROOT, "data", "latest.json"), os.path.join(ROOT, "discounts.yaml"))]
HALLS = os.path.join(ROOT, "halls.yaml")
HASHES = [(re.compile(r"\b(cinema|adhan)\.[0-9a-f]{10}\.js\b"), r"\1.HASH.js"),
          (re.compile(r"\?v=[0-9a-f]{10}\b"), "?v=HASH"),
          (re.compile(r'^var V = "[0-9a-f]{10}"', re.M), 'var V = "HASH"')]
TEXT = (".html", ".json", ".xml", ".txt", ".js", ".css", ".webmanifest", ".svg")
# Deliberate changes to the shared shell since phase 1, each named and undone before comparing (both sides,
# a no-op on phase 1): Task A4 (roadmap 203, 204, 138) — the bundle preload, the speculation rules and their
# data-saver/«back» script in every page's head; the bundle loaded by the «boot» loader that holds it while the
# page is prerendering (phase 1: a plain deferred <script>); the manifest's shortcuts and their three icons
# (tests/test_feel.py covers them).
SHELL_HTML = [(re.compile(r'<link rel="preload" href="[^"]+" as="script">\n'
                          r'<script type="speculationrules" id="spec">.*?</script>\n'
                          r'<script>\(function\(\)\{var c=navigator\.connection.*?</script>\n', re.S), ""),
              (re.compile(r'<script id="boot">\(function\(u,d\)\{.*?\}\)\("([^"]+)",document\)</script>'),
               r'<script src="\1" defer></script>')]
SHELL_FILES = re.compile(r"^assets/icons/sc-[a-z]+\.png$")


def _has_ref():
    if not GIT: return False
    r = subprocess.run([GIT, "-C", ROOT, "cat-file", "-e", GOLDEN_REF + "^{commit}"], capture_output=True)
    return r.returncode == 0


pytestmark = pytest.mark.skipif(not _has_ref(), reason=f"git or {GOLDEN_REF} not available")


@pytest.fixture(scope="module")
def phase1(tmp_path_factory):
    """The phase-1 tree at GOLDEN_REF, extracted (not checked out: the worktree is untouched)."""
    z = subprocess.run([GIT, "-C", ROOT, "archive", "--format=zip", GOLDEN_REF], capture_output=True, check=True).stdout
    d = tmp_path_factory.mktemp("phase1")
    zipfile.ZipFile(io.BytesIO(z)).extractall(d)
    return str(d)


def run_build(root, data, disc, out, mode="core", seed="0"):
    code = ("import sys, inspect; sys.path.insert(0, sys.argv[1]); import build\n"
            "kw = {}\n"
            "if sys.argv[6] == 'core' and 'modules' in inspect.signature(build.build).parameters:\n"
            "    kw['modules'] = build.discover(only=('core',))\n"
            "build.build(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], noindex=False, **kw)\n")
    # phase 1's discounts.json lists chains from a set (sorted since phase 2): a fixed seed keeps the old side
    # stable, and files() compares that file by content, not key order
    env = dict(os.environ, PYTHONHASHSEED=seed); env.pop("PREVIEW", None)
    r = subprocess.run([sys.executable, "-c", code, root, data, disc, out, HALLS, mode], cwd=root, env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert r.returncode == 0, r.stderr[-3000:]
    return out


def files(out):
    """{normalised relative path: normalised bytes} for everything a build wrote."""
    got = {}
    for dp, _, fs in os.walk(out):
        for f in fs:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, out).replace(os.sep, "/")
            if SHELL_FILES.match(rel): continue
            b = open(p, "rb").read()
            if rel.endswith(TEXT):
                t = b.decode("utf-8")
                if rel == "sw.js":   # the source hash is stamped for every __V__, its header comment too
                    v = re.search(r'^var V = "([0-9a-f]{10})"', t, re.M)
                    if v: t = t.replace(v.group(1), "HASH")
                for rx, to in HASHES: t = rx.sub(to, t)
                if rel.endswith(".html"):
                    for rx, to in SHELL_HTML: t = rx.sub(to, t)
                if rel == "manifest.webmanifest":
                    m = json.loads(t); m.pop("shortcuts", None); t = json.dumps(m, ensure_ascii=False, sort_keys=True)
                if rel == "data/discounts.json":   # the same content; phase 1 ordered the chains by set iteration
                    t = json.dumps(json.loads(t), ensure_ascii=False, sort_keys=True)
                b = t.encode("utf-8")
            for rx, to in HASHES: rel = rx.sub(to, rel)
            got[rel] = b
    return got


@pytest.mark.parametrize("name,data,disc", CASES, ids=[c[0] for c in CASES])
def test_core_build_is_byte_identical_to_phase1(phase1, tmp_path, name, data, disc):
    if not os.path.exists(data): pytest.skip(f"{os.path.relpath(data, ROOT)} not in this checkout")
    before = files(run_build(phase1, data, disc, str(tmp_path / "before")))
    after = files(run_build(ROOT, data, disc, str(tmp_path / "after"), "core"))
    assert sorted(before) == sorted(after)
    assert len(before) > 50
    bundle = "assets/cinema.HASH.js"
    diff = [p for p in before if p != bundle and before[p] != after[p]]
    assert not diff, diff[:10]
    assert sum(p.endswith(".html") for p in before) > 20 and any(p.startswith("data/") and p.endswith(".json") for p in before)


@pytest.mark.parametrize("name,data,disc", CASES[:1], ids=["sample"])
def test_full_build_only_adds_to_phase1(phase1, tmp_path, name, data, disc):
    before = files(run_build(phase1, data, disc, str(tmp_path / "before")))
    after = files(run_build(ROOT, data, disc, str(tmp_path / "after"), "all"))
    assert set(before) <= set(after), sorted(set(before) - set(after))[:10]


def test_discounts_json_does_not_depend_on_the_hash_seed(tmp_path):
    """data/discounts.json lists the chains sorted: two builds under different hash seeds write the same bytes."""
    name, data, disc = CASES[0]
    a = run_build(ROOT, data, disc, str(tmp_path / "a"), "core", seed="1")
    b = run_build(ROOT, data, disc, str(tmp_path / "b"), "core", seed="2")
    read = lambda o: open(os.path.join(o, "data", "discounts.json"), "rb").read()
    assert read(a) == read(b)
    chains = json.loads(read(a))["chains"]["ar"]
    assert list(chains) == sorted(chains)
