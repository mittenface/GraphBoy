import http.server
import socketserver
import json # Added for JSON parsing
from urllib.parse import urlparse, parse_qs # Added for URL parsing
import asyncio
import websockets
import threading

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
WS_PORT = 5001 # New port for WebSocket server

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    # chat_backend will be set from the backend_instance in main()
    chat_backend = None

    def do_GET(self):
        # Redirect root requests to index.html
        if self.path == '/':
            self.path = '/public/index.html'
        return super().do_GET()

    def do_POST(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path == '/api/chat':
            if not CustomHandler.chat_backend: # Access via class attribute
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
                response_data = CustomHandler.chat_backend.process_request(
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


async def websocket_handler(websocket, path, chat_backend):
    print(f"Client connected: {websocket.remote_address}")
    try:
        async for message_str in websocket:
            request_id = None # Initialize request_id to be accessible in error responses
            try:
                print(f"Received message from {websocket.remote_address}: {message_str}")
                request = json.loads(message_str)
                request_id = request.get("id")

                # Basic JSON-RPC validation
                if not all(k in request for k in ("jsonrpc", "method")) or request.get("jsonrpc") != "2.0":
                    raise ValueError("Invalid JSON-RPC request structure.")
                if not isinstance(request.get("method"), str):
                     raise ValueError("Invalid JSON-RPC method (must be string).")
                if "id" not in request : # id can be null, but must be present
                    raise ValueError("Invalid JSON-RPC request (missing id).")


                method = request["method"]
                params = request.get("params", {}) # Default to empty dict if no params

                if method == "chat":
                    if not chat_backend:
                        raise RuntimeError("Chat backend not available.")

                    # Validate params for "chat" method
                    if not isinstance(params, dict):
                        raise ValueError("Invalid params for 'chat' method (must be an object).")

                    user_input = params.get("userInput")
                    if user_input is None:
                        raise ValueError("Missing 'userInput' in params for 'chat' method.")

                    # Optional params with defaults
                    temperature = params.get("temperature", 0.7)
                    max_tokens = params.get("maxTokens", 256)

                    # Call backend
                    backend_response = chat_backend.process_request(
                        user_input=user_input,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    response_data = {
                        "jsonrpc": "2.0",
                        "result": backend_response,
                        "id": request_id
                    }
                else:
                    # Method not found
                    raise ValueError(f"Method '{method}' not found.")

            except json.JSONDecodeError:
                response_data = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": "Parse error"},
                    "id": None # request_id might not be available if parsing failed early
                }
            except ValueError as ve: # Handles our custom validation errors and method not found
                error_code = -32602 # Invalid params by default
                if "Invalid JSON-RPC" in str(ve) or "missing id" in str(ve):
                    error_code = -32600 # Invalid Request
                elif "Method not found" in str(ve):
                    error_code = -32601 # Method not found
                response_data = {
                    "jsonrpc": "2.0",
                    "error": {"code": error_code, "message": str(ve)},
                    "id": request_id
                }
            except RuntimeError as re: # Specific for backend not available
                 response_data = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32000, "message": str(re)}, # Custom server error for backend issues
                    "id": request_id
                }
            except Exception as e:
                # Catch-all for other unexpected errors
                print(f"Internal error processing WebSocket message: {e}")
                response_data = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": f"Internal error: {type(e).__name__} - {e}"},
                    "id": request_id
                }

            await websocket.send(json.dumps(response_data))
            print(f"Sent response to {websocket.remote_address}: {json.dumps(response_data)}")

    except websockets.exceptions.ConnectionClosedOK:
        print(f"Client disconnected gracefully: {websocket.remote_address}")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"Client connection closed with error: {websocket.remote_address}, Error: {e}")
    except Exception as e:
        # This catches errors in the connection handling itself, not message processing
        print(f"Overall error in WebSocket connection for {websocket.remote_address}: {e}")
    finally:
        print(f"Connection closed for {websocket.remote_address}")

async def main():
    # Ensure server.py can find the components directory
    import sys
    import os
    project_root = os.path.abspath(os.path.dirname(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Initialize the backend
    backend_instance = None
    # This re-tries importing AIChatInterfaceBackend, assuming it might not have been found initially
    global AIChatInterfaceBackend
    if AIChatInterfaceBackend is None: # Check if it was successfully imported at the top
        try:
            from components.AIChatInterface.backend import AIChatInterfaceBackend as BackendFromComponents
            AIChatInterfaceBackend = BackendFromComponents # Make it available globally if re-imported
            print("AIChatInterfaceBackend re-loaded successfully in main().")
        except ImportError:
            print("Warning: AIChatInterfaceBackend could not be imported even after sys.path modification in main().")
            # AIChatInterfaceBackend remains None

    if AIChatInterfaceBackend:
        backend_instance = AIChatInterfaceBackend()
        print("AIChatInterfaceBackend initialized.")
    else:
        print("CRITICAL ERROR: AIChatInterfaceBackend is None. Chat functionalities will not work.")
        # Decide if server should run without the backend or exit.
        # For now, it will proceed but features will be broken.

    CustomHandler.chat_backend = backend_instance # Set backend for HTTP handler

    # Configure and start HTTP server in a separate thread
    httpd = socketserver.TCPServer(("0.0.0.0", PORT), CustomHandler)
    http_server_thread = threading.Thread(target=httpd.serve_forever, name="HTTPThread")
    http_server_thread.daemon = True # Ensure thread exits when main program exits

    # Configure WebSocket server
    # Use a lambda to pass the backend_instance to the websocket_handler
    bound_websocket_handler = lambda ws, path: websocket_handler(ws, path, backend_instance)

    websocket_server_task = websockets.serve(
        bound_websocket_handler,
        "0.0.0.0",
        WS_PORT
    )

    print(f"HTTP Server starting at http://0.0.0.0:{PORT}")
    if backend_instance:
        print("AI Chat Interface backend is configured for HTTP at /api/chat (POST)")
    else:
        print("Warning: AI Chat Interface backend FAILED to load for HTTP. /api/chat will not work.")

    print(f"WebSocket Server starting at ws://0.0.0.0:{WS_PORT}")
    if backend_instance:
        print("AI Chat Interface backend is configured for WebSocket connections.")
    else:
        print("Warning: AI Chat Interface backend FAILED to load for WebSocket. Connections may not work as expected.")

    print("Application startup complete. Servers are starting...")

    http_server_thread.start()

    # Keep the main thread alive to run the asyncio event loop for the WebSocket server
    await websocket_server_task # This starts the WebSocket server and keeps main running

if __name__ == '__main__':
    asyncio.run(main())
