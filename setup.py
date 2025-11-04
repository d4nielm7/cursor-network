from setuptools import setup, find_packages

setup(
    name="linkedin-network-mcp",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastmcp",
        "fastapi",
        "uvicorn",
        "asyncpg",
        "python-dotenv",
        # add other dependencies here
    ],
    entry_points={
        "console_scripts": [
            "linkedin-network-mcp=linkedin_network_mcp.main:main",
        ]
    }
)
