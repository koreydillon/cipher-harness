import os
import sys
import importlib.util
import inspect

from tool import Tool


def load_plugins(plugin_dir: str) -> list[Tool]:
    plugin_dir = os.path.expanduser(plugin_dir)
    os.makedirs(plugin_dir, exist_ok=True)

    loaded = []
    if not os.path.isdir(plugin_dir):
        return loaded

    for filename in sorted(os.listdir(plugin_dir)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        filepath = os.path.join(plugin_dir, filename)
        module_name = f"cipher_plugin_{filename[:-3]}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, Tool) and obj is not Tool:
                    instance = obj()
                    loaded.append(instance)
                    print(f"[cipher] loaded plugin: {instance.name}")
        except Exception as e:
            print(f"[cipher] warning: failed to load plugin {filename}: {e}")

    return loaded
