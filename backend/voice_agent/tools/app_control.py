import os
import subprocess
from typing import Any, Dict
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

    async def run(self, **kwargs) -> Dict[str, Any]:
        app_name = kwargs.get('application_name')
        if not app_name:
            return {'error': 'Missing application_name'}

        # Desktop control is opt-in. Never pass user-controlled text through a
        # shell and never launch an arbitrary executable by default.
        allowed = {
            item.strip().lower(): item.strip()
            for item in os.getenv("MYGPT_ALLOWED_APPS", "").split(",")
            if item.strip()
        }
        target = allowed.get(str(app_name).strip().lower())
        if target is None:
            return {'error': 'This application is not allow-listed.'}

        try:
            subprocess.Popen([target], shell=False)
            return {'result': f'Launched {target}'}
        except Exception:
            return {'error': 'Unable to launch the configured application.'}

ToolRegistry.register(AppControlTool())
