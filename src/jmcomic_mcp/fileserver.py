#!/usr/bin/env python3
"""File server for jmcomic-mcp downloads — short safe names, dynamic listing."""
import os, json, mimetypes, re
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote

DOWNLOADS = os.path.expanduser("~/downloads")
import hashlib

PORT = 8889

def safe_name(fp, ext):
    """Short name from first 6 chars of MD5 hash."""
    h = hashlib.md5(os.path.basename(fp).encode()).hexdigest()[:6]
    return f"{h}{ext}"

def build_index():
    """Map safe names to real files, sorted by mtime (newest first)."""
    files = []
    for f in sorted(os.listdir(DOWNLOADS), key=lambda x: os.path.getmtime(os.path.join(DOWNLOADS, x)), reverse=True):
        fp = os.path.join(DOWNLOADS, f)
        ext = os.path.splitext(f)[1].lower()
        if os.path.isfile(fp) and ext in ('.pdf', '.zip', '.rar', '.cbz'):
            files.append((fp, f, ext, os.path.getsize(fp)))
    return files

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DOWNLOADS, **kwargs)

    def do_GET(self):
        path = unquote(self.path).split('?')[0]
        name = path.lstrip('/')

        # Short name lookup (hash-based: a1b2c3.pdf)
        m = re.match(r'^([a-f0-9]{6})(\.\w+)$', name)
        if m:
            h, ext = m.group(1), m.group(2)
            for fp, rn, fext, size in build_index():
                if fext == ext and hashlib.md5(os.path.basename(fp).encode()).hexdigest()[:6] == h:
                    sn = safe_name(fp, ext)
                    self.send_response(200)
                    self.send_header('Content-Type', mimetypes.guess_type(rn)[0] or 'application/octet-stream')
                    self.send_header('Content-Disposition', f'attachment; filename="{sn}"')
                    self.send_header('Content-Length', str(size))
                    self.end_headers()
                    with open(fp, 'rb') as f:
                        self.wfile.write(f.read())
                    return

        # Listing page
        if name == '' or name == '/':
            files = build_index()
            body = '<html><body><h2>Downloads</h2><ul>'
            for fp, rn, ext, sz in files:
                sn = safe_name(fp, ext)
                body += f'<li><a href="/{sn}">{sn}</a> — {rn[:60]} ({sz//1048576}MB)</li>'
            body += f'</ul><p>{len(files)} files</p></body></html>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(body.encode())
            return

        # Raw filename access (fallback)
        super().do_GET()

    def log_message(self, fmt, *args):
        pass  # silent

if __name__ == '__main__':
    print(f'Serving {DOWNLOADS} on :{PORT}')
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
