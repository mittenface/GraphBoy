import http.server
import socketserver
import json # Added for JSON parsing
from urllib.parse import urlparse, parse_qs # Added for URL parsing

# Attempt to import the backend module
# This path needs to be correct based on where server.py is run from
# and how Python's import system can find the components.
# If server.py is at the root, and components is a package:
try:
    from components.AIChatInterface.backend import AIChatInterfaceBackend
except ImportError:
    # Fallback for different execution contexts or if __init__.py is missing/not set up for proper packaging
    # This is a common issue in simpler project structures.
    # We might need to adjust sys.path if this fails.
    print("Warning: Could not import AIChatInterfaceBackend directly. Ensure PYTHONPATH is set up correctly or that components are structured as a package.")
    AIChatInterfaceBackend = None


PORT = 5000

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    # Instantiate the backend once, if available
    chat_backend = AIChatInterfaceBackend() if AIChatInterfaceBackend else None

    def do_GET(self):
        # Redirect root requests to index.html
        if self.path == '/':
            self.path = '/public/index.html'
        return super().do_GET()

    def do_POST(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path == '/api/chat':
            if not self.chat_backend:
                self.send_error(500, "Chat backend not initialized")
                return

            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)

            try:
                payload = json.loads(post_data.decode('utf-8'))
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON payload")
                return

            # Extract parameters from payload, matching the manifest
            user_input = payload.get('userInput')
            temperature = payload.get('temperature', 0.7) # Default if not provided
            max_tokens = payload.get('maxTokens', 256)    # Default if not provided

            if user_input is None:
                self.send_error(400, "Missing 'userInput' in payload")
                return

            try:
                # Call the backend processing method
                response_data = self.chat_backend.process_request(
                    user_input=user_input,
                    temperature=temperature,
                    max_tokens=max_tokens
                )

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode('utf-8'))
            except Exception as e:
                self.send_error(500, f"Error processing chat request: {e}")
        else:
            self.send_error(404, "Endpoint not found")


if __name__ == '__main__':
    # Ensure server.py can find the components directory if not run as a module
    # This is a common hack for direct script execution.
    # For robust applications, proper packaging or PYTHONPATH setup is preferred.
    import sys
    import os
    # Add project root to sys.path to allow imports like 'components.AIChatInterface.backend'
    # Assumes server.py is in the project root.
    project_root = os.path.abspath(os.path.dirname(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Re-attempt import if it failed initially, now that sys.path might be updated
    if AIChatInterfaceBackend is None:
        try:
            from components.AIChatInterface.backend import AIChatInterfaceBackend
            CustomHandler.chat_backend = AIChatInterfaceBackend() # Re-initialize in handler
            print("AIChatInterfaceBackend loaded successfully after sys.path modification.")
        except ImportError:
            print("Error: AIChatInterfaceBackend could still not be imported. Check project structure and PYTHONPATH.")
            # Decide if server should run without the backend or exit
            # For now, it will run but /api/chat will fail.

    with socketserver.TCPServer(("0.0.0.0", PORT), CustomHandler) as httpd:
        print(f"Server running at http://0.0.0.0:{PORT}")
        if CustomHandler.chat_backend:
            print("AI Chat Interface backend is available at /api/chat (POST)")
        else:
            print("AI Chat Interface backend FAILED to load. /api/chat will not work.")
        print("Open the webview to see your canvas application")
        httpd.serve_forever()
