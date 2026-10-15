#!/usr/bin/env python3
"""Download ALFWorld TextWorld data only (skip visual MRCNN detectors)."""

import os
import shutil
import sys
import zipfile

import requests
from tqdm import tqdm

JSON_URL = "https://github.com/alfworld/alfworld/releases/download/0.2.2/json_2.1.1_json.zip"
PDDL_URL = "https://github.com/alfworld/alfworld/releases/download/0.2.2/json_2.1.1_pddl.zip"
TW_PDDL_URL = "https://github.com/alfworld/alfworld/releases/download/0.4.0/json_2.1.2_tw-pddl.zip"

data_dir = os.environ.get("ALFWORLD_DATA", "/root/.cache/alfworld")
os.makedirs(data_dir, exist_ok=True)


def fetch(url: str, dst: str) -> str:
    name = url.rsplit("/", 1)[-1]
    path = os.path.join(dst, name)
    if os.path.isfile(path) and os.path.getsize(path) > 1000:
        print("skip existing", path)
        return path
    tmp = path + ".part"
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        with open(tmp, "wb") as f, tqdm(unit="B", unit_scale=True, total=total, desc=name) as pbar:
            for chunk in r.iter_content(1024 * 256):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
    shutil.move(tmp, path)
    return path


def unzip(path: str, dst: str) -> None:
    with zipfile.ZipFile(path) as z:
        z.extractall(dst)
    os.remove(path)


for url in (JSON_URL, PDDL_URL, TW_PDDL_URL):
    p = fetch(url, data_dir)
    unzip(p, data_dir)
    print("extracted", url.rsplit("/", 1)[-1])

# logic files from package
try:
    from alfworld.info import ALFRED_PDDL_PATH, ALFRED_TWL2_PATH

    logic = os.path.join(data_dir, "logic")
    os.makedirs(logic, exist_ok=True)
    shutil.copy(ALFRED_PDDL_PATH, os.path.join(logic, "alfred.pddl"))
    shutil.copy(ALFRED_TWL2_PATH, os.path.join(logic, "alfred.twl2"))
    print("logic copied")
except Exception as e:
    print("logic copy skipped:", e)

print("DATA_DIR", data_dir)
print("LIST", os.listdir(data_dir)[:20])
