#!/usr/bin/env python3
"""
Clean up DorMeME TEI XML files in the research-database.

Fixes applied:
  1. Invalid xml:id NCNames on <msPart> (shelfmark contains illegal chars)
  2. Duplicate xml:id placeholders (FILLINTOO, FILLIN, etc.) within a file
  3. Duplicate xml:id on <foliation> elements (original-foliation, modern-foliation)
  4. D-Mbs secondary <msItem> idno encoding (numbers in subtype instead of text)
  5. Controlled vocabulary: rend spaces→underscores, msPart type casing, locus subtype variants

Usage:
  python clean_tei.py --root /path/to/research-database
"""

import argparse
import re
import sys
from pathlib import Path
from lxml import etree

NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
XML_ID = f"{{{XML_NS}}}id"

REND_REPLACEMENTS = {
    "brown ink": "brown_ink",
    "black ink": "black_ink",
    "red ink": "red_ink",
}

MSPART_TYPE_NORMALISE = {
    "Altus": "altus",
    "Superius": "superius",
    "Tenor": "tenor",
    "Bassus": "bassus",
    "Cantus": "cantus",
    "Discantus": "discantus",
}

LOCUS_SUBTYPE_NORMALISE = {
    "title page": "title_page",
    "upper_end_paper": "upper_end_papers",
}

FOLIATION_IDS = {"original-foliation", "modern-foliation"}
NUMERIC_SUBTYPE = re.compile(r"^\d+$")


def _get_idno_val(elem, subtype):
    """Return stripped text of first matching <idno type="RISM" subtype=subtype>."""
    for idno in elem.findall(f".//{{{NS}}}idno"):
        if idno.get("type") == "RISM" and idno.get("subtype") == subtype:
            return (idno.text or "").strip()
    return ""


def _build_mspart_id(mspart, fallback_stem, index):
    """
    Build a valid NCName xml:id for a <msPart> element.

    Canonical form:
      choirbook / other single-part:  copy_{edition}_{copy}
      partbook with voice subtype:    copy_{edition}_{copy}_{voice}
    Falls back to copy_{stem}_{index} if idno values are missing.
    """
    edition = _get_idno_val(mspart, "edition")
    copy = _get_idno_val(mspart, "copy")

    if edition and copy:
        base = f"copy_{edition}_{copy}"
        voice = mspart.get("subtype", "").strip()
        if voice:
            return f"{base}_{voice}"
        return base

    return f"copy_{fallback_stem}_{index}"


def fix_mspart_ids(tree, stem):
    """Fix 1a, 1b, 1d: replace existing <msPart xml:id> with valid NCNames."""
    msparts = tree.findall(f".//{{{NS}}}msPart")
    seen_ids = {}
    changed = 0

    for i, mspart in enumerate(msparts):
        old_id = mspart.get(XML_ID)
        if old_id is None:
            continue  # don't add xml:id to elements that don't have one

        new_id = _build_mspart_id(mspart, stem, i)

        # Deduplicate: if new_id already used in this file, append index
        if new_id in seen_ids.values():
            new_id = f"{new_id}_{i}"

        seen_ids[i] = new_id

        if old_id != new_id:
            mspart.set(XML_ID, new_id)
            changed += 1

    return changed


def fix_foliation_ids(tree):
    """Fix 1c: remove xml:id from <foliation> elements to eliminate duplicates."""
    changed = 0
    for foliation in tree.findall(f".//{{{NS}}}foliation"):
        fid = foliation.get(XML_ID, "")
        if fid in FOLIATION_IDS:
            del foliation.attrib[XML_ID]
            changed += 1
    return changed


def fix_dmbs_idno(tree):
    """
    Fix 2a: In secondary <msItem> elements, correct idno elements where the
    RISM edition/copy numbers are encoded in the subtype attribute instead of
    element text.

    Pattern:  <idno type="RISM" subtype="993104328"/>
    Correct:  <idno type="RISM" subtype="edition">993104328</idno>

    Within each msItem, process numeric-subtype idno elements in pairs:
      odd-position (0, 2, …) → subtype="edition"
      even-position (1, 3, …) → subtype="copy"
    """
    changed = 0
    for msitem in tree.findall(f".//{{{NS}}}msItem"):
        bad_idnos = [
            el for el in msitem.findall(f"{{{NS}}}idno")
            if el.get("type") == "RISM" and NUMERIC_SUBTYPE.match(el.get("subtype", ""))
        ]
        if not bad_idnos:
            continue
        for j, idno in enumerate(bad_idnos):
            num = idno.get("subtype", "")
            idno.set("subtype", "edition" if j % 2 == 0 else "copy")
            idno.text = num
            changed += 1
    return changed


def fix_rend_values(tree):
    """Fix 3a: normalise rend attribute values (spaces → underscores)."""
    changed = 0
    for el in tree.iter():
        rend = el.get("rend", "")
        if rend in REND_REPLACEMENTS:
            el.set("rend", REND_REPLACEMENTS[rend])
            changed += 1
    return changed


def fix_mspart_type_case(tree):
    """Fix 3b: lowercase msPart type attribute for voice-part values."""
    changed = 0
    for mspart in tree.findall(f".//{{{NS}}}msPart"):
        t = mspart.get("type", "")
        if t in MSPART_TYPE_NORMALISE:
            mspart.set("type", MSPART_TYPE_NORMALISE[t])
            changed += 1
        st = mspart.get("subtype", "")
        if st in MSPART_TYPE_NORMALISE:
            mspart.set("subtype", MSPART_TYPE_NORMALISE[st])
            changed += 1
    return changed


def fix_locus_subtype(tree):
    """Fix 3c: normalise locus subtype values."""
    changed = 0
    for locus in tree.findall(f".//{{{NS}}}locus"):
        st = locus.get("subtype", "")
        if st in LOCUS_SUBTYPE_NORMALISE:
            locus.set("subtype", LOCUS_SUBTYPE_NORMALISE[st])
            changed += 1
    return changed


def process_file(path: Path, root: Path) -> bool:
    """Apply all fixes to one file. Returns True if any change was made."""
    try:
        # recover=True allows parsing files with xml:id NCName violations
        parser = etree.XMLParser(remove_blank_text=False, recover=True)
        tree = etree.parse(str(path), parser)
    except etree.XMLSyntaxError as e:
        print(f"SKIP (parse error): {path.relative_to(root)}: {e}", file=sys.stderr)
        return False

    stem = path.stem.replace(".tei", "")
    total = 0
    total += fix_mspart_ids(tree, stem)
    total += fix_foliation_ids(tree)
    total += fix_dmbs_idno(tree)
    total += fix_rend_values(tree)
    total += fix_mspart_type_case(tree)
    total += fix_locus_subtype(tree)

    if total == 0:
        return False

    tree.write(
        str(path),
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=False,
    )
    return True


def main():
    parser = argparse.ArgumentParser(description="Clean up DorMeME TEI XML files.")
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Root directory of the research-database repository",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    tei_files = sorted(root.rglob("*.tei.xml"))
    print(f"Processing {len(tei_files)} files…", file=sys.stderr)
    changed = 0
    for f in tei_files:
        if process_file(f, root):
            changed += 1
            print(f"  fixed: {f.relative_to(root)}")
    print(f"\nDone. {changed}/{len(tei_files)} files modified.", file=sys.stderr)


if __name__ == "__main__":
    main()
