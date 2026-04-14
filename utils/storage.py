import json
from pathlib import Path
from typing import Any


def load_json_array(path: str | Path) -> list[Any]:
	file_path = Path(path)
	if not file_path.exists():
		return []

	try:
		with file_path.open("r", encoding="utf-8") as f:
			data = json.load(f)
		return data if isinstance(data, list) else []
	except Exception:
		return []


def save_json_to_array(item: dict[str, Any], path: str | Path) -> dict[str, Any] | None:
	file_path = Path(path)
	data = load_json_array(file_path)

	new_url = item.get("url") if isinstance(item, dict) else None
	if new_url:
		for existing in data:
			if isinstance(existing, dict) and existing.get("url") == new_url:
				return None

	data.append(item)
	file_path.parent.mkdir(parents=True, exist_ok=True)
	with file_path.open("w", encoding="utf-8") as f:
		json.dump(data, f, ensure_ascii=False, indent=2)

	return item
