- Update parameter optimizer to switch GSAT/Felzenszwalb based on current user selection. Parameter space to be searched are quite different on those methods.   


## Analysis document

- Create a sample R quarto analysis document in tests/sample folder. 
- It compares tests/sample/c2600p_asis.png and tests/sample/c2600p_600c60min.png.
- Comparing original images and grain overlayed image side by side.
- Plot the grain distribution csv using bar plot.
- Compare their observed mean, median, standart deviations.
- Fit observed distribution with frequently used distribution (log-normal, weibull, gamma, beta ?) respectively and compare its distribution parameters. 
- Conclude that 600 degC 60 min annealed material produces what kind of grain sizes compared to non processed original C2600P (c2600p_asis).
- C2600P is a brass alloy plate consists of Cu 70% and Zn 30%.

