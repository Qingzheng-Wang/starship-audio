#!/usr/bin/env python3
"""
Setup script for Starship audio download system
"""

from setuptools import setup, find_packages

setup(
    name="starship",
    version="2.0.0",
    description="Starship - Scalable audio/video download system for GCP",
    author="CMU LTI",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.7",
    install_requires=[
        "pandas>=1.3.0",
        "pyarrow>=6.0.0",
        "yt-dlp>=2023.0.0",
        "absl-py>=1.0.0",
        "requests>=2.26.0",
        "google-cloud-storage>=2.0.0",
        "google-api-python-client>=2.0.0",
        "tqdm>=4.62.0",
        "flask>=2.0.0",
        "APScheduler>=3.8.0",
    ],
    entry_points={
        "console_scripts": [
            "starship-audio=starship.app_audio:cli",
            "starship-video=starship.app:cli",
        ],
    },
)

