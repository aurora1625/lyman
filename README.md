Python fMRI Analysis Ecosystem
==============================

This repository contains a set of Python-based code for analyzing
functional MRI data using FSL and Freesurfer tools and Nipype.

Dependencies
------------

### External

- Freesurfer

- FSL

### Python


- Core scientific Python environment (EPD)

- [nipype](https://github.com/nipy/nipype)

- [nipy](https://github.com/nipy/nipy)

- [nibabel](https://github.com/nipy/nibabel)

- [statsmodels](https://github.com/statsmodels/statsmodels)

- [rst2pdf](https://code.google.com/p/rst2pdf/)

- Docutils >= 0.9 (rst2pdf does not work with 0.8)

- My utility packages: [moss](https://github.com/mwaskom/moss) and [seaborn](https://github.com/mwaskom/seaborn)

Some of the core dependencies require developmet code in Github master

Basic Workflow
--------------

- All stages of processing assume that your anatomical data have been
  processed in Freesurfer (recon-all)

- run_warp.py: perform anatomical normalization

- run_fmri.py: perform subject-level functional analyses

- run_group.py: perform basic group level mixed effects analyses

License
-------

Simplified BSD

Notes
-----

Although all are welcome to use this code in their own work, it is not officially
"released" in any capacity and many elements of it are under active development and
subject to change at any time.

Please submit bug reports/feature ideas through the Github issues framework.

