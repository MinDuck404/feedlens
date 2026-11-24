"""Load packaged JavaScript templates at module import time."""
from importlib.resources import files


def load_script(package: str, name: str, selectors: dict[str, str]) -> str:
    script = files(package).joinpath("js", name).read_text(encoding="utf-8")
    for placeholder, selector in selectors.items():
        script = script.replace(placeholder, selector)
    return script
