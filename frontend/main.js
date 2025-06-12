// Initialize Konva stage for main content
var mainStage = new Konva.Stage({
  container: 'container', // id of container <div>
  width: 500, // Should match the container div's width or be dynamic
  height: 500 // Should match the container div's height or be dynamic
});

// Add a layer to the main stage
var mainLayer = new Konva.Layer();
mainStage.add(mainLayer);

// Create a simple rectangle in the main stage
var mainRect = new Konva.Rect({
  x: 50,
  y: 50,
  width: 100,
  height: 50,
  fill: 'green',
  stroke: 'black',
  strokeWidth: 4
});

// Add the rectangle to the main layer
mainLayer.add(mainRect);

// Draw the main layer
mainLayer.draw();

// Get the sidebar element
const sidebarDiv = document.getElementById('sidebar');

// Initialize Konva stage for sidebar
if (sidebarDiv) {
  var sidebarStage = new Konva.Stage({
    container: sidebarDiv, // Use the div element directly
    width: sidebarDiv.clientWidth, // Dynamically set width
    height: 200 // Example height, adjust as needed
  });

  // Add a layer to the sidebar stage
  var sidebarLayer = new Konva.Layer();
  sidebarStage.add(sidebarLayer);

  // Create a 'Dummy Component' rectangle for the sidebar
  const initialSidebarComponentX = 10;
  const initialSidebarComponentY = 10;
  var dummyComponent = new Konva.Rect({
    x: initialSidebarComponentX,
    y: initialSidebarComponentY,
    width: 50,
    height: 50,
    fill: 'blue',
    stroke: 'black',
    strokeWidth: 2,
    draggable: true // Make the component draggable
  });

  // Add the dummy component to the sidebar layer
  sidebarLayer.add(dummyComponent);

  // Draw the sidebar layer
  sidebarLayer.draw();

  // Event listener for when the draggable sidebar component is dropped
  dummyComponent.on('dragend', function() {
    console.log("Sidebar dummy component drag ended.");

    // Get the pointer position relative to the main stage.
    // This is where the user dropped the component.
    var pointerPosition = mainStage.getPointerPosition();

    // Reset the original sidebar component to its initial position
    dummyComponent.position({ x: initialSidebarComponentX, y: initialSidebarComponentY });
    sidebarLayer.draw(); // Redraw sidebar layer to show the component back in place
    console.log("Sidebar dummy component position reset.");

    // If pointerPosition is null, it means the drop happened outside any Konva stage,
    // or the mainStage is not present.
    if (!pointerPosition) {
        console.warn("Drop event occurred, but pointer position is not available (possibly dropped outside of any Konva area or mainStage missing).");
        return;
    }

    // Check if the drop position is within the valid bounds of the mainStage.
    // We subtract the component's dimensions from the stage dimensions for the x, y checks
    // to ensure the entire component is within the bounds, assuming x,y is top-left.
    // For this example, we'll check if the drop point (cursor) is within the stage.
    // A more robust check might ensure the entire new shape fits.
    const withinXBounds = pointerPosition.x > 0 && pointerPosition.x < mainStage.width();
    const withinYBounds = pointerPosition.y > 0 && pointerPosition.y < mainStage.height();

    if (withinXBounds && withinYBounds) {
      console.log(`Drop position (main stage relative): X=${pointerPosition.x}, Y=${pointerPosition.y} - Within bounds.`);

      // Create a new rectangle (a "clone" of the dummy component) on the main stage
      var newRect = new Konva.Rect({
        // Adjust x and y to center the new rectangle on the pointer position
        x: pointerPosition.x - dummyComponent.width() / 2,
        y: pointerPosition.y - dummyComponent.height() / 2,
        width: dummyComponent.width(),
        height: dummyComponent.height(),
        fill: 'red', // Different color to distinguish from the sidebar component
        stroke: 'black',
        strokeWidth: 2,
        draggable: true // Make this new component on the main stage draggable as well
      });

      // Add the new rectangle to the main layer
      mainLayer.add(newRect);
      // Redraw the main layer to display the new component
      mainLayer.draw();
      console.log("New component created on main stage and main layer redrawn.");
    } else {
      console.log(`Drop position (main stage relative): X=${pointerPosition.x}, Y=${pointerPosition.y} - Outside main stage bounds.`);
    }
  });

} else {
  console.error("Sidebar element not found! Cannot initialize sidebar stage or dummy component.");
}
