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
let sidebarStage; // Declare here to be accessible
let sidebarLayer; // Declare here to be accessible

if (sidebarDiv) {
  sidebarStage = new Konva.Stage({
    container: sidebarDiv, // Use the div element directly
    width: sidebarDiv.clientWidth, // Dynamically set width
    height: 600 // Adjusted height for more components, can be dynamic
  });

  sidebarLayer = new Konva.Layer();
  sidebarStage.add(sidebarLayer);

  const initialSidebarComponentX = 10;
  let currentSidebarComponentY = 10; // Start Y for the first component
  const componentHeight = 40;
  const componentWidth = 150;
  const componentSpacing = 10;

  fetch('/api/components')
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(components => {
        if (!Array.isArray(components)) {
            console.error("Error: /api/components did not return an array.", components);
            const errorText = new Konva.Text({
                x: initialSidebarComponentX,
                y: currentSidebarComponentY,
                text: "Error: Invalid component data.",
                fontSize: 12,
                fill: 'red'
            });
            sidebarLayer.add(errorText);
            sidebarLayer.draw();
            return;
        }
        if (components.length === 0) {
            const noComponentsText = new Konva.Text({
                x: initialSidebarComponentX,
                y: currentSidebarComponentY,
                text: "No components available.",
                fontSize: 12,
                fill: 'black'
            });
            sidebarLayer.add(noComponentsText);
            sidebarLayer.draw();
            return;
        }

        components.forEach((manifest, index) => {
            const componentGroup = new Konva.Group({
                x: initialSidebarComponentX,
                y: currentSidebarComponentY,
                draggable: true,
                width: componentWidth,
                height: componentHeight
            });
            componentGroup.setAttr('manifest', manifest);

            const rect = new Konva.Rect({
                width: componentWidth,
                height: componentHeight,
                fill: manifest.color || 'lightblue', // Use manifest color or default
                stroke: 'black',
                strokeWidth: 1
            });
            componentGroup.add(rect);

            const nameText = new Konva.Text({
                text: manifest.name || 'Unnamed',
                fontSize: 14,
                fontFamily: 'Arial',
                fill: 'black',
                padding: 5,
                align: 'center',
                verticalAlign: 'middle',
                width: componentWidth,
                height: componentHeight,
                listening: false // Text doesn't block dragging group
            });
            componentGroup.add(nameText);

            const originalX = initialSidebarComponentX;
            const originalY = currentSidebarComponentY;

            componentGroup.on('dragstart', function() {
                this.moveToTop();
                sidebarLayer.draw();
            });

            componentGroup.on('dragend', function() {
                const manifestData = this.getAttr('manifest');
                var pointerPosition = mainStage.getPointerPosition();

                this.position({ x: originalX, y: originalY });
                sidebarLayer.draw();

                if (!pointerPosition) {
                    console.warn("Drop outside Konva area or mainStage not available.");
                    return;
                }

                const stageRect = mainStage.getClientRect(); // Gets visible area of mainStage
                if (pointerPosition.x < 0 || pointerPosition.x > stageRect.width ||
                    pointerPosition.y < 0 || pointerPosition.y > stageRect.height) {
                    console.log("Dropped outside main stage bounds.", {pointerPosition, stageRect});
                    return;
                }

                const newMainComponentGroup = new Konva.Group({
                    x: pointerPosition.x - componentWidth / 2,
                    y: pointerPosition.y - componentHeight / 2,
                    draggable: true,
                    width: componentWidth,
                    height: componentHeight
                });
                newMainComponentGroup.setAttr('manifest', manifestData);

                const newRect = new Konva.Rect({
                    width: componentWidth,
                    height: componentHeight,
                    fill: manifestData.color || 'lightgreen', // Use manifest color or a different default for main stage
                    stroke: 'black',
                    strokeWidth: 2
                });
                newMainComponentGroup.add(newRect);

                const newNameText = new Konva.Text({
                    text: manifestData.name || 'Unnamed',
                    fontSize: 14,
                    fontFamily: 'Arial',
                    fill: 'black',
                    padding: 5,
                    align: 'center',
                    verticalAlign: 'middle',
                    width: componentWidth,
                    height: componentHeight,
                    listening: false
                });
                newMainComponentGroup.add(newNameText);

                mainLayer.add(newMainComponentGroup);
                mainLayer.draw();
                console.log(`New component '${manifestData.name}' added to main stage.`);
            });

            sidebarLayer.add(componentGroup);
            currentSidebarComponentY += componentHeight + componentSpacing;
        });
        sidebarLayer.draw();
    })
    .catch(error => {
        console.error('Error fetching or processing components:', error);
        const errorText = new Konva.Text({
            x: initialSidebarComponentX,
            y: currentSidebarComponentY,
            text: "Failed to load. Check console.",
            fontSize: 12,
            fill: 'red'
        });
        sidebarLayer.add(errorText);
        sidebarLayer.draw();
    });

} else {
  console.error("Sidebar element not found! Cannot initialize sidebar stage.");
}
