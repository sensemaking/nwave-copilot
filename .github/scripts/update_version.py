import os
import re
import json
from pathlib import Path

def update_version():
    run_number = os.environ.get("GITHUB_RUN_NUMBER")
    if not run_number:
        print("GITHUB_RUN_NUMBER not set, skipping version update")
        return

    # Update pyproject.toml
    pyproject_path = Path("pyproject.toml")
    content = pyproject_path.read_text(encoding="utf-8")
    
    # Extract current major version
    match = re.search(r'version = "(\d+)\.(\d+)\.(\d+)"', content)
    if not match:
        print("Could not find version in pyproject.toml")
        return
        
    major = match.group(1)
    # Format: MAJOR.RUN_NUMBER.0
    new_version = f"{major}.{run_number}.0"
    
    print(f"Updating version to {new_version}")
    
    new_content = re.sub(r'version = ".*"', f'version = "{new_version}"', content)
    pyproject_path.write_text(new_content, encoding="utf-8")
    
    # Update marketplace.json
    marketplace_path = Path(".github/plugin/marketplace.json")
    if marketplace_path.exists():
        data = json.loads(marketplace_path.read_text(encoding="utf-8"))
        data["metadata"]["version"] = new_version
        # Update specific plugin version too
        for plugin in data.get("plugins", []):
            if plugin["name"] == "nwave":
                plugin["version"] = new_version
        
        marketplace_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

if __name__ == "__main__":
    update_version()
