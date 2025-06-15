const AIChatInterface = () => {
  const [userInput, setUserInput] = React.useState('');
  const [temperature, setTemperature] = React.useState(0.5);
  const [maxTokens, setMaxTokens] = React.useState(256);
  const [responseText, setResponseText] = React.useState('');
  const [isLoading, setIsLoading] = React.useState(false);
  // isStreaming might be less relevant for non-streaming JSON-RPC, but we'll keep it for UI consistency
  const [isStreaming, setIsStreaming] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [isConnected, setIsConnected] = React.useState(false);

  const websocketRef = React.useRef(null);
  const pendingRequestsRef = React.useRef(new Map());
  const messageIdCounterRef = React.useRef(0);

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const WS_URL = `${protocol}//${window.location.host}`;

  React.useEffect(() => {
    console.log('Attempting to connect WebSocket...');
    const ws = new WebSocket(WS_URL);
    websocketRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
      setError(null); // Clear any previous connection errors
    };

    ws.onmessage = (event) => {
      console.log('WebSocket message received:', event.data);
      try {
        const response = JSON.parse(event.data);
        if (response.jsonrpc !== "2.0" || response.id === undefined) {
          console.error("Received non-JSON-RPC or malformed message:", response);
          // Handle non-JSON-RPC or malformed messages if necessary,
          // maybe by setting a general error. For now, we primarily expect JSON-RPC.
          return;
        }

        // Check if it's a component.emitOutput message (server push)
        if (response.method === "component.emitOutput") {
          const { componentId, outputName, data } = response.params;
          // Assuming this component is always "AIChatInterface" for now
          if (componentId === "AIChatInterface") {
            if (outputName === "responseText") {
              setResponseText(data);
              setIsLoading(false);
              setIsStreaming(false);
              setError(null); // Clear previous errors on new data
            } else if (outputName === "responseStream") {
              // Assuming stream comes as a whole, not chunks, as per subtask description
              setResponseText(data);
              setIsLoading(false);
              setIsStreaming(false);
              setError(null);
            } else if (outputName === "error") {
              setError(data);
              setIsLoading(false);
              setIsStreaming(false);
              setResponseText(''); // Clear any previous response
            }
          } else {
            console.warn("Received component.emitOutput for unhandled componentId:", componentId);
          }
        }
        // Else, handle as a regular JSON-RPC response with an ID
        else if (response.id !== undefined) {
          const { id, result, error: rpcError } = response;
          const pendingRequest = pendingRequestsRef.current.get(id);

          if (pendingRequest) {
            if (rpcError) {
              pendingRequest.reject(rpcError);
            } else {
              pendingRequest.resolve(result);
            }
            pendingRequestsRef.current.delete(id);
          } else {
            console.warn("Received response for unknown message ID:", id);
          }
        } else {
           console.error("Received message that is not a component.emitOutput and lacks an ID:", response);
        }
      } catch (e) {
        console.error('Error parsing WebSocket message or processing response:', e);
        setError('Error processing message from server.');
        // If a specific request was in flight, we might not know its ID here
        // Consider how to handle this, perhaps by rejecting all pending requests or setting a general error.
      }
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      setError('WebSocket connection error. Please check if the server is running.');
      setIsConnected(false);
      setIsLoading(false); // Stop loading if an error occurs
      setIsStreaming(false);
      // Reject all pending requests on WebSocket error
      pendingRequestsRef.current.forEach(request => {
        request.reject({ code: -32000, message: 'WebSocket connection error.' });
      });
      pendingRequestsRef.current.clear();
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
      websocketRef.current = null; // Clear the ref
      // Optionally, you might want to inform the user or attempt reconnection here.
      // For now, we just log and update connection status.
      // Reject any pending requests that were not fulfilled before close
      pendingRequestsRef.current.forEach(request => {
        request.reject({ code: -32001, message: 'WebSocket disconnected before response.' });
      });
      pendingRequestsRef.current.clear();
    };

    return () => {
      if (websocketRef.current && websocketRef.current.readyState === WebSocket.OPEN) {
        console.log('Closing WebSocket connection...');
        websocketRef.current.close();
      }
      pendingRequestsRef.current.forEach(request => {
        request.reject({ code: -32002, message: 'Component unmounting, request cancelled.' });
      });
      pendingRequestsRef.current.clear();
    };
  }, []); // Empty dependency array ensures this runs once on mount and cleanup on unmount

  const generateMessageId = () => {
    messageIdCounterRef.current += 1;
    return messageIdCounterRef.current;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!websocketRef.current || websocketRef.current.readyState !== WebSocket.OPEN) {
      setError('WebSocket is not connected. Please wait or try refreshing.');
      setIsLoading(false);
      setIsStreaming(false);
      return;
    }

    setIsLoading(true);
    setIsStreaming(true); // Indicates waiting for output, e.g., "AI is typing..."
    setError(null);
    // setResponseText(''); // Clear previous response, actual content comes via emitOutput

    const messageId = generateMessageId();
    const request = {
      jsonrpc: '2.0',
      method: 'component.updateInput',
      params: {
        componentName: "AIChatInterface", // This should match the component ID registered on the backend
        inputs: { userInput, temperature, maxTokens }
      },
      id: messageId,
    };

    try {
      websocketRef.current.send(JSON.stringify(request));
      console.log('Sent JSON-RPC request (component.updateInput):', request);

      const responsePromise = new Promise((resolve, reject) => {
        pendingRequestsRef.current.set(messageId, { resolve, reject });
      });

      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject({ code: -32003, message: 'Request for component.updateInput timed out' }), 30000)
      );

      const result = await Promise.race([responsePromise, timeoutPromise]);
      // The result of component.updateInput is now just an acknowledgment,
      // e.g., {"status": "success", "message": "Output will be sent via component.emitOutput"}
      // The actual chat response comes from a component.emitOutput message.
      console.log('component.updateInput response result:', result);
      if (result && result.status === "success") {
        // Successfully initiated the backend processing.
        // isLoading and isStreaming will be set to false by the component.emitOutput handler.
        // If no component.emitOutput is received, isLoading/isStreaming might stay true until timeout or error.
      } else if (result && result.status === "error") {
        setError(result.message || 'Backend indicated an error with the input.');
        setIsLoading(false);
        setIsStreaming(false);
      } else {
         // This case might indicate a valid JSON-RPC response but not the expected data structure
        console.warn('Response to component.updateInput received, but not in expected format or indicates an issue:', result);
        // setError('Received an unexpected response from the server for updateInput.');
        // setIsLoading(false); // Stop loading if response is not as expected
        // setIsStreaming(false);
        // Keep isLoading true, as we are still expecting an emitOutput or a timeout/error from it.
      }

    } catch (rpcError) {
      console.error('JSON-RPC Error or Timeout for component.updateInput:', rpcError);
      setError(rpcError.message || 'An error occurred while sending the request.');
      setResponseText('');
      setIsLoading(false);
      setIsStreaming(false);
    } finally {
      // Note: We don't set isLoading/isStreaming to false here anymore for the success case,
      // as that's now handled by the component.emitOutput message handler.
      // It's only set to false here in case of an initial error sending/receiving the updateInput ack.
      pendingRequestsRef.current.delete(messageId);
    }
  };

  return React.createElement(
    React.Fragment,
    null,
    React.createElement(
      'form',
      { onSubmit: handleSubmit },
      React.createElement(
        'div',
      null,
      React.createElement(
        'label',
        { htmlFor: 'userInput' },
        '[Input Port] User Input:'
      ),
      React.createElement('textarea', {
        id: 'userInput',
        value: userInput,
        onChange: (e) => setUserInput(e.target.value),
      })
    ),
    React.createElement(
      'div',
      null,
      React.createElement(
        'label',
        { htmlFor: 'temperature' },
        '[Input Port] Temperature:'
      ),
      React.createElement('input', {
        type: 'number',
        id: 'temperature',
        value: temperature,
        onChange: (e) => setTemperature(parseFloat(e.target.value)),
        min: '0.0',
        max: '1.0',
        step: '0.1',
      })
    ),
    React.createElement(
      'div',
      null,
      React.createElement(
        'label',
        { htmlFor: 'maxTokens' },
        '[Input Port] Max Tokens:'
      ),
      React.createElement('input', {
        type: 'number',
        id: 'maxTokens',
        value: maxTokens,
        onChange: (e) => setMaxTokens(parseInt(e.target.value)),
        min: '50',
        max: '1000',
        step: '50',
      })
    ),
      React.createElement(
        'button',
        { type: 'submit', disabled: isLoading },
        isLoading ? 'Sending...' : (isConnected ? 'Submit' : 'Connecting...')
      ),
      // Display connection status
      React.createElement(
        'div',
        { style: { marginTop: '5px', fontSize: '0.9em', color: isConnected ? 'green' : 'orange' } },
        isConnected ? 'WebSocket Connected' : 'WebSocket Disconnected. Attempting to connect...'
      ),
      isLoading && isStreaming && React.createElement( // Show "AI is typing..." only when loading and streaming
        'div',
        { style: { marginTop: '10px'} },
        'AI is typing...'
      ),
      isLoading && isStreaming && React.createElement(
        'div',
        { style: { marginTop: '10px'} },
        '[Output Port: responseStream active]'
      )
    ),
    error && React.createElement(
      'div',
      { style: { color: 'red', marginTop: '10px', whiteSpace: 'pre-wrap' } }, // pre-wrap for better error display
      `Error: [Output Port] ${error}`
    ),
    responseText && React.createElement(
      'div',
      { style: { marginTop: '20px', padding: '10px', border: '1px solid #ccc', whiteSpace: 'pre-wrap' } },
      React.createElement('h3', null, '[Output Port] AI Response:'),
      responseText
    )
  );
};