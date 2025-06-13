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

  const WS_URL = 'ws://localhost:5001';

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
    setIsStreaming(true); // For UI feedback, like "AI is typing..."
    setError(null);
    setResponseText('');

    const messageId = generateMessageId();
    const request = {
      jsonrpc: '2.0',
      method: 'chat',
      params: { userInput, temperature, maxTokens },
      id: messageId,
    };

    try {
      websocketRef.current.send(JSON.stringify(request));
      console.log('Sent JSON-RPC request:', request);

      const responsePromise = new Promise((resolve, reject) => {
        pendingRequestsRef.current.set(messageId, { resolve, reject });
      });

      // Timeout for the request
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject({ code: -32003, message: 'Request timed out' }), 30000) // 30s timeout
      );

      const result = await Promise.race([responsePromise, timeoutPromise]);

      console.log('JSON-RPC response result:', result);
      if (result && result.responseText !== undefined) {
        setResponseText(result.responseText);
      } else {
        // This case might indicate a valid JSON-RPC response but not the expected data structure
        console.warn('Response received, but `responseText` field is missing:', result);
        setError('Received a response, but it was not in the expected format.');
      }
    } catch (rpcError) {
      console.error('JSON-RPC Error or Timeout:', rpcError);
      setError(rpcError.message || 'An error occurred while processing your request.');
      setResponseText(''); // Clear any partial response
    } finally {
      setIsLoading(false);
      setIsStreaming(false);
      pendingRequestsRef.current.delete(messageId); // Clean up, even on timeout
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
        'User Input:'
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
        'Temperature:'
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
        'Max Tokens:'
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
      )
    ),
    error && React.createElement(
      'div',
      { style: { color: 'red', marginTop: '10px', whiteSpace: 'pre-wrap' } }, // pre-wrap for better error display
      `Error: ${error}`
    ),
    responseText && React.createElement(
      'div',
      { style: { marginTop: '20px', padding: '10px', border: '1px solid #ccc', whiteSpace: 'pre-wrap' } },
      React.createElement('h3', null, 'AI Response:'),
      responseText
    )
  );
};
