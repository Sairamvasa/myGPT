import subprocess
from typing import Dict
from voice_agent.tools.base import Tool, ToolRegistry
from voice_agent.security.permissions import PermissionLevel

class AppControlTool(Tool):
    def __init__(self):
        super().__init__(
            name='app_control',
            description='Open a desktop application by name.',
            permission=PermissionLevel.MEDIUM,
            parameters={'application_name': {'type': 'string', 'description': 'Name of the app to launch'}}
        )

    async def run(self, **kwargs) -> Dict[str, any]:
        app_name = kwargs.get('application_name')
        if not app_name:
            return {'error': 'Missing application_name'}
        try:
            subprocess.Popen(app_name, shell=True)
            return {'result': f'Launched {app_name}'}
        except Exception as e:
            return {'error': str(e)}

ToolRegistry.register(AppControlTool())
