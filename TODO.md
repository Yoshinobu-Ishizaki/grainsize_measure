- Count up version.

## UI change

- Separate settings dialog and viewer window.
- Settings dialog window is a main window for this app. Viewer window obeys it. If settings window closes, app ends. User should not able to close viewer window. 
- The dialog window should be tabbed. One tab is for processing image, the other is for calculation of grain. The last one should be for save, export related.

## Strategy change

- Make image process to two steps.
- The first step is to make image into contrasted monochrome one using gsat functions. The viewer window should show the result of such image interactively.
- Also, user should be able to choose grain area with rubber band mouse selection interface. This area should be shown as a px coodinate values in a viewer window and values should be editable in numeric input controls.  
- User should be able to choose length marker area as same as grain area.
- Coordinates of grain area and marker area should be saved in json params.
- The second step is grain size detetion and calculation. 
- The main dialog window should have "open image, open params, image process, grain calc, save image, save params, export csv" buttons or menus.
- The viewer window should have two tabs. One should show original image. The secondo should show processed one and the result of grain detection should be overlayed to it.
