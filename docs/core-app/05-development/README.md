# Core App Development

Guide for extending and developing PixEagle core components.

## Adding API Endpoints

### 1. Define Endpoint in FastAPIHandler

```python
# src/classes/fastapi_handler.py

def define_routes(self):
    # ... existing routes ...

    # Add new endpoint
    self.app.get("/api/my-feature/data")(self.get_my_feature_data)
    self.app.post("/api/my-feature/action")(self.my_feature_action)
```

### 2. Implement Handler Methods

```python
async def get_my_feature_data(self):
    """Get my feature data."""
    try:
        data = self.app_controller.get_my_feature_data()
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def my_feature_action(self, request: Request):
    """Perform my feature action."""
    try:
        body = await request.json()
        result = await self.app_controller.do_my_feature_action(body)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 3. Add Request Models (Optional)

```python
from pydantic import BaseModel

class MyFeatureRequest(BaseModel):
    param1: str
    param2: int = 10
```

## Adding Configuration Parameters

### 1. Add to Schema

```yaml
# configs/config_schema.yaml

sections:
  my_feature:
    display_name: "My Feature"
    category: other
    parameters:
      enabled:
        type: boolean
        description: "Enable my feature"
        default: false

      threshold:
        type: float
        description: "Feature threshold"
        default: 0.5
        min: 0.0
        max: 1.0
```

### 2. Add Defaults

```yaml
# configs/config_default.yaml

my_feature:
  enabled: false
  threshold: 0.5
```

### 3. Use in Code

```python
from classes.config_service import ConfigService

config = ConfigService.get_instance()

if config.get_parameter('my_feature', 'enabled'):
    threshold = config.get_parameter('my_feature', 'threshold')
    # Use threshold
```

## Adding a New Component

### 1. Create Component Class

```python
# src/classes/my_component.py

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class MyComponent:
    """My new component description."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._initialized = False
        logger.info("MyComponent initialized")

    def start(self):
        """Start the component."""
        self._initialized = True

    def stop(self):
        """Stop the component."""
        self._initialized = False

    def process(self, data: Any) -> Any:
        """Process data."""
        if not self._initialized:
            raise RuntimeError("Component not initialized")
        # Process data
        return result
```

### 2. Integrate with AppController

```python
# src/classes/app_controller.py

class AppController:
    def __init__(self):
        # ... existing initialization ...

        # Initialize new component
        from classes.my_component import MyComponent
        self.my_component = MyComponent(config)

    async def update_loop(self, frame):
        # ... existing code ...

        # Use new component
        if self.my_component.is_enabled():
            result = self.my_component.process(data)
```

### 3. Add Tests

```python
# tests/unit/core_app/test_my_component.py

import pytest
from classes.my_component import MyComponent

class TestMyComponent:
    def test_initialization(self):
        component = MyComponent({})
        assert not component._initialized

    def test_start_stop(self):
        component = MyComponent({})
        component.start()
        assert component._initialized
        component.stop()
        assert not component._initialized
```

## Extending Logging

### Using LoggingManager

```python
from classes.logging_manager import logging_manager
import logging

logger = logging.getLogger(__name__)

# Connection status (with spam reduction)
logging_manager.log_connection_status(
    logger,
    "MyService",
    is_connected=True,
    details="Connected to server"
)

# Polling activity (periodic summaries)
logging_manager.log_polling_activity(
    logger,
    "MyService",
    success=True
)

# Operations (spam reduced)
logging_manager.log_operation(
    logger,
    "MY_OPERATION",
    level="info",
    details="Processing complete"
)
```

## Testing Guidelines

### Unit Tests

```python
# tests/unit/core_app/test_my_component.py

import pytest
from unittest.mock import MagicMock, patch

class TestMyComponent:
    @pytest.fixture
    def component(self):
        return MyComponent({'enabled': True})

    def test_initialization(self, component):
        assert component.config['enabled'] is True

    def test_process_not_initialized(self, component):
        with pytest.raises(RuntimeError):
            component.process(data)

    @patch('classes.my_component.external_service')
    def test_process_with_mock(self, mock_service, component):
        mock_service.call.return_value = "result"
        component.start()
        result = component.process(data)
        assert result == "result"
```

### Integration Tests

```python
# tests/integration/core_app/test_my_feature.py

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_my_feature_endpoint():
    async with AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/api/my-feature/data")
        assert response.status_code == 200
```

## Code Style

### Imports

```python
# Standard library
import logging
import time
from typing import Dict, List, Optional

# Third-party
import numpy as np
from fastapi import HTTPException

# Local
from classes.parameters import Parameters
from classes.config_service import ConfigService
```

### Docstrings

```python
def my_function(param1: str, param2: int = 10) -> Dict[str, Any]:
    """
    Brief description of function.

    Args:
        param1: Description of param1
        param2: Description of param2 (default: 10)

    Returns:
        Description of return value

    Raises:
        ValueError: When param1 is empty
    """
```

### Error Handling

```python
try:
    result = risky_operation()
except SpecificError as e:
    logger.error(f"Specific error: {e}")
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    logger.exception(f"Unexpected error: {e}")
    raise HTTPException(status_code=500, detail="Internal error")
```

## Related Documentation

- [Architecture](../01-architecture/README.md)
- [API Reference](../03-api/README.md)
- [Configuration](../04-configuration/README.md)
