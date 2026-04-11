- image processing button is doubled at top and bottom of dialog. remove bottom one.
- auto detect scale ratio does not work with scale bar region .
- The viewer window should show 3 state, original/processed/grain overlay.


---

## Not for app development

Pls use original GSAT functions to find good params for images in @params.json. 
The good param combination which maximize grain detection for that image. 
Do not forget that part of this image is grain area. 
Write back the best result into new json file.