const AIChatInterface = () => {
  const [userInput, setUserInput] = React.useState('');
  const [temperature, setTemperature] = React.useState(0.5);
  const [maxTokens, setMaxTokens] = React.useState(256);
  const [responseText, setResponseText] = React.useState('');
  const [isLoading, setIsLoading] = React.useState(false);
  const [isStreaming, setIsStreaming] = React.useState(false);
  const [error, setError] = React.useState(null);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setIsLoading(true);
    setIsStreaming(true);
    setError(null);
    setResponseText(''); // Clear previous response

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          userInput,
          temperature,
          maxTokens,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log('Success:', data);
      if (data.responseText) {
        setResponseText(data.responseText);
      } else {
        setError('No responseText found in the response.');
      }
    } catch (error) {
      console.error('Error:', error);
      setError(error.message || 'An unexpected error occurred.');
    } finally {
      setIsLoading(false);
      setIsStreaming(false);
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
        isLoading && !isStreaming ? 'Sending...' : 'Submit'
      ),
      isStreaming && React.createElement(
        'div',
        { style: { marginTop: '10px'} },
        'AI is typing...'
      )
    ),
    error && React.createElement(
      'div',
      { style: { color: 'red', marginTop: '10px' } },
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
