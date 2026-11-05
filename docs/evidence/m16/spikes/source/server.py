"""Static server for the renderer spikes with the Studio CSP as a response header."""
import functools
import http.server
import sys

CSP = ("default-src 'self' ipc: http://ipc.localhost; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob:; font-src 'self'; connect-src 'self' ipc: http://ipc.localhost; object-src 'none'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


import os
if os.environ.get('SPIKE_RELAX'): CSP = CSP.replace("script-src 'self'", "script-src 'self' 'unsafe-eval' 'wasm-unsafe-eval'")


class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


H.extensions_map[".js"] = "text/javascript"
H.extensions_map[".wasm"] = "application/wasm"
port = int(sys.argv[2])
http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(H, directory=sys.argv[1])).serve_forever()
