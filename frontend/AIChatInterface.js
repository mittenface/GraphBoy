const AIChatInterface = () => {
  const [userInput, setUserInput] = React.useState('');
  const [temperature, setTemperature] = React.useState(0.5);
  const [maxTokens, setMaxTokens] = React.useState(256);

  const handleSubmit = (event) => {
    event.preventDefault();
    console.log({
      userInput,
      temperature,
      maxTokens,
    });
  };

  return React.createElement(
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
      { type: 'submit' },
      'Submit'
    )
  );
};
