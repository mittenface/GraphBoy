
import http.server
import socketserver
import os

# Serve files from the project root to access both public and frontend folders
# os.chdir('public') - removed to serve from root

PORT = 5000

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Redirect root requests to index.html
        if self.path == '/':
            self.path = '/public/index.html'
        return super().do_GET()

Handler = CustomHandler

with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
    print(f"Server running at http://0.0.0.0:{PORT}")
    print("Open the webview to see your canvas application")
    httpd.serve_forever()
