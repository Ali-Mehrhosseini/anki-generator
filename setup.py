from setuptools import setup, find_packages

setup(
    name="anki-generator",
    version="1.0.0",
    py_modules=["cli", "main", "practice_mode", "production_backfill"],
    install_requires=[
        "requests",
        "python-dotenv",
        "google-genai",
        "boto3",
        "flask",
        "gunicorn==21.2.0",
        "Pillow",
        "arabic-reshaper",
        "python-bidi",
    ],
    entry_points={
        "console_scripts": [
            "anki=cli:main",
        ],
    },
)
