# Data provenance

The code is MIT-licensed. No third-party geographic boundary or 12306 station-name dataset is redistributed with the repository.

- `prepare_map.py` obtains geoBoundaries CHN ADM1 gbOpen simplified geometry from geoBoundaries revision `9469f09`. The API metadata at `https://www.geoboundaries.org/api/current/gbOpen/CHN/ADM1/` states `boundaryLicense: Public Domain` and `boundarySource: geoBoundaries, Wikimedia Commons`. Its SHA-256 is pinned in the script. The root downloaded file is ignored by Git; the distributable skill package explicitly includes the checksum-verified Public Domain copy and generated HTML embeds it. Geographic representation and public map display may require jurisdiction-specific review.
- `lib12306.py` downloads `station_name.js` from `https://kyfw.12306.cn/otn/resources/js/framework/station_name.js` at runtime into ignored `.cache/`. No copy is shipped.
- Approximate coordinate values in `coords.py` are maintained as project data; do not interpret them as precise platform coordinates or actual track alignments.

The artwork and copy are original homecoming motifs. The project does not include or quote Yu Guangzhong's poem 《乡愁》.
