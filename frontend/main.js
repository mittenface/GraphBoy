// Initialize Konva stage
var stage = new Konva.Stage({
  container: 'container', // id of container <div>
  width: 500,
  height: 500
});

// Add a layer to the stage
var layer = new Konva.Layer();
stage.add(layer);

// Create a simple rectangle
var rect = new Konva.Rect({
  x: 50,
  y: 50,
  width: 100,
  height: 50,
  fill: 'green',
  stroke: 'black',
  strokeWidth: 4
});

// Add the rectangle to the layer
layer.add(rect);

// Draw the layer
layer.draw();
