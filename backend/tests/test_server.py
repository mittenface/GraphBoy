import pytest
import pytest_asyncio
import asyncio
import json
import websockets
import sys
import os

# Add project root to sys.path to allow server import
# Assuming this test file is in backend/tests/ and server.py is at the project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now we can import from server
from server import setup_and_start_servers, stop_servers, WS_PORT, AIChatInterfaceBackend

# If AIChatInterfaceBackend is None at this point, it means the initial import in server.py failed.
# The server's setup_and_start_servers() tries to re-import/re-initialize it.
# For tests, we want to know the state of this backend.

# Fixture to manage the server lifecycle
@pytest_asyncio.fixture(scope="module")
async def test_server():
    print("Starting server for module tests...")
    httpd, http_thread, ws_server_instance = await setup_and_start_servers()

    # Check if server started correctly - attempt to connect to WebSocket
    ws_uri = f"ws://localhost:{WS_PORT}"
    max_retries = 10  # Max 5 seconds (10 * 0.5s)
    retry_delay = 0.5
    for attempt in range(max_retries):
        try:
            print(f"Attempting to connect to WebSocket server (attempt {attempt + 1}/{max_retries})...")
            async with websockets.connect(ws_uri, open_timeout=0.5) as temp_ws: # Short open_timeout for readiness check
                # Ping to ensure connection is truly active
                pong_waiter = await temp_ws.ping()
                await asyncio.wait_for(pong_waiter, timeout=0.5)
                print("WebSocket server ready.")
                await temp_ws.close()
                break # Connected successfully
        except (ConnectionRefusedError, asyncio.TimeoutError, websockets.exceptions.InvalidHandshake) as e:
            print(f"Readiness check: Connection attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                pytest.fail(f"WebSocket server at {ws_uri} did not become ready after {max_retries * retry_delay} seconds.")
            await asyncio.sleep(retry_delay)

    assert http_thread.is_alive(), "HTTP server thread did not start."
    # For ws_server_instance, its presence implies it's serving. Websockets.serve starts serving immediately.

    yield # This is where the tests will run

    print("Stopping server after module tests...")
    await stop_servers(httpd, http_thread, ws_server_instance)
    # Ensure thread is stopped (it's a daemon, but good to check)
    if http_thread.is_alive():
        http_thread.join(timeout=1.0) # Attempt to join
        if http_thread.is_alive():
            print("Warning: HTTP server thread still alive after stop_servers and join.")
    print("Server stopped.")


@pytest.mark.asyncio
async def test_websocket_connection(test_server):
    uri = f"ws://localhost:{WS_PORT}"
    try:
        async with websockets.connect(uri) as websocket:
            assert websocket.open, "WebSocket connection failed to open."
            # Test sending a ping (optional, standard pings are handled by websockets library)
            # await websocket.ping()
            # pong_waiter = await websocket.ping()
            # await asyncio.wait_for(pong_waiter, timeout=1) # Check if pong is received
            print("WebSocket connected successfully.")
            await websocket.close()
    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused. Is the server running correctly?")
    except Exception as e:
        pytest.fail(f"test_websocket_connection failed: {e}")


async def send_json_rpc_request(uri, request_data):
    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps(request_data))
        response_str = await websocket.recv()
        return json.loads(response_str)

@pytest.mark.asyncio
async def test_json_rpc_chat_success(test_server):
    uri = f"ws://localhost:{WS_PORT}"
    request_id = 1
    request = {
        "jsonrpc": "2.0",
        "method": "chat",
        "params": {"userInput": "Hello server!", "temperature": 0.5, "maxTokens": 50},
        "id": request_id
    }

    # This test depends on AIChatInterfaceBackend being available and working.
    if AIChatInterfaceBackend is None : # Check if the original import in server was None
        if hasattr(server, 'AIChatInterfaceBackend') and server.AIChatInterfaceBackend is None: # Check after setup too
             pytest.skip("AIChatInterfaceBackend is not available, skipping chat success test.")

    try:
        response = await send_json_rpc_request(uri, request)
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == request_id
        assert "result" in response, f"Response missing 'result'. Error: {response.get('error')}"
        assert "responseText" in response["result"]
        # Actual responseText content depends on the backend's logic.
        # For this test, we're mainly checking structure and that it processes.
        print(f"Chat success response: {response['result']['responseText']}")
        assert isinstance(response["result"]["responseText"], str)
    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except Exception as e:
        pytest.fail(f"test_json_rpc_chat_success failed: {e}")


@pytest.mark.asyncio
async def test_json_rpc_method_not_found(test_server):
    uri = f"ws://localhost:{WS_PORT}"
    request_id = "err-m nf-1"
    request = {"jsonrpc": "2.0", "method": "non_existent_method", "params": {}, "id": request_id}
    try:
        response = await send_json_rpc_request(uri, request)
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == request_id
        assert "error" in response
        assert response["error"]["code"] == -32601 # Method not found
        assert "Method not found" in response["error"]["message"]
    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except Exception as e:
        pytest.fail(f"test_json_rpc_method_not_found failed: {e}")

@pytest.mark.asyncio
async def test_json_rpc_parse_error(test_server):
    uri = f"ws://localhost:{WS_PORT}"
    # ID might not be included in response if parse error is too severe
    malformed_request_str = '{"jsonrpc": "2.0", "method": "chat", "params": {"userInput":"test"}, "id": 1' # Missing closing brace
    try:
        async with websockets.connect(uri) as websocket:
            await websocket.send(malformed_request_str)
            response_str = await websocket.recv()
            response = json.loads(response_str)

        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") is None # ID is null for parse errors if it cannot be read
        assert "error" in response
        assert response["error"]["code"] == -32700 # Parse error
        assert "Parse error" in response["error"]["message"]
    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except Exception as e:
        pytest.fail(f"test_json_rpc_parse_error failed: {e}")


@pytest.mark.asyncio
async def test_json_rpc_invalid_request_missing_method(test_server):
    uri = f"ws://localhost:{WS_PORT}"
    request_id = "err-ir-1"
    request = {"jsonrpc": "2.0", "params": {}, "id": request_id} # Missing "method"
    try:
        response = await send_json_rpc_request(uri, request)
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == request_id
        assert "error" in response
        assert response["error"]["code"] == -32600 # Invalid Request
        assert "Invalid JSON-RPC request structure" in response["error"]["message"] or "Invalid JSON-RPC method" in response["error"]["message"]
    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except Exception as e:
        pytest.fail(f"test_json_rpc_invalid_request_missing_method failed: {e}")

@pytest.mark.asyncio
async def test_json_rpc_invalid_request_missing_id(test_server):
    uri = f"ws://localhost:{WS_PORT}"
    request = {"jsonrpc": "2.0", "method":"chat", "params": {"userInput":"test"}} # Missing "id"
    try:
        response = await send_json_rpc_request(uri, request)
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") is None # ID is null as it was missing in request, and server might respond with null id
        assert "error" in response
        assert response["error"]["code"] == -32600 # Invalid Request
        assert "missing id" in response["error"]["message"]
    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except Exception as e:
        pytest.fail(f"test_json_rpc_invalid_request_missing_id failed: {e}")


@pytest.mark.asyncio
async def test_json_rpc_chat_invalid_params_missing_userInput(test_server):
    uri = f"ws://localhost:{WS_PORT}"
    request_id = "err-ip-1"
    request = {
        "jsonrpc": "2.0",
        "method": "chat",
        "params": {"temperature": 0.5}, # Missing "userInput"
        "id": request_id
    }
    try:
        response = await send_json_rpc_request(uri, request)
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == request_id
        assert "error" in response
        assert response["error"]["code"] == -32602 # Invalid params
        assert "Missing 'userInput' in params" in response["error"]["message"]
    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except Exception as e:
        pytest.fail(f"test_json_rpc_chat_invalid_params_missing_userInput failed: {e}")

# This test is tricky because it relies on the global AIChatInterfaceBackend being None
# when setup_and_start_servers() is called by the fixture.
# This requires configuring the test environment or server.py carefully.
# For now, we assume if AIChatInterfaceBackend is None globally in server.py *before* setup,
# the server will start with it as None.
@pytest.mark.asyncio
async def test_json_rpc_chat_backend_not_available(test_server, monkeypatch):
    # We need to ensure the backend is None for this specific test.
    # One way is to monkeypatch the global AIChatInterfaceBackend in the server module
    # *before* the server fixture starts it for this test.
    # However, the fixture is module-scoped. This test needs a function-scoped server
    # or a way to configure the backend state for the existing server.

    # Simpler approach for now: check if the server started with a None backend.
    # This relies on how the server.py and fixture are structured.
    # The server.py prints "CRITICAL ERROR: AIChatInterfaceBackend is None..." if it's None.
    # We can't easily check that print here, but we can check the global in server.py
    # This is not ideal as it's checking global state used by the server.

    # Let's assume for this test to be meaningful, we'd need to force server.AIChatInterfaceBackend to None
    # then restart the server, or have a function-scoped fixture.
    # Given the current module-scoped fixture, we can try to monkeypatch server.AIChatInterfaceBackend
    # and then call setup_and_start_servers / stop_servers manually if the fixture wasn't used.
    # Or, if the backend *is* actually None (e.g. due to import issues), this test will pass.

    # This test will only run meaningfully if the server's `backend_instance` is indeed None.
    # We can't directly access `backend_instance` from `setup_and_start_servers` here easily.
    # A practical way is to check the global `AIChatInterfaceBackend` in the `server` module.
    # If this global is not None, this test might not reflect the "backend not available" state correctly.

    import server # direct import for checking its global
    if server.AIChatInterfaceBackend is not None:
        # To properly test this, we would need to modify the server startup for this test
        # or ensure the backend *can* fail to load.
        # For now, if the backend *is* available, we skip this test.
        pytest.skip("AIChatInterfaceBackend is available, cannot reliably test 'backend not available' scenario without specific test setup (e.g., function-scoped server with mocked backend).")

    uri = f"ws://localhost:{WS_PORT}"
    request_id = "err-bna-1"
    request = {
        "jsonrpc": "2.0",
        "method": "chat",
        "params": {"userInput": "Hello"},
        "id": request_id
    }
    try:
        response = await send_json_rpc_request(uri, request)
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == request_id
        assert "error" in response
        assert response["error"]["code"] == -32000 # Custom server error for backend issues
        assert "Chat backend not available" in response["error"]["message"]
    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except Exception as e:
        pytest.fail(f"test_json_rpc_chat_backend_not_available failed: {e}")

# TODO: Add a test for invalid JSON-RPC params type (e.g. string instead of object for "chat")
# TODO: Add a test for JSON-RPC request with non-string method name
# TODO: Add a test for JSON-RPC request with non-string/non-numeric/null ID
# These are partially covered by existing validation in server.py's websocket_handler.
# For example, `if not isinstance(request.get("method"), str):`

@pytest.mark.asyncio
async def test_json_rpc_chat_invalid_params_type(test_server):
    uri = f"ws://localhost:{WS_PORT}"
    request_id = "err-ipt-1"
    request = {
        "jsonrpc": "2.0",
        "method": "chat",
        "params": "this should be an object", # Invalid: params is a string
        "id": request_id
    }
    try:
        response = await send_json_rpc_request(uri, request)
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == request_id
        assert "error" in response
        assert response["error"]["code"] == -32602 # Invalid params
        assert "Invalid params for 'chat' method (must be an object)" in response["error"]["message"]
    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except Exception as e:
        pytest.fail(f"test_json_rpc_chat_invalid_params_type failed: {e}")

@pytest.mark.asyncio
async def test_json_rpc_invalid_method_type(test_server):
    uri = f"ws://localhost:{WS_PORT}"
    request_id = "err-imt-1"
    request = {"jsonrpc": "2.0", "method": 123, "params": {}, "id": request_id} # Invalid: method is a number
    try:
        response = await send_json_rpc_request(uri, request)
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == request_id
        assert "error" in response
        assert response["error"]["code"] == -32600 # Invalid Request (as method name must be string)
        assert "Invalid JSON-RPC method (must be string)" in response["error"]["message"]
    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except Exception as e:
        pytest.fail(f"test_json_rpc_invalid_method_type failed: {e}")

@pytest.mark.asyncio
async def test_json_rpc_invalid_id_type(test_server):
    uri = f"ws://localhost:{WS_PORT}"
    request_id_obj = {"id_is_object": True} # Invalid ID type (object)
    request = {"jsonrpc": "2.0", "method":"chat", "params": {"userInput":"test"}, "id": request_id_obj}
    try:
        response = await send_json_rpc_request(uri, request)
        assert response.get("jsonrpc") == "2.0"
        # The server should still try to use the (invalid) ID in its response if it can parse it.
        # If it can't parse the request due to the ID, it might be a parse error or invalid request.
        # The JSON-RPC spec says ID should be string, number, or null.
        # Our server's current validation `if "id" not in request:` only checks for presence.
        # It does not validate the *type* of the ID itself.
        # If the server successfully parses this, it will echo the object ID.
        # If it fails to serialize (e.g. if json.dumps has issues with the ID type in response map), that's a server bug.
        # For now, let's assume the server code for response `"id": request_id` handles this.
        # The more specific check is that the server returns an error because the request is bad,
        # but not because of the ID type itself directly based on current server code,
        # rather, a more general "Invalid Request" if the structure is too mangled.
        # However, Python's json.dumps will handle object IDs fine.
        # The client (test) expects `response.get("id") == request_id_obj`
        assert response.get("id") == request_id_obj
        assert "error" not in response # Assuming chat backend is available.
        # Actually, the spec implies that if ID is not string/number/null, it's not strictly compliant.
        # Let's refine this: the server *should* ideally flag an invalid ID type.
        # Current server code does not validate ID type, only presence.
        # So, it will likely pass if the backend is available.
        # This test might need to be re-evaluated based on stricter ID type validation on server.
        # For now, let's test the current behavior: it processes the request.
        if AIChatInterfaceBackend is None:
             pytest.skip("AIChatInterfaceBackend is not available, cannot fully test this scenario.")
        assert "result" in response

    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except Exception as e:
        pytest.fail(f"test_json_rpc_invalid_id_type failed: {e}")

    # Test with ID as array (also invalid type for JSON-RPC spec)
    request_id_arr = [1,2,3]
    request = {"jsonrpc": "2.0", "method":"chat", "params": {"userInput":"test array id"}, "id": request_id_arr}
    try:
        response = await send_json_rpc_request(uri, request)
        assert response.get("id") == request_id_arr
        if AIChatInterfaceBackend is None:
             pytest.skip("AIChatInterfaceBackend is not available, cannot fully test this scenario.")
        assert "result" in response
    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except Exception as e:
        pytest.fail(f"test_json_rpc_invalid_id_type (array) failed: {e}")

# Final check on AIChatInterfaceBackend availability to make some tests more robust or skippable.
# This is a bit of a hack. Ideally, the backend state would be more controllable for tests.
if AIChatInterfaceBackend is None:
    print("\nWARNING: AIChatInterfaceBackend was not available during test setup. Some chat-related tests might be skipped or may not reflect full backend integration.")

# It's good practice to also ensure that the server cleans up ports correctly.
# Pytest with allow_reuse_address helps, but checking for listen_on after server stop can be useful.
# However, that's more involved and platform-dependent.


@pytest.mark.asyncio
async def test_component_update_input_success(test_server):
    uri = f"ws://localhost:{WS_PORT}"
    request_id = "comp-success-1"
    component_name = "AIChatInterface" # Assuming this component exists and is discoverable
    user_input = "Hello component!"

    request = {
        "jsonrpc": "2.0",
        "method": "component.updateInput",
        "params": {
            "componentName": component_name,
            "inputs": {"userInput": user_input, "temperature": 0.6, "maxTokens": 60}
        },
        "id": request_id
    }

    if AIChatInterfaceBackend is None:
        pytest.skip("AIChatInterfaceBackend is not available, skipping component.updateInput success test.")

    try:
        response = await send_json_rpc_request(uri, request)
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == request_id
        assert "result" in response, f"Response missing 'result'. Error: {response.get('error')}"

        result = response["result"]
        assert "responseText" in result
        assert isinstance(result["responseText"], str)
        # Assuming the mock backend or actual backend would include these if process_request is called
        assert "responseStream" in result # Based on AIChatInterfaceBackend.process_request structure
        assert "error" in result and result["error"] is False # Based on AIChatInterfaceBackend.process_request structure

        print(f"Component update success response: {result['responseText']}")

    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except Exception as e:
        pytest.fail(f"test_component_update_input_success failed: {e}")


@pytest.mark.asyncio
async def test_component_update_input_not_found(test_server):
    uri = f"ws://localhost:{WS_PORT}"
    request_id = "comp-nf-1"
    component_name = "NonExistentComponent123"

    request = {
        "jsonrpc": "2.0",
        "method": "component.updateInput",
        "params": {
            "componentName": component_name,
            "inputs": {"someInput": "doesn't matter"}
        },
        "id": request_id
    }

    try:
        response = await send_json_rpc_request(uri, request)
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == request_id
        assert "error" in response, "Response missing 'error' field for non-existent component."

        error_details = response["error"]
        assert error_details.get("code") == -32001
        assert f"Component '{component_name}' not found" in error_details.get("message", "")

        print(f"Component not found response: {error_details}")

    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except Exception as e:
        pytest.fail(f"test_component_update_input_not_found failed: {e}")


@pytest.mark.asyncio
@pytest.mark.parametrize("params, expected_message_part", [
    ({"inputs": {"data": "value"}}, "Missing or invalid 'componentName'"), # Missing componentName
    ({"componentName": 123, "inputs": {"data": "value"}}, "Missing or invalid 'componentName'"), # componentName not a string
    ({"componentName": "TestComponent"}, "Missing or invalid 'inputs'"), # Missing inputs
    ({"componentName": "TestComponent", "inputs": "not_an_object"}, "Missing or invalid 'inputs'"), # inputs not an object
    ({}, "Missing or invalid 'componentName'"), # Empty params
])
async def test_component_update_input_invalid_params(test_server, params, expected_message_part):
    uri = f"ws://localhost:{WS_PORT}"
    request_id = f"comp-invp-{hash(json.dumps(params))}" # Unique ID for parametrized test

    request = {
        "jsonrpc": "2.0",
        "method": "component.updateInput",
        "params": params,
        "id": request_id
    }

    try:
        response = await send_json_rpc_request(uri, request)
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == request_id
        assert "error" in response, "Response missing 'error' field for invalid params."

        error_details = response["error"]
        assert error_details.get("code") == -32602 # Invalid Params
        assert expected_message_part in error_details.get("message", ""), \
            f"Error message '{error_details.get('message', '')}' did not contain '{expected_message_part}' for params: {params}"

        print(f"Invalid params response for {params}: {error_details}")

    except ConnectionRefusedError:
        pytest.fail(f"Connection to {uri} was refused.")
    except Exception as e:
        pytest.fail(f"test_component_update_input_invalid_params failed for {params}: {e}")
