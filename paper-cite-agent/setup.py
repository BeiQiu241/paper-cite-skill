from setuptools import setup, find_packages

setup(
    name="paper-cite-agent",
    version="1.0.0",
    description="论文参考文献检索 Agent：自动分析论文并推荐参考文献",
    packages=find_packages(),
    install_requires=[
        "anthropic>=0.40.0",
        "python-docx>=1.1.0",
        "typer>=0.12.0",
        "pyyaml>=6.0",
        "requests>=2.31.0",
        "lxml>=5.0.0",
    ],
    extras_require={
        "embeddings": ["sentence-transformers>=3.0.0"],
    },
    entry_points={
        "console_scripts": [
            "paper-cite-agent=cli:app",
        ],
    },
    python_requires=">=3.10",
)
