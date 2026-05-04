import os
import sys
import importlib.util
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tool import Tool, ToolResult


class SelfExtendTool(Tool):
    is_read_only = False
    is_concurrency_safe = False
    is_destructive = False

    def __init__(self, agent=None):
        self.agent = agent

    @property
    def name(self): return "self_extend"

    @property
    def description(self):
        return (
            "Create a new tool at runtime by writing a Python class that extends Tool. "
            "The tool is saved to .cipher/runtime_tools/ and immediately registered. "
            "Use this to add capabilities not currently available."
        )

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Snake_case name for the new tool file"},
                "description": {"type": "string", "description": "Human-readable description of what this tool does"},
                "code": {"type": "string", "description": "Complete Python class extending Tool"},
            },
            "required": ["tool_name", "description", "code"],
        }

    def call(self, input: dict) -> ToolResult:
        tool_name = input["tool_name"].strip().replace(" ", "_")
        code = input["code"]

        if self.agent is None:
            return ToolResult(output="SelfExtendTool has no agent reference — cannot register.", error=True)

        cwd = getattr(self.agent, "cwd", os.getcwd())
        runtime_dir = os.path.join(cwd, ".cipher", "runtime_tools")
        os.makedirs(runtime_dir, exist_ok=True)

        filepath = os.path.join(runtime_dir, f"{tool_name}.py")

        # Add import boilerplate if not present
        if "from tool import" not in code and "import Tool" not in code:
            preamble = "import os, sys\nsys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))\nfrom tool import Tool, ToolResult\n\n"
            code = preamble + code

        try:
            with open(filepath, "w") as f:
                f.write(code)
        except Exception as e:
            return ToolResult(output=f"Failed to write tool file: {e}", error=True)

        module_name = f"cipher_runtime_{tool_name}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                return ToolResult(output="Failed to create module spec.", error=True)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            return ToolResult(output=f"Failed to import tool: {e}", error=True)

        new_tools = []
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Tool) and obj is not Tool:
                try:
                    instance = obj()
                    self.agent.tools.append(instance)
                    self.agent.tool_map[instance.name] = instance
                    # Update API tools list
                    self.agent._api_tools = [t.to_api_dict() for t in self.agent.tools]
                    new_tools.append(instance.name)
                except Exception as e:
                    return ToolResult(output=f"Failed to instantiate {obj.__name__}: {e}", error=True)

        if not new_tools:
            return ToolResult(output="No Tool subclasses found in provided code.", error=True)

        return ToolResult(
            output=f"Registered {len(new_tools)} new tool(s): {', '.join(new_tools)}\nSaved to: {filepath}"
        )
