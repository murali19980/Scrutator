# Contributing to Scrutator Academic

Thank you for your interest in contributing to Scrutator Academic! We welcome contributions of all kinds, including bug fixes, new features, documentation improvements, and bug reports.

## Code of Conduct

Please be respectful and professional in all your interactions with the community.

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/murali19980/Scrutator.git
   cd Scrutator
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Setup environment variables:
   ```bash
   cp .env.example .env
   # Edit .env and fill in your API keys
   ```

## Running the Web UI

To start the Gradio Web UI locally:
```bash
python api/web_ui.py
```

## Running Tests

We use `pytest` for testing. Please ensure all tests pass before submitting a pull request:
```bash
pytest tests/ -v
```

## Code Style

- Follow PEP 8 guidelines.
- Keep functions modular and well-documented.
- Write tests for any new modules or components.
