"""The one local server every check and perf tool measures (W1-P1, MASTER-PLAN §5.0 #6, measurement isolation).

Ten agents share one laptop, and a Windows server that binds with SO_REUSEADDR lets a second server take the same
port: mobile-motion §2.0's first runs were answered by another agent's build. So this server
  - refuses to start when anything already answers on the port at 127.0.0.1, [::1] or the alt address: a server that
    bound the wildcard (0.0.0.0 or [::]), which an exclusive bind on one address does not see (review M2);
  - binds each address it serves exclusively (SO_EXCLUSIVEADDRUSE on Windows, no address reuse anywhere), on both
    loopbacks, so a second server on 127.0.0.1, [::1] or the alt address fails to start, and `localhost` (IPv6 first
    in node and Chrome) reaches this server too. A server that binds a wildcard (0.0.0.0 or [::]) *after* this one
    still starts on Windows (measured), but there a specific binding wins over a wildcard, so it never receives a
    request addressed to these; X-Served-By stays the last check. Never a wildcard here: that listens beyond loopback;
  - stamps every response with `X-Served-By: <name>-<git short sha>`, which every tool asserts on the document and
    on one asset before it measures anything (a check pointed at the wrong port fails there);
  - serves `/posters/*` from a local folder when the file is there, else proxies the read-only GET to the live
    site once and keeps it in memory (Task 3's report: the real build's posters and trailer frames);
  - gzips text as CloudFront does, so Lighthouse sees the transfer sizes of production.

  python tools/serve.py --out out --port 8111 --name w1-p1 [--alt-out DIR] [--alt-host 127.0.0.2] [--posters DIR]
                       [--host 127.0.0.1] [--no-proxy]

`--alt-out`: a second build on the same port at a second loopback address, `127.0.0.2:<port>` (`--alt-host`), stamped
`<name>-<sha>-alt`: tools/perf_fx.cjs interleaves a control and a variant this way without a second port (two hosts
are two origins, so neither shares the other's cache or storage). A literal address, never the name `localhost`, which
another agent's wildcard server could answer.

Prints one line «serving <dir> on http://host:port as <X-Served-By>» once it listens. Ports are fixed per package
(§5.0: W1-P1 8111, W1-P2 8112, D1–D3 8113–8115, O1 8116, W2-P1…P10 8121–8130, QA 8131, W3+ from 8141)."""
import argparse, errno, gzip, http.server, mimetypes, os, socket, socketserver, subprocess, sys, threading, time, urllib.request

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
        # TCPServer's bind, not HTTPServer's: that one asks getfqdn(), a 5 s reverse lookup for 127.0.0.2 on Windows
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class ExclusiveServer6(ExclusiveServer):
    address_family = socket.AF_INET6


NOT_HERE = {errno.EADDRNOTAVAIL, errno.EAFNOSUPPORT, getattr(errno, "EPROTONOSUPPORT", -1)}   # no IPv6 loopback here


def answers(hosts, port, timeout=0.5):
    """The hosts at which something already accepts a connection on the port. Probed together: on Windows a closed
    loopback port only gives up at the timeout."""
    hit = set()

    def probe(h):
        try:
            with socket.socket(socket.AF_INET6 if ":" in h else socket.AF_INET, socket.SOCK_STREAM) as c:
                c.settimeout(timeout)
                c.connect((h, port))
                hit.add(h)
        except OSError:
            pass
    ts = [threading.Thread(target=probe, args=(h,)) for h in hosts]
    for t in ts: t.start()
    for t in ts: t.join()
    return [h for h in hosts if h in hit]


def url(host, port):
    return f"http://[{host}]:{port}" if ":" in host else f"http://{host}:{port}"


def handler(root, posters, proxy, cache, lock):
    """One per address: root is (dir, stamp); the poster cache is shared by the builds."""

    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def root(self):
            return root

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
    ap.add_argument("--alt-out", default=None, help="a second build on the same port at --alt-host (perf_fx.cjs)")
    ap.add_argument("--alt-host", default="127.0.0.2", help="the alt build's loopback address")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--name", required=True, help="the package, e.g. w1-p1 (the header adds the git short sha)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--posters", default=None, help="local posters folder (default: <repo>/data/posters when it exists)")
    ap.add_argument("--no-proxy", action="store_true", help="never fetch a missing poster from the live site")
    ap.add_argument("--sha", default=None, help="override the git short sha in the header")
    a = ap.parse_args()
    stamp = f"{a.name}-{a.sha or short_sha(ROOT)}"
    main_root = (os.path.abspath(a.out), stamp)
    posters = a.posters or (os.path.join(ROOT, "data", "posters") if os.path.isdir(os.path.join(ROOT, "data", "posters")) else None)
    # (address, root, required): the main build on --host and, beside 127.0.0.1, on [::1], where `localhost` goes first
    plan = [(a.host, main_root, True)] + ([("::1", main_root, False)] if a.host == "127.0.0.1" else [])
    if a.alt_out: plan.append((a.alt_host, (os.path.abspath(a.alt_out), stamp + "-alt"), True))
    taken = answers(sorted({"127.0.0.1", "::1"} | {h for h, _, _ in plan}), a.port)
    if taken:
        print(f"port {a.port} is taken: something already answers on {', '.join(url(h, a.port) for h in taken)} (another server "
              "owns it, perhaps on the wildcard), so nothing here would be measured", file=sys.stderr)
        sys.exit(3)
    cache, lock, bound = {}, threading.Lock(), []
    for host, root, required in plan:
        try:
            srv = (ExclusiveServer6 if ":" in host else ExclusiveServer)((host, a.port), handler(root, posters, not a.no_proxy, cache, lock))
        except OSError as e:
            if not required and e.errno in NOT_HERE:
                continue                        # no IPv6 loopback (a container, the Fold's chroot): 127.0.0.1 alone
            for b in bound: b[0].server_close()
            print(f"port {a.port} is taken on {url(host, a.port)} ({e}); another server owns it, so nothing here would be measured",
                  file=sys.stderr)
            sys.exit(3)
        bound.append((srv, host, root))
    for srv, _, _ in bound:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    mains = " and ".join(url(h, a.port) for _, h, r in bound if r is main_root)
    alt = [(h, r) for _, h, r in bound if r is not main_root]
    print(f"serving {main_root[0]} on {mains} as {stamp}" + (f" (and {alt[0][1][0]} on {url(alt[0][0], a.port)} as {alt[0][1][1]})" if alt else ""),
          flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
