import json
from pathlib import Path

json_path = Path("config/google_drive.json")
toml_path = Path("secrets.toml")

with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

with open(toml_path, "w", encoding="utf-8") as f:
    f.write("[gcp_service_account]\n\n")

    for k, v in data.items():
        if k == "private_key":
            f.write(f'{k} = """{v}"""\n')
        else:
            f.write(f'{k} = "{v}"\n')

print("Archivo generado:", toml_path.resolve())