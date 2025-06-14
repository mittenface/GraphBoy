import pytest
import pytest_asyncio
import asyncio
import json
import websockets
from unittest.mock import MagicMock, patch

# Attempt to import from server.py, handling potential early-stage non-existence
try:
    from backend.server import WS_PORT, AIChatInterfaceBackend, websocket_handler, setup_and_start_servers, component_registry
    SERVER_AVAILABLE = True
except ImportError:
    SERVER_AVAILABLE = False
    # Define WS_PORT here if server.py is not available, so tests can be parsed
    WS_PORT = 8765
    # Define dummy classes/functions if server components are not available
    class AIChatInterfaceBackend: pass
    async def websocket_handler(websocket, path, chat_backend, registry): pass # Original problematic signature for parsing
    async def setup_and_start_servers(): pass
    class ComponentRegistry:
        def get_component_instance(self, name): return None
        def register_component(self, name, klass, instance=None): pass
    component_registry = ComponentRegistry()


from backend.component_registry import ComponentRegistry # This should be the actual one

# Helper function to send JSON-RPC request (should be present in the test file)
async def send_json_rpc_request(uri, request_data):
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(request_data))
        response = await ws.recv()
        return json.loads(response)

@pytest_asyncio.fixture # Changed from @pytest.fixture
async def test_server():
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping server tests as server.py components are not available.")

    # Ensure the registry is clean for each test run if it's a global instance
    # This might involve a reset method on ComponentRegistry or re-initialization
    # For now, we assume component_registry is managed by setup_and_start_servers

    server_process = None
    try:
        # Start the server
        server_task = asyncio.create_task(setup_and_start_servers())

        # Wait for the server to be ready
        # This simple check pings the server; more robust checks might be needed
        uri = f"ws://localhost:{WS_PORT}/" # Added trailing slash for consistency
        up = False
        for _ in range(10): # Try for a few seconds
            await asyncio.sleep(0.2)
            try:
                async with websockets.connect(uri) as temp_ws:
                    await temp_ws.ping()
                    up = True
                    break
            except (ConnectionRefusedError, websockets.exceptions.InvalidStatusCode):
                continue # Server not ready yet
            except Exception as e: # Catch broader exceptions during check
                print(f"Test server readiness check failed: {e}")
                continue

        if not up:
            # Attempt to stop the server task if it was started
            if server_task and not server_task.done():
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    print("Server task cancelled during setup failure.")
            raise RuntimeError(f"WebSocket server at {uri} did not start in time.")

        yield uri # Provide the URI to the tests

        # Teardown: Stop the server task
        if server_task and not server_task.done():
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                print("Server task cancelled successfully during teardown.")

    except Exception as e:
        pytest.fail(f"Test server fixture setup failed: {e}")
    finally:
        # Ensure any server task is cancelled, even if setup failed partway
        if 'server_task' in locals() and server_task and not server_task.done():
            server_task.cancel()
            try:
                await server_task # Wait for cancellation to complete
            except asyncio.CancelledError:
                pass # Expected


@pytest.mark.asyncio
async def test_component_update_input_routes_to_chat_component(test_server, monkeypatch):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping test as server.py components are not available.")

    uri = test_server # Use the URI from the fixture
    request_id = "comp-route-test-1"
    component_name = "AIChatInterface" # This must match the one registered in server.py
    test_inputs = {"userInput": "Testing routing", "temperature": 0.5, "maxTokens": 50}

    # 1. Set up a mock AIChatInterfaceBackend instance
    mock_chat_backend = MagicMock(spec=AIChatInterfaceBackend)
    # Configure the mock update method to return a serializable dictionary
    mock_chat_backend.update.return_value = {"status": "mock update called", "responseText": "mocked response from update"}
    # Mock get_component_id if it's called by the handler indirectly
    mock_chat_backend.get_component_id.return_value = "AIChatInterface"


    # 2. Patch ComponentRegistry.get_component_instance
    # We need to access the registry instance that is used by the server's websocket_handler.
    # If component_registry is imported directly from server, we can patch that.

    # Get the actual registry instance used by the server.
    # This relies on `component_registry` being the actual instance used by `setup_and_start_servers`.
    # If `setup_and_start_servers` creates its own registry, this patching won't affect it.
    # The server.py creates a global `component_registry` and `setup_and_start_servers` uses it.

    original_get_component_instance = component_registry.get_component_instance

    def mock_get_component_instance(name): # Changed from method to function
        if name == component_name:
            return mock_chat_backend
        # For other components, you might want to call the original method
        # or return another appropriate mock/real instance.
        return original_get_component_instance(name)

    monkeypatch.setattr(component_registry, 'get_component_instance', mock_get_component_instance)

    # 3. Prepare and send the WebSocket request
    request = {
        "jsonrpc": "2.0",
        "method": "component.updateInput",
        "params": {
            "componentName": component_name,
            "inputs": test_inputs
        },
        "id": request_id
    }

    response = None
    try:
        response = await send_json_rpc_request(uri, request)

        # 4. Assertions
        # Check that the mock_chat_backend.update was called correctly
        mock_chat_backend.update.assert_called_once_with(test_inputs)

        # Check the server's response
        assert response is not None, "Response was None"
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == request_id

        # Check for error field in response before asserting result
        if "error" in response:
            pytest.fail(f"Server returned an error: {response['error']}")

        assert "result" in response, "Response missing 'result' field."
        assert response["result"] == mock_chat_backend.update.return_value

    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except websockets.exceptions.ConnectionClosedError as e:
        pytest.fail(f"Connection closed unexpectedly: {e}. Server log might have details. Response: {response}")
    except Exception as e:
        pytest.fail(f"Test failed: {type(e).__name__} - {e}. Response: {response}")
    finally:
        # Clean up the patch
        monkeypatch.undo()

# Example of another test that might exist (to ensure the overwrite doesn't remove everything)
@pytest.mark.asyncio
async def test_server_responds_to_ping(test_server):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping test as server.py components are not available.")
    uri = test_server
    try:
        async with websockets.connect(uri) as ws:
            await ws.ping()
            # Pong is handled automatically by websockets library,
            # if ping is successful, connection is good.
            assert True # If ping doesn't raise an exception, it's good.
    except Exception as e:
        pytest.fail(f"Ping test failed: {e}")

# A simple test to ensure basic JSON-RPC invalid request is handled
@pytest.mark.asyncio
async def test_invalid_json_rpc_request(test_server):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping test as server.py components are not available.")
    uri = test_server
    request = {"invalid_json_rpc": True} # Not a valid JSON-RPC request

    response = await send_json_rpc_request(uri, request)

    assert response.get("jsonrpc") == "2.0"
    assert "error" in response
    assert response["error"]["code"] == -32600 # Invalid Request
    assert response.get("id") is None # Or matches request id if provided, but this one is None

@pytest.mark.asyncio
async def test_method_not_found(test_server):
    if not SERVER_AVAILABLE:
        pytest.skip("Skipping test as server.py components are not available.")
    uri = test_server
    request_id = "method-not-found-test-1"
    request = {
        "jsonrpc": "2.0",
        "method": "nonExistent.method",
        "params": {},
        "id": request_id
    }
    response = await send_json_rpc_request(uri, request)
    assert response.get("jsonrpc") == "2.0"
    assert response.get("id") == request_id
    assert "error" in response
    assert response["error"]["code"] == -32601 # Method not found
