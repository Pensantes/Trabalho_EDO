#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PEN · Simulador de Lançamento — servidor com HTML externo
=========================================================
O QUE MUDOU em relação à versão com HTML embutido:
  1. A string gigante com o HTML foi REMOVIDA daqui.
  2. A rota "/" agora lê ./index.html do disco a cada request.
  3. Qualquer arquivo da pasta é servido estaticamente
     (foguete.png, style.css, app.js, etc.) — o HTML não precisa
     de nenhuma alteração, caminhos relativos funcionam normal.

Estrutura esperada:
  main.py
  index.html      <- todo o HTML/CSS/JS da simulação
  foguete.png     <- sprite com os 3 estágios (opcional; a rota /sprite
                     detecta a imagem automaticamente pelo nome/tamanho)

Uso:
  python main.py                  # http://localhost:8000
  python main.py --port 8080
  python main.py --dir outra/pasta
  python main.py --no-browser     # não abre o navegador sozinho
  python main.py --no-reload      # desativa o auto-reload ao salvar

Sem dependências: apenas biblioteca padrão do Python.
"""

import argparse
import html
import json
import mimetypes
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

# ---------------------------------------------------------------- assets --
MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".txt": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".wasm": "application/wasm",
}
IMG_EXTS = {".png", ".webp", ".jpg", ".jpeg", ".gif"}
BLOCKED = {".py", ".pyc", ".ipynb"}  # não expõe código/notebooks
WATCH_EXTS = set(MIME.keys())

FAVICON = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
    "<text y='0.9em' font-size='90'>🚀</text></svg>"
).encode("utf-8")

# Injetado no final do index.html (desative com --no-reload).
# Consulta /__mtime a cada 1 s e dá F5 sozinho quando algum arquivo muda.
RELOAD_SNIPPET = """
<script>
(() => {
  let last = null;
  setInterval(async () => {
    try {
      const r = await fetch("/__mtime", { cache: "no-store" });
      const j = await r.json();
      if (last !== null && j.mtime !== last) location.reload();
      last = j.mtime;
    } catch (e) { /* servidor reiniciando: tenta de novo no próximo tick */ }
  }, 1000);
})();
</script>
"""


def find_sprite(base: Path):
    """Acha a imagem do foguete na pasta (prioriza nomes like foguete/rocket/sprite)."""
    try:
        cands = [
            p for p in base.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXTS
        ]
    except OSError:
        return None
    if not cands:
        return None

    def score(p: Path):
        n = p.name.lower()
        s = sum(
            10
            for kw in ("foguete", "rocket", "sprite", "nave", "pen", "estagio")
            if kw in n
        )
        try:
            s += min(p.stat().st_size / 1_000_000, 5)  # imagens maiores ganham
        except OSError:
            pass
        return s

    return max(cands, key=score)


def tree_mtime(base: Path) -> float:
    """mtime mais recente entre os arquivos servidos (para o live-reload)."""
    latest = 0.0
    skip = {".git", "__pycache__", "node_modules", ".venv", "venv"}
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
        for name in files:
            if os.path.splitext(name)[1].lower() in WATCH_EXTS:
                try:
                    latest = max(latest, os.path.getmtime(os.path.join(root, name)))
                except OSError:
                    pass
    return latest


def page_missing_index(base: Path) -> bytes:
    """Página de erro real: o servidor está no ar, só falta o index.html."""
    safe = html.escape(str(base))
    doc = f"""<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="3">
<title>PEN · index.html não encontrado</title>
<style>
 body{{margin:0;min-height:100vh;display:grid;place-items:center;
      background:#04060d;color:#e9eef8;font:16px/1.6 system-ui,'Segoe UI',sans-serif}}
 .card{{max-width:660px;margin:24px;padding:40px;border:1px solid #22304a;border-radius:16px;
       background:linear-gradient(160deg,#0e1729,#0a1120)}}
 h1{{margin:0 0 8px;font-size:22px}} h1 span{{color:#a06bff}}
 code{{font-family:Consolas,monospace;color:#22d3ee}}
 pre{{background:#04060d;border:1px solid #22304a;border-radius:10px;
      padding:14px 18px;color:#9aa7bd;overflow:auto}}
 .ok{{color:#3ddc84}}
</style></head><body>
<div class="card">
 <h1>🚀 <span>PEN</span> — servidor no ar, mas falta o HTML</h1>
 <p>Coloque o arquivo <code>index.html</code> na pasta abaixo.
    Esta página se atualiza sozinha a cada 3 s:</p>
 <pre>{safe}</pre>
 <p>Estrutura esperada:</p>
 <pre>main.py
index.html      ← todo o HTML/CSS/JS da simulação
foguete.png     ← sprite com os 3 estágios (opcional)
style.css / app.js / …   (opcionais, servidos normalmente)</pre>
 <p class="ok">Aguardando o index.html…</p>
</div></body></html>"""
    return doc.encode("utf-8")


# --------------------------------------------------------------- handler --
class Handler(BaseHTTPRequestHandler):
    server_version = "PEN-Sim/2.0"
    protocol_version = "HTTP/1.1"  # keep-alive (sempre enviamos Length)
    base: Path = Path(".").resolve()
    reload_enabled = True

    # -- helpers ----------------------------------------------------------
    def _send(self, data: bytes, ctype: str, status: int = 200):
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # navegador cancelou o request: normal

    def _json(self, obj, status=200):
        self._send(
            json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8", status
        )

    def _file(self, path: Path):
        ctype = (
            MIME.get(path.suffix.lower())
            or mimetypes.guess_type(path.name)[0]
            or "application/octet-stream"
        )
        try:
            data = path.read_bytes()
        except OSError:
            return self._send(b"erro ao ler arquivo", "text/plain; charset=utf-8", 500)
        self._send(data, ctype)

    def _safe(self, rel: str):
        """Resolve o caminho e bloqueia path traversal (../../etc)."""
        rel = unquote(rel).lstrip("/")
        if not rel:
            return None
        target = (self.base / rel).resolve()
        try:
            target.relative_to(self.base.resolve())
        except ValueError:
            return None
        return target

    def _index(self):
        f = self.base / "index.html"
        if not f.is_file():
            return self._send(
                page_missing_index(self.base), "text/html; charset=utf-8", 404
            )
        try:
            data = f.read_bytes()
        except OSError:
            return self._send(
                b"erro ao ler index.html", "text/plain; charset=utf-8", 500
            )
        if self.reload_enabled:
            text = data.decode("utf-8", errors="replace")
            i = text.lower().rfind("</body>")
            text = (
                (text[:i] + RELOAD_SNIPPET + text[i:])
                if i != -1
                else (text + RELOAD_SNIPPET)
            )
            data = text.encode("utf-8")
        self._send(data, "text/html; charset=utf-8")

    # -- rotas ------------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            return self._index()
        if path == "/__mtime":  # live-reload
            return self._json({"mtime": tree_mtime(self.base)})
        if path == "/__info":  # p/ o HUD mostrar o sprite
            sp = find_sprite(self.base)
            return self._json(
                {"sprite": sp.name if sp else None, "reload": self.reload_enabled}
            )
        if path in ("/sprite", "/sprite.png"):  # nome fixo p/ o JS
            sp = find_sprite(self.base)
            if sp is None:
                return self._json({"error": "nenhuma imagem na pasta"}, 404)
            return self._file(sp)
        if path == "/favicon.ico":
            return self._send(FAVICON, "image/svg+xml")

        target = self._safe(path)  # arquivos estáticos
        if target is None:
            return self._send(b"404", "text/plain; charset=utf-8", 404)
        rel_parts = target.relative_to(self.base.resolve()).parts
        if target.suffix.lower() in BLOCKED or any(
            p.startswith(".") for p in rel_parts
        ):
            return self._send(b"403", "text/plain; charset=utf-8", 403)
        if target.is_dir():
            idx = target / "index.html"
            if idx.is_file():
                return self._file(idx)
            return self._send(b"404", "text/plain; charset=utf-8", 404)
        if not target.is_file():
            return self._send(b"404", "text/plain; charset=utf-8", 404)
        return self._file(target)

    def do_HEAD(self):
        self.do_GET()

    def log_message(self, fmt, *args):
        if urlparse(self.path).path in ("/__mtime", "/__info"):
            return  # não spammar o console com o polling do reload
        sys.stdout.write("  \033[90m%s\033[0m\n" % (fmt % args))


# ------------------------------------------------------------------ main --
def make_server(host: str, port: int):
    last = None
    for p in range(port, port + 11):  # porta ocupada? tenta as próximas
        try:
            srv = ThreadingHTTPServer((host, p), Handler)
            srv.daemon_threads = True
            return srv, p
        except OSError as e:
            last = e
    raise last


def main():
    ap = argparse.ArgumentParser(
        description="Servidor da simulação PEN (HTML externo)."
    )
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument(
        "--host",
        default="127.0.0.1",
        help="use 0.0.0.0 para acessar de outros dispositivos da rede",
    )
    ap.add_argument(
        "--dir", default=None, help="pasta com o index.html (padrão: pasta do main.py)"
    )
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-reload", action="store_true")
    args = ap.parse_args()

    base = Path(args.dir).resolve() if args.dir else Path(__file__).resolve().parent
    if not base.is_dir():
        print(f"[erro] pasta não existe: {base}")
        sys.exit(1)

    Handler.base = base
    Handler.reload_enabled = not args.no_reload
    if os.name == "nt":
        os.system("")  # habilita cores ANSI no terminal do Windows

    try:
        httpd, port = make_server(args.host, args.port)
    except OSError as e:
        print(f"[erro] não consegui abrir a porta {args.port}: {e}")
        sys.exit(1)

    open_host = "localhost" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{open_host}:{port}/"
    sp = find_sprite(base)
    has_index = (base / "index.html").is_file()

    G, Y, P, C, D, R = (
        "\033[92m",
        "\033[93m",
        "\033[95m",
        "\033[96m",
        "\033[90m",
        "\033[0m",
    )
    idx_txt = (
        (G + "encontrado" + R)
        if has_index
        else (Y + "NÃO encontrado — crie o arquivo" + R)
    )
    sp_txt = sp.name if sp else (Y + "nenhuma imagem (opcional: foguete.png)" + R)
    rl_txt = (
        "ativo — salvar o HTML recarrega a página"
        if Handler.reload_enabled
        else "desativado"
    )
    port_txt = (
        f" {D}(porta {args.port} ocupada, usando {port}){R}"
        if port != args.port
        else ""
    )

    print(f"""
{P}  ┌──────────────────────────────────────────────
  │  🚀  PEN · SIMULADOR DE LANÇAMENTO — SERVIDOR
  └──────────────────────────────────────────────{R}
  {D}pasta :{R} {base}
  {D}html  :{R} index.html {idx_txt}
  {D}sprite:{R} {sp_txt}
  {D}reload:{R} {rl_txt}{port_txt}

  {G}➜  {url}{R}
  {D}Ctrl+C para encerrar{R}
""")

    if not args.no_browser:
        t = threading.Timer(0.6, lambda: webbrowser.open(url))
        t.daemon = True
        t.start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{D}  encerrando… até a próxima missão 🚀{R}")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
