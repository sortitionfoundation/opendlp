# ABOUTME: Prints a slice of a frozen `gettext-auto scan` JSON snapshot,
# ABOUTME: one compact JSON object per line, for feeding entries to a model.
import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(f"usage: {sys.argv[0]} <scan.json> <start> <count>")
    snapshot, start, count = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])

    entries = json.loads(snapshot.read_text())["entries"]
    for entry in entries[start : start + count]:
        record = {"id": entry["id"], "msgid": entry["msgid"]}
        if entry["msgctxt"]:
            record["ctxt"] = entry["msgctxt"]
        if entry["msgid_plural"]:
            record["plural"] = entry["msgid_plural"]
        if entry["extracted_comments"]:
            record["cmt"] = entry["extracted_comments"]
        if entry["status"] == "fuzzy":
            record["old"] = entry["current_msgstr"]
        record["ref"] = entry["references"][0] if entry["references"] else ""
        print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
