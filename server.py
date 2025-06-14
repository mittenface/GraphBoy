import http.server
import socketserver
import json
from urllib.parse import urlparse, parse_qs
import asyncio
import websockets
import threading
import functools # Added for functools.partial
from pathlib import Path

from backend.component_registry import ComponentRegistry

try:
    from components.AIChatInterface.backend import AIChatInterfaceBackend
except ImportError:
    print("Warning: Could not import AIChatInterfaceBackend directly. Ensure PYTHONPATH is set up correctly or that components are structured as a package.")
    AIChatInterfaceBackend = None

PORT = 5000
WS_PORT = 5001

# New: WebSocket process_request_hook
async def process_request_hook(websocket, path_from_hook):
    """
    Hook to capture the request path and attach it to the websocket connection object.
    """
    # print(f"Process_request_hook: Path '{path_from_hook}' for {websocket.remote_address}")
    websocket.actual_request_path = path_from_hook
    return None # No additional headers

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    chat_backend = None

    def do_GET(self):
        if self.path == '/':
            self.path = '/public/index.html'
        return super().do_GET()

    def do_POST(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path == '/api/chat':
            if not CustomHandler.chat_backend:
                self.send_error(500, "Chat backend not initialized")
                return
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode('utf-8'))
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON payload")
                return
            user_input = payload.get('userInput')
            temperature = payload.get('temperature', 0.7)
            max_tokens = payload.get('maxTokens', 256)
            if user_input is None:
                self.send_error(400, "Missing 'userInput' in payload")
                return
            try:
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

# Modified: websocket_handler signature and path access
async def websocket_handler(websocket, chat_backend, registry: ComponentRegistry):
    request_path = getattr(websocket, 'actual_request_path', '/') # Get path from hook
    print(f"Client connected from {websocket.remote_address} on path '{request_path}'")
    try:
        async for message_str in websocket:
            request_id = None
            try:
                # print(f"Received message from {websocket.remote_address} on path '{request_path}': {message_str}")
                request = json.loads(message_str)
                request_id = request.get("id")

                if not all(k in request for k in ("jsonrpc", "method")) or request.get("jsonrpc") != "2.0":
                    raise ValueError("Invalid JSON-RPC request structure.")
                if not isinstance(request.get("method" ), str):
                     raise ValueError("Invalid JSON-RPC method (must be string).")
                if "id" not in request:
                    raise ValueError("Invalid JSON-RPC request (missing id).")

                method = request["method"]
                params = request.get("params", {})

                if method == "chat":
                    if not chat_backend:
                        raise RuntimeError("Chat backend not available.")
                    if not isinstance(params, dict):
                        raise ValueError("Invalid params for 'chat' method (must be an object).")
                    user_input = params.get("userInput")
                    if user_input is None:
                        raise ValueError("Missing 'userInput' in params for 'chat' method.")
                    temperature = params.get("temperature", 0.7)
                    max_tokens = params.get("maxTokens", 256)
                    backend_response = chat_backend.process_request(
                        user_input=user_input,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    response_data = {"jsonrpc": "2.0", "result": backend_response, "id": request_id}
                elif method == "component.updateInput":
                    if not isinstance(params, dict):
                        raise ValueError("Invalid params for 'component.updateInput' (must be an object).")
                    component_name = params.get("componentName")
                    inputs_data = params.get("inputs")
                    if not isinstance(component_name, str):
                        raise ValueError("Missing or invalid 'componentName' in params for 'component.updateInput' (must be a string).")
                    if not isinstance(inputs_data, dict):
                        raise ValueError("Missing or invalid 'inputs' in params for 'component.updateInput' (must be an object).")

                    component_instance = registry.get_component_instance(component_name)
                    if component_instance is None:
                        response_data = {
                            "jsonrpc": "2.0",
                            "error": {"code": -32001, "message": f"Component '{component_name}' not found."},
                            "id": request_id
                        }
                    else:
                        try:
                            response_content = component_instance.update(inputs_data)
                            response_data = {"jsonrpc": "2.0", "result": response_content, "id": request_id}
                        except Exception as e:
                            print(f"Error during component '{component_name}' update: {e}")
                            response_data = {
                                "jsonrpc": "2.0",
                                "error": {"code": -32002, "message": f"Component error in '{component_name}': {type(e).__name__} - {e}"},
                                "id": request_id
                            }
                else:
                    raise ValueError(f"Method '{method}' not found.")
            except json.JSONDecodeError:
                response_data = {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None}
            except ValueError as ve:
                error_code = -32602
                if "Invalid JSON-RPC" in str(ve) or "missing id" in str(ve): error_code = -32600
                elif "Method not found" in str(ve): error_code = -32601
                response_data = {"jsonrpc": "2.0", "error": {"code": error_code, "message": str(ve)}, "id": request_id}
            except RuntimeError as re:
                 response_data = {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(re)}, "id": request_id}
            except Exception as e:
                print(f"Internal error processing WebSocket message: {e}")
                response_data = {"jsonrpc": "2.0", "error": {"code": -32603, "message": f"Internal error: {type(e).__name__} - {e}"}, "id": request_id}

            await websocket.send(json.dumps(response_data))
            # print(f"Sent response to {websocket.remote_address}: {json.dumps(response_data)}")
    except websockets.exceptions.ConnectionClosedOK:
        print(f"Client disconnected gracefully: {websocket.remote_address} from path '{request_path}'")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"Client connection closed with error: {websocket.remote_address} from path '{request_path}', Error: {e}")
    except Exception as e:
        print(f"Overall error in WebSocket connection for {websocket.remote_address} on path '{request_path}': {e}")
    finally:
        print(f"Connection closed for {websocket.remote_address} from path '{request_path}'")

# Modified: setup_and_start_servers to use process_request_hook and functools.partial
async def setup_and_start_servers():
    import sys # Ensure sys is imported if not already at top level
    import os  # Ensure os is imported
    project_root = os.path.abspath(os.path.dirname(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    registry = ComponentRegistry() # Moved registry initialization here
    components_path = Path(project_root) / "components" # Define components_path
    registry.discover_components(components_path)
    print(f"Component registry initialized in setup_and_start_servers. Found {len(registry.manifests)} components.")


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

    httpd = socketserver.TCPServer(("0.0.0.0", PORT), CustomHandler, bind_and_activate=False)
    httpd.allow_reuse_address = True
    httpd.server_bind()
    httpd.server_activate()
    http_server_thread = threading.Thread(target=httpd.serve_forever, name="HTTPThread")
    http_server_thread.daemon = True

    # Modified: Use functools.partial for the handler
    bound_websocket_handler = functools.partial(websocket_handler, chat_backend=backend_instance, registry=registry)

    ws_server_object = await websockets.serve(
        bound_websocket_handler,
        "0.0.0.0",
        WS_PORT,
        process_request=process_request_hook # Added process_request_hook
    )

    print(f"HTTP Server configured for http://0.0.0.0:{PORT}")
    print(f"WebSocket Server configured for ws://0.0.0.0:{WS_PORT} with path hook")
    http_server_thread.start()
    print("HTTP server thread started.")
    return httpd, http_server_thread, ws_server_object

async def stop_servers(httpd, http_server_thread, ws_server_instance):
    print("Stopping WebSocket server...")
    if ws_server_instance:
        ws_server_instance.close()
        await ws_server_instance.wait_closed()
        print("WebSocket server stopped.")
    print("Stopping HTTP server...")
    if httpd:
        httpd.server_close()
    if http_server_thread and http_server_thread.is_alive():
        print("HTTP server thread is a daemon, should stop with main loop.")
    print("Servers stopping sequence initiated.")

# Modified: main() to use process_request_hook and functools.partial correctly
async def main():
    # Ensure server.py can find the components directory (duplicating setup_and_start_servers logic for clarity if main is run directly)
    import sys
    import os
    project_root_main = Path(__file__).resolve().parent
    if str(project_root_main) not in sys.path:
        sys.path.insert(0, str(project_root_main))

    # Initialize registry for main scope if not using setup_and_start_servers directly for all parts
    registry_main = ComponentRegistry()
    registry_main.discover_components(project_root_main / "components")
    print(f"Component registry initialized in main. Found {len(registry_main.manifests)} components.")

    # Initialize backend for main scope
    backend_instance_main = None
    global AIChatInterfaceBackend # Ensure global AIChatInterfaceBackend is accessible
    if AIChatInterfaceBackend is None: # Check if it was successfully imported at the top or by setup
        try:
            from components.AIChatInterface.backend import AIChatInterfaceBackend as BackendFromComponentsMain
            AIChatInterfaceBackend = BackendFromComponentsMain # Make it available globally if re-imported
            print("AIChatInterfaceBackend re-loaded successfully in main().")
        except ImportError:
            print("Warning: AIChatInterfaceBackend could not be imported even after sys.path modification in main().")

    if AIChatInterfaceBackend:
        backend_instance_main = AIChatInterfaceBackend()
        print("AIChatInterfaceBackend initialized for main.")
    else:
        print("CRITICAL ERROR: AIChatInterfaceBackend is None in main. Chat functionalities will not work.")

    CustomHandler.chat_backend = backend_instance_main # Ensure HTTP handler gets backend if main is entry point

    # HTTP Server Setup (similar to setup_and_start_servers)
    httpd_main = socketserver.TCPServer(("0.0.0.0", PORT), CustomHandler, bind_and_activate=False)
    httpd_main.allow_reuse_address = True
    httpd_main.server_bind()
    httpd_main.server_activate()
    http_server_thread_main = threading.Thread(target=httpd_main.serve_forever, name="HTTPThreadMain")
    http_server_thread_main.daemon = True

    # WebSocket Server Setup (similar to setup_and_start_servers)
    # Important: Use the registry and backend instance specific to this main's scope
    bound_websocket_handler_main = functools.partial(websocket_handler, chat_backend=backend_instance_main, registry=registry_main)

    ws_server_instance_main = await websockets.serve(
        bound_websocket_handler_main,
        "0.0.0.0",
        WS_PORT,
        process_request=process_request_hook # Added process_request_hook
    )

    print(f"HTTP Server starting at http://0.0.0.0:{PORT} (from main)")
    print(f"WebSocket Server starting at ws://0.0.0.0:{WS_PORT} (from main) with path hook")

    http_server_thread_main.start()
    print("HTTP server thread started (from main).")
    print("Application startup complete from main. Servers are starting...")

    try:
        if ws_server_instance_main:
            shutdown_event = asyncio.Event()
            print("Servers running (from main). Waiting for shutdown signal...")
            await shutdown_event.wait()
        else:
            print("WebSocket server failed to start (from main). Exiting.")
    except KeyboardInterrupt:
        print("KeyboardInterrupt received in main, shutting down...")
    finally:
        print("Main loop ending, initiating server shutdown (from main)...")
        await stop_servers(httpd_main, http_server_thread_main, ws_server_instance_main)

if __name__ == '__main__':
    # Note: The setup_and_start_servers() is primarily for tests or external management.
    # The main() function here provides a runnable server instance.
    # If tests are the primary user of setup_and_start_servers, ensure AIChatInterfaceBackend
    # and registry are correctly scoped or passed.
    # For clarity, main() now has its own full setup.
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Application shutdown (from __main__).")
