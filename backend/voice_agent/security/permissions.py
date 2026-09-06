from enum import Enum, auto

class PermissionLevel(Enum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()

def requires_confirmation(level: PermissionLevel) -> bool:
    return level in {PermissionLevel.MEDIUM, PermissionLevel.HIGH}
