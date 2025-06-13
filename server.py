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
    print("HTTP server thread started.")

    # Return references for management (e.g., in tests or a more complex app structure)
    return httpd, http_server_thread, websocket_server_instance

async def stop_servers(httpd, http_server_thread, ws_server_instance):
    print("Stopping WebSocket server...")
    if ws_server_instance:
        ws_server_instance.close()
        await ws_server_instance.wait_closed()
        print("WebSocket server stopped.")

    print("Stopping HTTP server...")
    if httpd:
        # httpd.shutdown() needs to be called from a different thread than serve_forever()
        # Since http_server_thread is a daemon, it will exit when the main program exits
        # For explicit shutdown, one might need to signal the thread or use a different server type
        # For now, relying on daemon thread property for tests.
        # A more robust shutdown would involve httpd.shutdown() called from another thread.
        # Or, if the loop is stopped, the daemon thread will also stop.
        httpd.server_close() # Closes the server socket
    if http_server_thread and http_server_thread.is_alive():
        # http_server_thread.join(timeout=1.0) # Wait for thread to finish
        print("HTTP server thread is a daemon, should stop with main loop.")
    print("Servers stopping sequence initiated.")


async def main_server_loop(httpd_server_ref, ws_server_ref):
    """Keeps the servers running. httpd runs in its own thread."""
    # The httpd server runs in a daemon thread, so it doesn't need explicit await here
    # We await the WebSocket server task to keep the asyncio loop alive for it.
    if ws_server_ref:
        await ws_server_ref
    else:
        # If there's no WebSocket server, we might need another way to keep loop alive
        # or this function might complete immediately if httpd is only daemon.
        # For now, assume ws_server_ref is always there.
        print("WebSocket server not started, main loop might exit if HTTP is daemon only.")


async def setup_and_start_servers():
    # Ensure server.py can find the components directory
    import sys
    import os
    project_root = os.path.abspath(os.path.dirname(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Initialize the backend
    backend_instance = None
    global AIChatInterfaceBackend
    if AIChatInterfaceBackend is None:
        try:
            from components.AIChatInterface.backend import AIChatInterfaceBackend as BackendFromComponents
            AIChatInterfaceBackend = BackendFromComponents
            print("AIChatInterfaceBackend re-loaded successfully in setup_and_start_servers().")
        except ImportError:
            print("Warning: AIChatInterfaceBackend could not be imported in setup_and_start_servers().")

    if AIChatInterfaceBackend:
        backend_instance = AIChatInterfaceBackend()
        print("AIChatInterfaceBackend initialized.")
    else:
        print("CRITICAL ERROR: AIChatInterfaceBackend is None. Chat functionalities will not work.")

    CustomHandler.chat_backend = backend_instance

    # Configure HTTP server
    httpd = socketserver.TCPServer(("0.0.0.0", PORT), CustomHandler, bind_and_activate=False)
    # Set allow_reuse_address to True to prevent "Address already in use" errors during tests or rapid restarts
    httpd.allow_reuse_address = True
    httpd.server_bind()
    httpd.server_activate()

    http_server_thread = threading.Thread(target=httpd.serve_forever, name="HTTPThread")
    http_server_thread.daemon = True

    http_server_thread.daemon = True

    # Configure WebSocket server
    bound_websocket_handler = lambda ws, path: websocket_handler(ws, path, backend_instance)

    # The actual websockets.Server object is returned by websockets.serve()
    # This object can be used to close the server.
    ws_server_object = await websockets.serve(
        bound_websocket_handler, # Original handler
        "0.0.0.0",
        WS_PORT
    )

    print(f"HTTP Server configured for http://0.0.0.0:{PORT}")
    if backend_instance:
        print("AI Chat Interface backend is configured for HTTP.")
    else:
        print("Warning: AI Chat Interface backend FAILED to load for HTTP.")

    print(f"WebSocket Server configured for ws://0.0.0.0:{WS_PORT}")
    if backend_instance:
        print("AI Chat Interface backend is configured for WebSocket.")
    else:
        print("Warning: AI Chat Interface backend FAILED to load for WebSocket.")

    http_server_thread.start()
    print("HTTP server thread started.")
    print("Servers setup complete. WebSocket server is running via its task.")

    # ws_server_object is the websockets.Server instance that we need to await or manage
    # In the original main, it was `await websocket_server_task`
    # For testability, we return the server objects.
    return httpd, http_server_thread, ws_server_object


async def main():
    httpd, http_server_thread, ws_server_instance = await setup_and_start_servers()

    # In the main application, we want the servers to run indefinitely.
    # The HTTP server is in a daemon thread. The WebSocket server runs in the asyncio loop.
    # Awaiting the ws_server_instance's task (which is what websockets.serve effectively does)
    # or using something like asyncio.Event().wait() can keep the main coroutine alive.
    try:
        # If ws_server_instance is the result of websockets.serve, it's a Server instance.
        # It doesn't need to be awaited directly here to keep it running if it's managed by the loop.
        # Instead, we might want a way to signal shutdown. For simplicity, gather it.
        # await asyncio.gather(ws_server_instance.serve_forever()) # This is one way if serve_forever() exists
        # However, websockets.serve already starts the server task.
        # We just need to keep the main task from exiting.
        if ws_server_instance:
             # The server runs until ws_server_instance.close() is called.
             # To keep main alive, we can wait for a shutdown signal or just loop.
             # For now, this simple await on wait_closed will effectively mean it runs until closed elsewhere.
             # This might not be ideal for the actual main() if nothing calls close().
             # A better approach for main() is often an asyncio.Event:
             shutdown_event = asyncio.Event()
             print("Servers running. Waiting for shutdown signal...")
             await shutdown_event.wait() # This will wait indefinitely until event.set()
        else:
            print("WebSocket server failed to start. Exiting.")

    except KeyboardInterrupt:
        print("KeyboardInterrupt received, shutting down...")
    finally:
        print("Main loop ending, initiating server shutdown...")
        await stop_servers(httpd, http_server_thread, ws_server_instance)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Application shutdown.")
