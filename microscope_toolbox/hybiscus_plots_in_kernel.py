"""A photometry's hybiscus plot, drawn in a kernel on the Jupyter server.

This module's source is sent to the kernel, which has the database access and
terray packages this app doesn't, so it only imports them inside the function.
Ported from AlignQcFigures.hyb_plot_bw in terray_notebooks'
utils/panel_auto_qc.py (48c8e75), which the notebook draws when a row of its
runs table is selected.
"""

import io


def hybiscus_plot_png(phot_id: int) -> bytes:
    import matplotlib.pyplot as plt
    import numpy as np
    from terray_datajoint.db import extr
    from terray_notebooks.utils import decode_plotting

    # datajoint 0.13 renders restriction values into SQL with repr(), which under
    # numpy 2 gives `np.int64(5)` instead of `5`, and get_photometry() puts ids it
    # fetched back into queries.
    np.set_printoptions(legacy="1.25")

    photometry = extr.Photometries.for_id(phot_id).get_photometry(bkg_sub="matlab")
    decode_plotting.plot_phot_scatterplot_hist_no_colors(photometry)
    figure = plt.gcf()
    png = io.BytesIO()
    figure.savefig(png, format="png")
    # Otherwise the kernel's inline backend displays the figure a second time.
    plt.close(figure)
    return png.getvalue()
