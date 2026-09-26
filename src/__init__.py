"""Yohaku Challenge 5 - AI Approaches for Orbital Anomaly Detection.

A deliberately small, honest prototype. The technical model is a z-score over
SGP4-propagated altitude residuals; the substance of the submission is the
accountability layer wrapped around it.
"""

__all__ = [
    "accountability",
    "config",
    "data_source",
    "detection",
    "orbits",
    "reporting",
]
__version__ = "0.1.0"
