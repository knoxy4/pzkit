"""JARVIS art lane — drives local ComfyUI (Z-Image Turbo) to generate mod graphics.

Requires a workflow template exported from ComfyUI via "Save (API Format)" at
pzkit/workflows/zimage_default.json. The template's positive-prompt node must be
titled "positive" (set the node title in ComfyUI) so injection is by-title, not
by-id — survives workflow edits.
"""

import json
import os
import time
import urllib.request
from pathlib import Path

COMFY_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8288")
WORKFLOW = Path(__file__).parent.parent / "workflows" / "zimage_default.json"


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{COMFY_URL}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _get(path: str) -> bytes:
    with urllib.request.urlopen(f"{COMFY_URL}{path}", timeout=60) as r:
        return r.read()


def generate(prompt: str, out_path: str, timeout_s: int = 180) -> str:
    """Render `prompt` through the template workflow; save first output image to out_path."""
    wf = json.loads(WORKFLOW.read_text())
    hits = [n for n in wf.values() if n.get("_meta", {}).get("title") == "positive"]
    if not hits:
        raise RuntimeError("workflow template has no node titled 'positive'")
    hits[0]["inputs"]["text"] = prompt

    prompt_id = _post("/prompt", {"prompt": wf})["prompt_id"]
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        hist = json.loads(_get(f"/history/{prompt_id}"))
        if prompt_id in hist:
            outputs = hist[prompt_id]["outputs"]
            for node in outputs.values():
                for img in node.get("images", []):
                    q = f"filename={img['filename']}&subfolder={img.get('subfolder','')}&type={img.get('type','output')}"
                    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(out_path).write_bytes(_get(f"/view?{q}"))
                    return out_path
            raise RuntimeError(f"job {prompt_id} finished with no images")
        time.sleep(2)
    raise TimeoutError(f"ComfyUI job {prompt_id} exceeded {timeout_s}s")
