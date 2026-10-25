"""Reusable satellite-analysis kernels.

Submodules are intentionally not imported eagerly: binary evaluation requires
only NumPy, while detection additionally requires scikit-image. Both operate
on in-memory arrays and carry no knowledge of jobs, persistence, HTTP APIs, or
the historical Valencia case study.
"""
