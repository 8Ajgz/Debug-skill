"""Setup configuration for verification-debugging-suite"""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="verification-debugging-suite",
    version="1.0.0",
    author="Anthropic",
    description="Unified verification and debugging orchestrator",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/anthropics/verification-debugging-suite",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "z3-solver>=4.12.2",
        "hypothesis>=6.0",
        "pytest>=7.0",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Development Status :: 5 - Production/Stable",
    ],
    keywords="verification debugging testing formal-methods z3 code-analysis",
)
