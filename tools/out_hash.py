"""Byte identity of a build (W1-P1, MASTER-PLAN §5.2 «pure moves, build output byte-identical»): build the site into a
folder and hash every file under it, then compare two such manifests. A refactor that only moves code must leave
every file the same; `compare` names every file that differs, appeared or went.

  python tools/out_hash.py build --out DIR --manifest M.json [--data data/latest.json] [--discounts discounts.yaml]
  python tools/out_hash.py compare A.json B.json [--same-v]

The build runs with PYTHONHASHSEED=0 (data/discounts.json lists chains from a set), no lastmod file (every
sitemap date is the data's day) and noindex off, so two builds of the same inputs are comparable.

`--same-v`: Kit.v, the cache-busting token on /assets/cinema.css?v= and icon.svg?v= and in sw.js, hashes every file
under src/ — moving CSS rules from one file to another changes it by design, though no served byte of the
stylesheet moves. With the flag, that one token is set aside (each manifest also keeps a hash of every file with
the token replaced) and reported on its own line; every other byte must still match."""
import argparse, hashlib, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def manifest(out):
    """{path: [sha256, sha256 with the build's version token set aside, size]}. The token is read from sw.js
    (`var V = "…"`, Kit.v) and replaced wherever it appears: ?v= on every page, the worker's name and its comment."""
    files, v = {}, None
    sw = os.path.join(out, "sw.js")
    if os.path.exists(sw):
        m = re.search(rb'var V = "([0-9a-f]{10})"', open(sw, "rb").read())
        v = m and m.group(1)
    for dp, _, fs in os.walk(out):
        for f in fs:
            p = os.path.join(dp, f)
            b = open(p, "rb").read()
            n = b.replace(v, b"<V>") if v else b
            files[os.path.relpath(p, out).replace(os.sep, "/")] = [hashlib.sha256(b).hexdigest(), hashlib.sha256(n).hexdigest(), len(b)]
    return files


def do_build(a):
    if os.environ.get("PYTHONHASHSEED") != "0":
        env = dict(os.environ, PYTHONHASHSEED="0")
        sys.exit(subprocess.call([sys.executable] + sys.argv, env=env))
    sys.path.insert(0, ROOT)
    import build
    n = build.build(a.data, a.discounts, a.out, noindex=False, lastmod_path=None)
    m = manifest(a.out)
    json.dump({"pages": n, "files": m}, open(a.manifest, "w", encoding="utf-8"), indent=0, sort_keys=True)
    print(f"built {n} pages, {len(m)} files -> {a.manifest}")


def do_compare(a):
    x, y = (json.load(open(p, encoding="utf-8"))["files"] for p in (a.a, a.b))
    k = 1 if a.same_v else 0
    gone, new = sorted(set(x) - set(y)), sorted(set(y) - set(x))
    diff = sorted(f for f in set(x) & set(y) if x[f][k] != y[f][k])
    vonly = sorted(f for f in set(x) & set(y) if x[f][0] != y[f][0] and x[f][1] == y[f][1])
    print(f"{len(x)} files before, {len(y)} after; {len(set(x) & set(y)) - len(diff)} identical"
          + (f" ({len(vonly)} of them differ only by the src/ version token)" if a.same_v else ""))
    for label, fs in (("GONE", gone), ("NEW", new), ("DIFF", diff)):
        for f in fs: print(label, f)
    sys.exit(1 if gone or new or diff else 0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build")
    b.add_argument("--out", required=True); b.add_argument("--manifest", required=True)
    b.add_argument("--data", default=os.path.join(ROOT, "data", "latest.json"))
    b.add_argument("--discounts", default=os.path.join(ROOT, "discounts.yaml"))
    c = sp.add_parser("compare")
    c.add_argument("a"); c.add_argument("b"); c.add_argument("--same-v", action="store_true")
    a = ap.parse_args()
    do_build(a) if a.cmd == "build" else do_compare(a)
