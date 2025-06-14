import http.server
import socketserver
import json
from urllib.parse import urlparse # parse_qs removed
import asyncio
import websockets
import threading
import functools # Added for functools.partial
from pathlib import Path
import logging

from backend.component_registry import ComponentRegistry

try:
    from components.AIChatInterface.backend import AIChatInterfaceBackend
except ImportError:
    print("Warning: Could not import AIChatInterfaceBackend directly. Ensure PYTHONPATH is set up correctly or that components are structured as a package.")
    AIChatInterfaceBackend = None

PORT = 5000
WS_PORT = 8080

async def process_request_hook(server_connection, request):
    """
    Custom process_request hook for the websockets server.

    This hook is called for each incoming WebSocket request and allows us to:
    1. Log request details for debugging
    2. Extract and store the request path on the websocket object
    3. Optionally return a custom HTTP response (we don't do this here)

    Args:
        server_connection: The WebSocket server connection object
        request: The HTTP request object containing headers and path
    """
    logger = logging.getLogger(__name__)
    logger.info(
        f"process_request_hook: received request: "
        f"'{request}' (type: {type(request)})"
    )

    # Extract the path from the Request object
    path_to_set = request.path
    logger.info(f"process_request_hook: extracted path '{path_to_set}' from Request object")

    # Store the request path on the server_connection object for later use
    server_connection.actual_request_path = path_to_set
    logger.info(
        f"process_request_hook: server_connection.actual_request_path finally set to "
        f"'{server_connection.actual_request_path}' (type: {type(server_connection.actual_request_path)})"
    )

async def enhanced_process_request_hook(server_connection, request):
    """
    Enhanced process_request hook that logs detailed information about
    invalid WebSocket upgrade requests for debugging purposes.
    """
    try:
        # Call the original process_request_hook functionality
        await process_request_hook(server_connection, request)
    except Exception as e:
        # Log detailed information about the failed request
        logger = logging.getLogger(__name__)
        logger.error(
            f"WebSocket upgrade failed - Enhanced logging:\n"
            f"  Exception: {type(e).__name__}: {e}\n"
            f"  Remote Address: {getattr(server_connection, 'remote_address', 'unknown')}\n"
            f"  Request Path: {getattr(request, 'path', 'unknown')}\n"
            f"  Request Headers: {dict(getattr(request, 'headers', {}))}\n"
            f"  User-Agent: {getattr(request, 'headers', {}).get('User-Agent', 'not provided')}\n"
            f"  Origin: {getattr(request, 'headers', {}).get('Origin', 'not provided')}\n"
            f"  Connection: {getattr(request, 'headers', {}).get('Connection', 'missing - this is likely the issue')}\n"
            f"  Upgrade: {getattr(request, 'headers', {}).get('Upgrade', 'not provided')}"
        )
        raise  # Re-raise the exception to maintain original behavior

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
    # Get path from hook
    request_path = getattr(websocket, 'actual_request_path', '/')
    print(f"Client connected from {websocket.remote_address} on path '{request_path}'")
    try:
        async for message_str in websocket:
            request_id = None
            try:
                # print(
                #    f"Received message from {websocket.remote_address} on path "
                #    f"'{request_path}': {message_str}"
                # )
                request = json.loads(message_str)
                request_id = request.get("id")

                if (not all(k in request for k in ("jsonrpc", "method")) or
                        request.get("jsonrpc") != "2.0"):
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
                        raise ValueError(
                            "Invalid params for 'chat' method (must be an object)."
                        )
                    user_input = params.get("userInput")
                    if user_input is None:
                        raise ValueError(
                            "Missing 'userInput' in params for 'chat' method."
                        )
                    temperature = params.get("temperature", 0.7)
                    max_tokens = params.get("maxTokens", 256)
                    backend_response = chat_backend.process_request(
                        user_input=user_input,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    response_data = {"jsonrpc": "2.0",
                                     "result": backend_response, "id": request_id}
                elif method == "component.updateInput":
                    if not isinstance(params, dict):
                        raise ValueError(
                            "Invalid params for 'component.updateInput' (must be an object)."
                        )
                    component_name = params.get("componentName")
                    inputs_data = params.get("inputs")
                    if not isinstance(component_name, str):
                        raise ValueError(
                            "Missing or invalid 'componentName' in params for "
                            "'component.updateInput' (must be a string)."
                        )
                    if not isinstance(inputs_data, dict):
                        raise ValueError(
                            "Missing or invalid 'inputs' in params for "
                            "'component.updateInput' (must be an object)."
                        )

                    component_instance = registry.get_component_instance(component_name)
                    if component_instance is None:
                        response_data = {
                            "jsonrpc": "2.0",
                            "error": {"code": -32001,
                                      "message": f"Component '{component_name}' not found."},
                            "id": request_id
                        }
                    else:
                        try:
                            response_content = component_instance.update(inputs_data)
                            response_data = {"jsonrpc": "2.0",
                                             "result": response_content,
                                             "id": request_id}
                        except Exception as e:
                            print(f"Error during component '{component_name}' update: {e}")
                            response_data = {
                                "jsonrpc": "2.0",
                                "error": {"code": -32002,
                                          "message": f"Component error in '{component_name}': {type(e).__name__} - {e}"},
                                "id": request_id
                            }
                else:
                    raise ValueError(f"Method '{method}' not found.")
            except json.JSONDecodeError:
                response_data = {"jsonrpc": "2.0",
                                 "error": {"code": -32700, "message": "Parse error"},
                                 "id": None}
            except ValueError as ve:
                error_code = -32602
                if "Invalid JSON-RPC" in str(ve) or "missing id" in str(ve):
                    error_code = -32600
                elif "Method not found" in str(ve):
                    error_code = -32601
                response_data = {"jsonrpc": "2.0",
                                 "error": {"code": error_code, "message": str(ve)},
                                 "id": request_id}
            except RuntimeError as re:
                 response_data = {"jsonrpc": "2.0",
                                  "error": {"code": -32000, "message": str(re)},
                                  "id": request_id}
            except Exception as e:
                print(f"Internal error processing WebSocket message: {e}")
                response_data = {"jsonrpc": "2.0",
                                 "error": {"code": -32603,
                                           "message": f"Internal error: {type(e).__name__} - {e}"},
                                 "id": request_id}

            await websocket.send(json.dumps(response_data))
            # print(
            #     f"Sent response to {websocket.remote_address}: "
            #     f"{json.dumps(response_data)}"
            # )
    except websockets.exceptions.ConnectionClosedOK:
        print(
            f"Client disconnected gracefully: {websocket.remote_address} "
            f"from path '{request_path}'"
        )
    except websockets.exceptions.ConnectionClosedError as e:
        print(
            f"Client connection closed with error: {websocket.remote_address} "
            f"from path '{request_path}', Error: {e}"
        )
    except Exception as e:
        print(
            f"Overall error in WebSocket connection for {websocket.remote_address} "
            f"on path '{request_path}': {e}"
        )
    finally:
        print(
            f"Connection closed for {websocket.remote_address} from path '{request_path}'"
        )

# Modified: setup_and_start_servers to use process_request_hook and functools.partial
async def setup_and_start_servers():
    import sys # Ensure sys is imported if not already at top level
    # import os  # Ensure os is imported # os removed
    # Replaced os.path.abspath(os.path.dirname(__file__))
    project_root = str(Path(__file__).resolve().parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    registry = ComponentRegistry() # Moved registry initialization here
    components_path = Path(project_root) / "components" # Define components_path
    registry.discover_components(components_path)
    print(
        f"Component registry initialized in setup_and_start_servers. "
        f"Found {len(registry.manifests)} components."
    )


    backend_instance = None
    global AIChatInterfaceBackend
    if AIChatInterfaceBackend is None:
        try:
            from components.AIChatInterface.backend import AIChatInterfaceBackend as BackendFromComponents
            AIChatInterfaceBackend = BackendFromComponents
            print(
                "AIChatInterfaceBackend re-loaded successfully in setup_and_start_servers()."
            )
        except ImportError:
            print(
                "Warning: AIChatInterfaceBackend could not be imported in setup_and_start_servers()."
            )

    if AIChatInterfaceBackend:
        backend_instance = AIChatInterfaceBackend()
        print("AIChatInterfaceBackend initialized.")
    else:
        print(
            "CRITICAL ERROR: AIChatInterfaceBackend is None. "
            "Chat functionalities will not work."
        )

    CustomHandler.chat_backend = backend_instance

    httpd = socketserver.TCPServer(("0.0.0.0", PORT), CustomHandler,
                                   bind_and_activate=False)
    httpd.allow_reuse_address = True
    httpd.server_bind()
    httpd.server_activate()
    http_server_thread = threading.Thread(target=httpd.serve_forever,
                                          name="HTTPThread")
    http_server_thread.daemon = True

    # Modified: Use functools.partial for the handler
    bound_websocket_handler = functools.partial(websocket_handler,
                                                chat_backend=backend_instance,
                                                registry=registry)

    ws_server_object = await websockets.serve(
        bound_websocket_handler,
        "0.0.0.0",
        WS_PORT,
        process_request=enhanced_process_request_hook # Use enhanced hook for debugging
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
    # Ensure server.py can find the components directory (duplicating
    # setup_and_start_servers logic for clarity if main is run directly)
    import sys
    # import os # os removed
    project_root_main = Path(__file__).resolve().parent
    if str(project_root_main) not in sys.path:
        sys.path.insert(0, str(project_root_main))

    # Initialize registry for main scope if not using setup_and_start_servers
    # directly for all parts
    registry_main = ComponentRegistry()
    registry_main.discover_components(project_root_main / "components")
    print(
        f"Component registry initialized in main. "
        f"Found {len(registry_main.manifests)} components."
    )

    # Initialize backend for main scope
    backend_instance_main = None
    # Ensure global AIChatInterfaceBackend is accessible
    global AIChatInterfaceBackend
    # Check if it was successfully imported at the top or by setup
    if AIChatInterfaceBackend is None:
        try:
            from components.AIChatInterface.backend import AIChatInterfaceBackend as BackendFromComponentsMain
            # Make it available globally if re-imported
            AIChatInterfaceBackend = BackendFromComponentsMain
            print("AIChatInterfaceBackend re-loaded successfully in main().")
        except ImportError:
            print(
                "Warning: AIChatInterfaceBackend could not be imported even after "
                "sys.path modification in main()."
            )

    if AIChatInterfaceBackend:
        # Define a mock send function for the main scope
        def mock_send_output(component_id, output_name, data):
            print(f"Output from {component_id}: {output_name} = {data}")

        backend_instance_main = AIChatInterfaceBackend(
            component_id="main_chat_instance", 
            send_component_output_func=mock_send_output
        )
        print("AIChatInterfaceBackend initialized for main.")
    else:
        print(
            "CRITICAL ERROR: AIChatInterfaceBackend is None in main. "
            "Chat functionalities will not work."
        )

    # Ensure HTTP handler gets backend if main is entry point
    CustomHandler.chat_backend = backend_instance_main

    # HTTP Server Setup (similar to setup_and_start_servers)
    httpd_main = socketserver.TCPServer(("0.0.0.0", PORT), CustomHandler,
                                        bind_and_activate=False)
    httpd_main.allow_reuse_address = True
    httpd_main.server_bind()
    httpd_main.server_activate()
    http_server_thread_main = threading.Thread(target=httpd_main.serve_forever,
                                               name="HTTPThreadMain")
    http_server_thread_main.daemon = True

    # WebSocket Server Setup (similar to setup_and_start_servers)
    # Important: Use the registry and backend instance specific to this main's scope
    bound_websocket_handler_main = functools.partial(
        websocket_handler,
        chat_backend=backend_instance_main,
        registry=registry_main
    )

    ws_server_instance_main = await websockets.serve(
        bound_websocket_handler_main,
        "0.0.0.0",
        WS_PORT,
        process_request=enhanced_process_request_hook # Use enhanced hook for debugging
    )

    print(f"HTTP Server starting at http://0.0.0.0:{PORT} (from main)")
    print(
        f"WebSocket Server starting at ws://0.0.0.0:{WS_PORT} (from main) with path hook"
    )

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
        await stop_servers(httpd_main, http_server_thread_main,
                           ws_server_instance_main)

if __name__ == '__main__':
    # Note: The setup_and_start_servers() is primarily for tests or external
    # management. The main() function here provides a runnable server instance.
    # If tests are the primary user of setup_and_start_servers, ensure
    # AIChatInterfaceBackend and registry are correctly scoped or passed.
    # For clarity, main() now has its own full setup.
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Application shutdown (from __main__).")
import asyncio
import logging
import sys
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading
import os

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.server import setup_and_start_servers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CustomHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=".", **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

def start_http_server():
    """Start HTTP server for frontend files on port 5000"""
    try:
        os.chdir(str(project_root))  # Ensure we're in the right directory
        httpd = HTTPServer(("0.0.0.0", 5000), CustomHTTPRequestHandler)
        logger.info("HTTP Server starting at http://0.0.0.0:5000 (from main)")
        httpd.serve_forever()
    except Exception as e:
        logger.error(f"HTTP server failed: {e}")

async def main():
    # Start HTTP server in a separate thread
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()
    logger.info("HTTP server thread started (from main).")

    # Start WebSocket server
    logger.info("WebSocket Server starting at ws://0.0.0.0:8080 (from main) with path hook")
    ws_server = await setup_and_start_servers()
    if ws_server is None:
        logger.error("WebSocket server failed to start. Exiting.")
        return

    logger.info("Application startup complete from main. Servers are starting...")

    # Wait for WebSocket server to close
    await ws_server.wait_closed()
    logger.info("WebSocket server has shut down.")

if __name__ == "__main__":
    asyncio.run(main())