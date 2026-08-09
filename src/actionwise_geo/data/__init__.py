"""Readers for the seven source datasets. Pure I/O plus CRS normalisation.

Every public reader here returns a frame already in EPSG:3059 and records one
audit row. No index logic lives in this package.
"""
