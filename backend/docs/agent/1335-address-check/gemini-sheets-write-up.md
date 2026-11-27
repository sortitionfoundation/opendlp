Done a quick exploration with Gemini in an "our working version" spreadsheet, to explore the formula. The write up (with made up address strings):

## Overview of the Logic Leading to `address_check` (Column DE)

The `address_check` column validates whether a respondent's self-reported house number or flat identifier exists in the official delivery points registered for that postcode on the **`UK Delivery Addresses`** tab.
Only two raw fields from columns **A–AG** are used in this process:

- **Column L:** `address_line_1`
- **Column O:** `postcode`

---

Step-by-Step Column Pipeline

1. **`AH` (`address_line_1`)**:
    1. Mirrors Column L directly from the raw respondent input.
2. **`AI` (`up to first space`)**:
    1. Extracts the first token of the address string:
`REGEXEXTRACT(AH, "[^ ]+")`
    2. _Examples:_ `"42b High Street"` $\rightarrow$ `"42b"`; `"Flat 4, Rosewood House"` $\rightarrow$ `"Flat"`.
3. **`AJ` (`deal with flats, add #`)**:
    1. Formats the building or flat tag:
        1. If the first token starts with `FLAT`, it extracts `FLAT <identifier>`: `REGEXEXTRACT(UPPER(AH), "FLAT [^ ]+")` (e.g., `"FLAT 4"`).
        2. Otherwise, it prepends `#` to the first token: `"#" & AI` (e.g., `"#42B"`).
4. **`DD` (`postcode`)**:
    1. Standardizes the postcode from Column O into standard UK spacing (outward code, space, 3-character inward code, e.g., `"SW1A 1AA"`, `"OX1 2JD"`).
5. **`DF:DK` (`all address at postcode 1..6`)**:
    1. Looks up the standardized postcode in `'UK Delivery Addresses'!A:A` and retrieves all registered address lines from `'UK Delivery Addresses'!B:B`.
    2. Each retrieved address is prefixed with `#` and given a trailing space (e.g., `"#42A HIGH STREET "`, `"#42B HIGH STREET "`).
6. **`DE` (`address_check`)**:
    1. Evaluates the formula:`=IF(REGEXMATCH(CONCATENATE(DF:DK), UPPER(AJ) & " "), "ok", "CHECK")`
**Formula result:**
    2. It checks whether the target identifier (e.g., `"#42B "` or `"FLAT 4 "`) occurs within any of the official addresses registered for that postcode.
    3. **Why some rows show `BAD`:** The formula automatically outputs `"ok"` (match found) or `"CHECK"` (no match found). Rows flagged with `"CHECK"` are manually audited; if confirmed to be an invalid, non-existent, or mismatched address, they are overwritten with `"BAD"` (or manually approved as `"ok"` if valid but unusually phrased).

---

Fictional Examples| Example | Address Line 1 (L) | Postcode (O) | Formatted Target (AJ) | Registered Delivery Addresses (DF:DK) | Result (DE) | Explanation |
| --- | --- | --- | --- | --- | --- | --- |
| **1** | `42b High Street` | `AB12 3CD` | `"#42b"` | `#40 HIGH STREET`, `#42B HIGH STREET` | **`ok`** | `"#42B "` matches the registered address `#42B HIGH STREET`. |
| **2** | `Flat 2, Oak Mansions` | `EF45 6GH` | `"FLAT 2"` | `#FLAT 1`, `#FLAT 2`, `#FLAT 3` | **`ok`** | `"FLAT 2 "` matches the registered address `#FLAT 2`. |
| **3** | `Meadow View Cottage` | `IJ78 9KL` | `"#Meadow"` | `#14 CHURCH ROAD` | **`BAD`** | Named property not found in standard numbered delivery points. Flagged `CHECK`, manually confirmed **`BAD`**. |
| **4** | `15A Victoria Road` | `MN01 2OP` | `"#15a"` | `#15B VICTORIA ROAD`, `#15C VICTORIA ROAD` | **`BAD`** | Official records list `15B` and `15C`, but no `15A`. Flagged `CHECK`, manually marked **`BAD`**. |
| **5** | `Room 12, West Hall` | `QR34 5ST` | `"#Room"` | _(None listed)_ | **`BAD`** | Campus building with no matching delivery point recorded. Flagged `CHECK`, marked **`BAD`**. |

---

Equivalent Python Code

``` python
import re

def normalize_postcode(pc: str | None) -> str:
    """Standardizes UK postcode spacing (equivalent to columns AK & DD)."""
    if not pc:
        return ""
    clean = re.sub(r"\s+", "", str(pc)).upper()
    if 5 <= len(clean) <= 8:
        # Standard UK format: Inward code is always the last 3 characters
        return f"{clean[:-3]} {clean[-3:]}"
    return clean

def extract_address_tag(address_line_1: str | None) -> str:
    """Extracts house or flat tag (equivalent to columns AI & AJ).

    - If starts with 'FLAT', extracts 'FLAT <number/id>'.
    - Otherwise, extracts '#<first_token>'.
    """
    if not address_line_1:
        return ""

    addr = str(address_line_1).strip()
    tokens = addr.split()
    if not tokens:
        return ""

    first_token = tokens[0]

    # Check if first token contains "FLAT" (case-insensitive)
    if "FLAT" in first_token.upper():
        match = re.search(r"\bFLAT\s+[^ ,]+", addr, re.IGNORECASE)
        if match:
            return match.group(0).upper()
        return f"FLAT {tokens[1]}".upper() if len(tokens) > 1 else "FLAT"

    # Prepend '#' to the first token (house number, lettered number, or building name)
    return f"#{first_token}".upper()

def generate_address_check(
    row: dict[str, str], delivery_addresses_lookup: dict[str, list[str]]
) -> str:
    """Generates the 'address_check' value (column DE).

    :param row: Dictionary containing row keys from columns A-AG,
                specifically 'address_line_1' and 'postcode'.
    :param delivery_addresses_lookup: Mapping from normalized postcode to
                a list of registered delivery address strings.
    :return: 'ok' if matched, otherwise 'CHECK'.
    """
    address_line_1 = row.get("address_line_1", "")
    raw_postcode = row.get("postcode", "")

    postcode = normalize_postcode(raw_postcode)
    target_tag = extract_address_tag(address_line_1)

    if not target_tag or not postcode:
        return "CHECK"

    # Retrieve all registered addresses for this postcode (columns DF:DK)
    postcode_addresses = delivery_addresses_lookup.get(postcode, [])

    # Prepend '#' and append a space to each delivery address (as done in DF:DK)
    formatted_addresses = [
        "#" + addr.strip().upper() + " " for addr in postcode_addresses
    ]
    concatenated_addresses = "".join(formatted_addresses)

    # Check whether UPPER(AJ) + " " is present in CONCATENATE(DF:DK)
    pattern = re.escape(target_tag) + r"\s"
    if re.search(pattern, concatenated_addresses):
        return "ok"

    return "CHECK"  # Unmatched rows evaluate to 'CHECK' (and are manually verified/marked 'BAD')

# --- Demonstration with Fictional Data ---
if __name__ == "__main__":
    fictional_delivery_db = {
        "AB12 3CD": ["40 HIGH STREET", "42B HIGH STREET"],
        "EF45 6GH": ["FLAT 1, OAK MANSIONS", "FLAT 2, OAK MANSIONS"],
        "IJ78 9KL": ["14 CHURCH ROAD"],
        "MN01 2OP": ["15B VICTORIA ROAD", "15C VICTORIA ROAD"],
        "QR34 5ST": [],
    }

    # Example 1: Valid street number match -> 'ok'
    row_1 = {"address_line_1": "42b High Street", "postcode": "AB12 3CD"}
    print("Example 1 result:", generate_address_check(row_1, fictional_delivery_db))
    # Output: ok

    # Example 2: Valid flat match -> 'ok'
    row_2 = {"address_line_1": "Flat 2, Oak Mansions", "postcode": "EF45 6GH"}
    print("Example 2 result:", generate_address_check(row_2, fictional_delivery_db))
    # Output: ok

    # Example 3: Unmatched house name -> 'CHECK' (flagged for review / marked 'BAD')
    row_3 = {"address_line_1": "Meadow View Cottage", "postcode": "IJ78 9KL"}
    print("Example 3 result:", generate_address_check(row_3, fictional_delivery_db))
    # Output: CHECK

    # Example 4: Non-existent house number -> 'CHECK' (flagged for review / marked 'BAD')
    row_4 = {"address_line_1": "15A Victoria Road", "postcode": "MN01 2OP"}
    print("Example 4 result:", generate_address_check(row_4, fictional_delivery_db))
    # Output: CHECK
```
