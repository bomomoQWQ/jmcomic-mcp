#!/usr/bin/env python3
"""File server for jmcomic-mcp downloads — short safe names, dynamic listing."""
import os, json, mimetypes, re
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote

DOWNLOADS = os.path.expanduser("~/downloads")
PORT = 8889

def safe_name(idx, ext):
    return f"f_{idx:03d}{ext}"

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

        # Short name lookup (f_001.pdf)
        m = re.match(r'^f_(\d{3})(\.\w+)$', name)
        if m:
            idx, ext = int(m.group(1)), m.group(2)
            files = build_index()
            if 1 <= idx <= len(files):
                real_path, real_name, _, size = files[idx - 1]
                self.send_response(200)
                self.send_header('Content-Type', mimetypes.guess_type(real_name)[0] or 'application/octet-stream')
                self.send_header('Content-Disposition', f'attachment; filename="{safe_name(idx, ext)}"')
                self.send_header('Content-Length', str(size))
                self.end_headers()
                with open(real_path, 'rb') as f:
                    self.wfile.write(f.read())
                return

        # Listing page
        if name == '' or name == '/':
            files = build_index()
            body = '<html><body><h2>Downloads</h2><ul>'
            for i, (_, rn, ext, sz) in enumerate(files, 1):
                sn = safe_name(i, ext)
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
