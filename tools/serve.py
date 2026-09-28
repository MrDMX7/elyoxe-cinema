"""The one local server every check and perf tool measures (W1-P1, MASTER-PLAN §5.0 #6, measurement isolation).

Ten agents share one laptop, and a Windows server that binds with SO_REUSEADDR lets a second server take the same
port: mobile-motion §2.0's first runs were answered by another agent's build. So this server
  - binds its port exclusively (SO_EXCLUSIVEADDRUSE on Windows, no address reuse anywhere): a second server on the
    port fails to start instead of sharing it;
  - stamps every response with `X-Served-By: <name>-<git short sha>`, which every tool asserts on the document and
    on one asset before it measures anything (a check pointed at the wrong port fails there);
  - serves `/posters/*` from a local folder when the file is there, else proxies the read-only GET to the live
    site once and keeps it in memory (Task 3's report: the real build's posters and trailer frames);
  - gzips text as CloudFront does, so Lighthouse sees the transfer sizes of production.

  python tools/serve.py --out out --port 8111 --name w1-p1 [--alt-out DIR] [--posters DIR] [--host 127.0.0.1] [--no-proxy]

`--alt-out`: a second build on the same port, answered to requests whose Host is `localhost:<port>` (the first build
answers `127.0.0.1:<port>`), stamped `<name>-<sha>-alt`: tools/perf_fx.cjs interleaves a control and a variant this way
without a second port (the two hosts are two origins, so neither shares the other's cache or storage).

Prints one line «serving <dir> on http://host:port as <X-Served-By>» once it listens. Ports are fixed per package
(§5.0: W1-P1 8111, W1-P2 8112, D1–D3 8113–8115, O1 8116, W2-P1…P10 8121–8130, QA 8131, W3+ from 8141)."""
import argparse, gzip, http.server, mimetypes, os, socket, subprocess, sys, threading, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE = "https://cinema.elyoxe.com"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp",
         ".jpg": "image/jpeg", ".woff2": "font/woff2", ".webmanifest": "application/manifest+json", ".xml": "application/xml",
         ".txt": "text/plain; charset=utf-8", ".ics": "text/calendar; charset=utf-8"}
GZIP = ("text/", "application/json", "application/javascript", "image/svg+xml", "application/manifest+json", "application/xml")


def short_sha(cwd):
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=10).stdout.strip() or "nogit"
    except Exception:
        return "nogit"


class ExclusiveServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = False       # http.server.HTTPServer sets 1: on Windows that lets a second server share the port
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):   # Windows only
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def handler(roots, posters, proxy):
    """roots: {"main": (dir, stamp), "alt": (dir, stamp)?}; the alt build answers Host: localhost:<port>."""
    cache, lock = {}, threading.Lock()

    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def root(self):
            alt = roots.get("alt") and (self.headers.get("Host") or "").split(":")[0] == "localhost"
            return roots["alt"] if alt else roots["main"]

        def send(self, code, body, ctype, cache_control="no-cache"):
            if ctype.startswith(GZIP) and "gzip" in (self.headers.get("Accept-Encoding") or "") and len(body) > 256:
                body, enc = gzip.compress(body, 6), True
            else:
                enc = False
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            if enc: self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache_control)
            self.send_header("X-Served-By", self.root()[1])
            self.send_header("Vary", "Accept-Encoding")
            self.end_headers()
            if self.command != "HEAD": self.wfile.write(body)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            out = self.root()[0]
            p = urllib.request.unquote(self.path.split("?", 1)[0].split("#", 1)[0])
            if p.startswith("/posters/"):
                return self.poster(p)
            f = os.path.normpath(os.path.join(out, p.lstrip("/")))
            if not (f == out or f.startswith(out + os.sep)):
                return self.send(403, b"forbidden", "text/plain; charset=utf-8")
            if os.path.isdir(f): f = os.path.join(f, "index.html")
            if not os.path.isfile(f):
                nf = os.path.join(out, "404.html")
                if os.path.isfile(nf) and not p.startswith(("/data/", "/assets/")):
                    return self.send(404, open(nf, "rb").read(), TYPES[".html"])
                return self.send(404, b"not found", "text/plain; charset=utf-8")
            ext = os.path.splitext(f)[1].lower()
            cc = "public, max-age=31536000, immutable" if p.startswith("/assets/") and ext in (".js", ".woff2", ".png") else "no-cache"
            self.send(200, open(f, "rb").read(), TYPES.get(ext) or mimetypes.guess_type(f)[0] or "application/octet-stream", cc)

        def poster(self, p):
            name = os.path.basename(p)
            local = os.path.join(posters, name) if posters else None
            ctype = TYPES.get(os.path.splitext(name)[1].lower(), "image/webp")
            if local and os.path.isfile(local):
                return self.send(200, open(local, "rb").read(), ctype, "public, max-age=31536000, immutable")
            if not proxy:
                return self.send(404, b"not found", "text/plain; charset=utf-8")
            with lock:
                hit = cache.get(p)
            if hit is None:
                try:
                    req = urllib.request.Request(LIVE + p, headers={"User-Agent": "cinema-local-check"})
                    with urllib.request.urlopen(req, timeout=20) as r:
                        hit = (r.read(), r.headers.get("Content-Type") or ctype)
                except Exception:
                    hit = False
                with lock:
                    cache[p] = hit
            if not hit:
                return self.send(404, b"not found", "text/plain; charset=utf-8")
            self.send(200, hit[0], hit[1], "public, max-age=31536000, immutable")

    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    ap.add_argument("--alt-out", default=None, help="a second build, answered to Host: localhost:<port> (perf_fx.cjs)")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--name", required=True, help="the package, e.g. w1-p1 (the header adds the git short sha)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--posters", default=None, help="local posters folder (default: <repo>/data/posters when it exists)")
    ap.add_argument("--no-proxy", action="store_true", help="never fetch a missing poster from the live site")
    ap.add_argument("--sha", default=None, help="override the git short sha in the header")
    a = ap.parse_args()
    stamp = f"{a.name}-{a.sha or short_sha(ROOT)}"
    roots = {"main": (os.path.abspath(a.out), stamp)}
    if a.alt_out: roots["alt"] = (os.path.abspath(a.alt_out), stamp + "-alt")
    posters = a.posters or (os.path.join(ROOT, "data", "posters") if os.path.isdir(os.path.join(ROOT, "data", "posters")) else None)
    try:
        srv = ExclusiveServer((a.host, a.port), handler(roots, posters, not a.no_proxy))
    except OSError as e:
        print(f"port {a.port} is taken ({e}); another server owns it, so nothing here would be measured", file=sys.stderr)
        sys.exit(3)
    print(f"serving {roots['main'][0]} on http://{a.host}:{a.port} as {stamp}" + (f" (and {roots['alt'][0]} on localhost as {stamp}-alt)" if a.alt_out else ""), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
