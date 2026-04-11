- @tests/sample/c2600p_asis_overlay.png shows many gray area which seems to be grain for humans eye but not detected by the app. Can you find reason for this and search better processing parameter to detect those area as grains? If you find better results, please save those parameters json file.
- if scale bar is detected, bar line should be overlayed on top of scale bar area with vivid red color. the position of scale bar should be remembered in parameters.json. if scale bar position is not null in parameters.json, it should show the line as same as it is just found. Show scale line on to the processed image not to original image.


---

## TODO for next turn

- Add parameter optimizer functionality for any image file.
- The optimizer is a different program which can be invoked via terminal or from the app.
- Add menu to call parameter optimizer. 
- If parameter optimizer is called, whether from terminal or app, it produces a `{stem}_param_optimized.json` and it will be loaded if the opitimizer is called from the app.


## TODO for more after next turn

- Execute processing and grain-detecting phase automatically if parameter json file is loaded.
- Update documents including japanese version for recent app status.
- Do not overlay grain detection area and marker area onto the original image view. The original image should show solely the **original**.

