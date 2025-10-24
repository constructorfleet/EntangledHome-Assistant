# EntangledHome - Assistant

Development scaffold for the EntangledHome Home Assistant custom component.

## Development

1. Run the environment bootstrap script:
   ```bash
   scripts/setup_env.sh
   ```
2. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```
3. Run linters:
   ```bash
   ruff check
   ```
4. Execute the test suite:
   ```bash
   pytest
   ```

The development dependencies install pytest, pytest-homeassistant-custom-component, Ruff, and the FastAPI stack (FastAPI, Uvicorn, HTTPX) for adapter service work.
