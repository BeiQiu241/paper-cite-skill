from setuptools import find_packages, setup


setup(
    name="papercite",
    version="1.0.0",
    description="A simplified codex-only paper citation helper for Word documents.",
    packages=find_packages(),
    install_requires=[
        "python-docx>=1.1.0",
        "pyyaml>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "papercite=cli:main",
        ],
    },
    python_requires=">=3.10",
)
