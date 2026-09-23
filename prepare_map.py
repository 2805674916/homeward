"""Install the public-domain geoBoundaries CHN ADM1 geometry for offline reports."""
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.request import getproxies

ROOT = Path(__file__).resolve().parent
OID = "bc4afc7eacf4351ae5b3ae7a612327987ce1123cb5deb8574fb49107091c6623"
SIZE = 263343
BATCH = "https://github.com/wmgeolab/geoBoundaries.git/info/lfs/objects/batch"
OUTPUT = ROOT / "assets" / "china_adm1.geojson"


def curl(*args):
    proxy = getproxies().get("https")
    command = ["curl", "-fsSL", "--max-time", "45"]
    if proxy:
        command += ["--proxy", proxy.replace("socks5://", "socks5h://", 1)]
    result = subprocess.run([*command, *args], capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return result.stdout


def main():
    request = json.dumps({"operation": "download", "transfers": ["basic"],
                          "objects": [{"oid": OID, "size": SIZE}]})
    response = json.loads(curl("-H", "Accept: application/vnd.git-lfs+json",
                               "-H", "Content-Type: application/vnd.git-lfs+json",
                               "--data", request, BATCH))
    url = response["objects"][0]["actions"]["download"]["href"]
    body = curl(url)
    if hashlib.sha256(body).hexdigest() != OID:
        raise RuntimeError("地图文件校验失败，未写入。请检查下载来源。")
    data = json.loads(body)
    if data.get("type") != "FeatureCollection" or not data.get("features"):
        raise RuntimeError("地图文件不是有效的 GeoJSON。")
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_bytes(body)
    print("已安装 geoBoundaries CHN ADM1 省界（Public Domain）：", OUTPUT)


if __name__ == "__main__":
    main()
