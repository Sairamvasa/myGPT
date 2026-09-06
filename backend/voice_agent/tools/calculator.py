import math
from typing import Dict
from voice_agent.tools.base import Tool, ToolRegistry
from voice_agent.security.permissions import PermissionLevel

class CalculatorTool(Tool):
    def __init__(self):
        super().__init__(
            name='calculator',
            description='Evaluate simple arithmetic expressions safely.',
            permission=PermissionLevel.LOW,
            parameters={'expression': {'type': 'string', 'description': 'Arithmetic expression to evaluate'}}
        )

    async def run(self, **kwargs) -> Dict[str, any]:
        expr = kwargs.get('expression')
        if expr is None:
            return {'error': 'Missing expression'}
        allowed_names = {k: getattr(math, k) for k in dir(math) if not k.startswith('_')}
        allowed_names.update({'abs': abs, 'round': round})
        try:
            result = eval(expr, {'__builtins__': {}}, allowed_names)
            return {'result': result}
        except Exception as e:
            return {'error': str(e)}

ToolRegistry.register(CalculatorTool())
