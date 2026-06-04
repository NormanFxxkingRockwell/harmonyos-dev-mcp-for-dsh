"""Small dependency injection container for service singletons."""

from typing import Any, Callable, Dict, Type, TypeVar

from loguru import logger

T = TypeVar("T")


class Container:
    """Manage lazily-created singleton instances by registered factory."""

    def __init__(self):
        self._instances: Dict[Type, Any] = {}
        self._factories: Dict[Type, Callable] = {}

    def register(self, service_type: Type[T], factory: Callable[[], T]) -> None:
        self._factories[service_type] = factory
        logger.debug(f"registered service factory: {service_type.__name__}")

    def get(self, service_type: Type[T]) -> T:
        if service_type not in self._instances:
            if service_type not in self._factories:
                raise ValueError(f"unregistered service type: {service_type.__name__}")
            self._instances[service_type] = self._factories[service_type]()
            logger.debug(f"created service instance: {service_type.__name__}")
        return self._instances[service_type]

    def reset(self) -> None:
        self._instances.clear()
        self._factories.clear()
        logger.debug("container reset")
