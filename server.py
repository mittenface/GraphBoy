
import http.server
import socketserver
import os

# Change to the directory containing the HTML file
os.chdir('public')

PORT = 5000

Handler = http.server.SimpleHTTPRequestHandler

with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
    print(f"Server running at http://0.0.0.0:{PORT}")
    print("Open the webview to see your canvas application")
    httpd.serve_forever()
