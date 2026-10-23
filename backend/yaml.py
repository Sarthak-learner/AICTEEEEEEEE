"""PyYAML compatibility shim.

Loads real PyYAML module directly from site-packages to avoid recursive import.
"""
import os
import sys
import importlib.util

_real_yaml_path = None
for p in sys.path:
    candidate = os.path.join(p, "yaml", "__init__.py")
    if os.path.exists(candidate) and os.path.abspath(candidate) != os.path.abspath(__file__):
        _real_yaml_path = candidate
        break

if _real_yaml_path:
    spec = importlib.util.spec_from_file_location("_system_pyyaml", _real_yaml_path, submodule_search_locations=[os.path.dirname(_real_yaml_path)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_system_pyyaml"] = mod
    spec.loader.exec_module(mod)
    for k in dir(mod):
        if not k.startswith("__"):
            globals()[k] = getattr(mod, k)



