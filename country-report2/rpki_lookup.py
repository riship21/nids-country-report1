import io
import lzma
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ipaddress
import pandas as pd
import pycountry
import requests

try:
    import radix
except ImportError:
    raise SystemExit(
        "\nMissing dependency: py-radix\n"
        "Install it with:\n"
        "    pip install py-radix\n"
    )


# ============================================================
# CONFIGURATION
# ============================================================

TOP_N = 15
PAGE_SIZE = 5000
BGP_WINDOW_DAYS = 14
MIN_PEERS_SEEING = 10

# None = automatically use the most recent COMPLETE UTC day.
# For a reproducible historical run, set e.g. "2026-08-20".
ANALYSIS_END_DATE = None

CAIDA_URL = "https://api.asrank.caida.org/v2/graphql"

BGP_URL = (
    "https://stat.ripe.net/data/announced-prefixes/data.json"
)

RPKI_BASE_URL = "https://ftp.ripe.net/rpki"

TRUST_ANCHORS = [
    "afrinic",
    "apnic",
    "arin",
    "lacnic",
    "ripencc",
]

CACHE_DIR = Path("rpki_roa_cache")


# ============================================================
# CAIDA GRAPHQL QUERY
# ============================================================

CAIDA_QUERY = """
query ($first: Int!, $offset: Int!) {
  asns(first: $first, offset: $offset, sort: "rank") {
    totalCount
    pageInfo {
      hasNextPage
    }
    edges {
      node {
        asn
        rank
        asnName
        country {
          iso
        }
      }
    }
  }
}
"""


# ============================================================
# 1. COUNTRY INPUT
# ============================================================

def get_country(country_input):
    try:
        country = pycountry.countries.lookup(country_input)
        return {
            "code": country.alpha_2,
            "name": country.name,
        }
    except LookupError:
        raise ValueError(
            f"Could not recognize country: {country_input}"
        )


# ============================================================
# 2. GET TOP 15 COUNTRY ASNs FROM CAIDA ASRANK
# ============================================================

def get_top_country_asns(country_code, top_n=TOP_N):
    country_code = country_code.upper()

    print()
    print(f"Scanning CAIDA ASRank for {country_code}...")

    results = []
    seen_asns = set()
    offset = 0
    page = 1

    while len(results) < top_n:
        variables = {
            "first": PAGE_SIZE,
            "offset": offset,
        }

        response = requests.post(
            CAIDA_URL,
            json={
                "query": CAIDA_QUERY,
                "variables": variables,
            },
            timeout=60,
        )
        response.raise_for_status()

        payload = response.json()

        if payload.get("errors"):
            raise RuntimeError(
                f"CAIDA GraphQL error: {payload['errors']}"
            )

        data = payload["data"]["asns"]
        edges = data.get("edges", [])

        if not edges:
            break

        for edge in edges:
            node = edge.get("node")
            if not node:
                continue

            country = node.get("country")
            if not country:
                continue

            if country.get("iso") != country_code:
                continue

            asn_value = node.get("asn")
            if asn_value is None:
                continue

            asn = int(asn_value)

            if asn in seen_asns:
                continue

            seen_asns.add(asn)

            results.append(
                {
                    "asn": asn,
                    "name": node.get("asnName") or "Unknown",
                    "asrank": node.get("rank"),
                    "country_rank": len(results) + 1,
                }
            )

            if len(results) >= top_n:
                break

        print(
            f"Page {page} | Found "
            f"{len(results)}/{top_n} ASNs"
        )

        if len(results) >= top_n:
            break

        if not data["pageInfo"]["hasNextPage"]:
            break

        offset += PAGE_SIZE
        page += 1

    return results


# ============================================================
# 3. CHOOSE A COMPLETE 14-DAY BGP WINDOW
# ============================================================

def get_analysis_window(
    days=BGP_WINDOW_DAYS,
    analysis_end_date=ANALYSIS_END_DATE,
):
    if days < 1:
        raise ValueError("BGP_WINDOW_DAYS must be at least 1")

    if analysis_end_date is None:
        # Do not use the partially completed current UTC day.
        final_day = (
            datetime.now(timezone.utc).date()
            - timedelta(days=1)
        )
    else:
        try:
            final_day = datetime.strptime(
                analysis_end_date,
                "%Y-%m-%d",
            ).date()
        except ValueError:
            raise ValueError(
                "ANALYSIS_END_DATE must use YYYY-MM-DD"
            )

    start_day = final_day - timedelta(days=days - 1)
    end_exclusive = final_day + timedelta(days=1)

    starttime = f"{start_day.isoformat()}T00:00"
    endtime = f"{end_exclusive.isoformat()}T00:00"

    # Validate against the daily RPKI snapshot from the final
    # completed day in the BGP observation window.
    rpki_date = final_day.isoformat()

    return starttime, endtime, rpki_date


# ============================================================
# 4. GET BGP PREFIXES FOR ONE ASN
# ============================================================

def get_bgp_prefixes(asn, starttime, endtime):
    print()
    print("=" * 70)
    print(f"Getting BGP prefixes for AS{asn}")
    print(f"Window: {starttime} to {endtime} UTC")
    print("=" * 70)

    params = {
        "resource": f"AS{asn}",
        "starttime": starttime,
        "endtime": endtime,
        "min_peers_seeing": MIN_PEERS_SEEING,
    }

    response = requests.get(
        BGP_URL,
        params=params,
        timeout=60,
    )
    response.raise_for_status()

    payload = response.json()

    if payload.get("status") != "ok":
        raise RuntimeError(
            payload.get("message", "RIPEstat error")
        )

    prefixes = []

    for item in payload.get("data", {}).get("prefixes", []):
        if isinstance(item, dict):
            prefix = item.get("prefix")
        else:
            prefix = item

        if not prefix:
            continue

        try:
            network = ipaddress.ip_network(
                prefix,
                strict=False,
            )
            prefixes.append(str(network))
        except ValueError:
            continue

    prefixes = sorted(set(prefixes))

    ipv4_count = sum(1 for prefix in prefixes if ":" not in prefix)
    ipv6_count = len(prefixes) - ipv4_count

    print(f"BGP prefixes found: {len(prefixes):,}")
    print(f"  IPv4: {ipv4_count:,}")
    print(f"  IPv6: {ipv6_count:,}")

    return prefixes


# ============================================================
# 5. DOWNLOAD RPKI VRPs
# ============================================================

def get_roa_url(trust_anchor, date):
    year = date[:4]
    month = date[5:7]
    day = date[8:10]

    return (
        f"{RPKI_BASE_URL}/"
        f"{trust_anchor}.tal/"
        f"{year}/{month}/{day}/"
        f"roas.csv.xz"
    )


def download_roas(trust_anchor, date):
    CACHE_DIR.mkdir(exist_ok=True)

    cache_file = (
        CACHE_DIR
        / f"{trust_anchor}_{date}_roas.csv.xz"
    )

    if cache_file.exists():
        print(f"Loading {trust_anchor} from cache...")
        compressed = cache_file.read_bytes()
    else:
        url = get_roa_url(trust_anchor, date)
        print(f"Downloading {trust_anchor}...")

        response = requests.get(
            url,
            timeout=120,
        )

        if response.status_code != 200:
            print(
                f"  Failed: HTTP {response.status_code}"
            )
            return None

        compressed = response.content
        cache_file.write_bytes(compressed)

    try:
        decompressed = lzma.decompress(compressed)
    except lzma.LZMAError as error:
        raise RuntimeError(
            f"Could not decompress {trust_anchor}: {error}"
        )

    df = pd.read_csv(
        io.BytesIO(decompressed),
        low_memory=False,
    )

    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    df["trust_anchor"] = trust_anchor

    print(f"  {len(df):,} VRP rows")

    return df


def download_all_roas(date):
    frames = []

    print()
    print("=" * 70)
    print(f"Loading RPKI VRPs for {date}")
    print("=" * 70)

    for trust_anchor in TRUST_ANCHORS:
        df = download_roas(
            trust_anchor,
            date,
        )

        if df is not None:
            frames.append(df)

    if not frames:
        raise RuntimeError(
            "No RPKI data downloaded. "
            f"No usable RPKI archive was found for {date}."
        )

    combined = pd.concat(
        frames,
        ignore_index=True,
    )

    print()
    print(
        f"Raw VRP rows loaded: {len(combined):,}"
    )

    return combined


# ============================================================
# 6. BUILD RADIX TREE
# ============================================================

def parse_asn(value):
    match = re.search(r"(\d+)", str(value))

    if not match:
        return None

    return int(match.group(1))


def parse_max_length(value, network):
    if pd.isna(value):
        return network.prefixlen

    text = str(value).strip()

    if not text or text.lower() == "nan":
        return network.prefixlen

    try:
        max_length = int(float(text))
    except ValueError:
        return None

    if max_length < network.prefixlen:
        return None

    if network.version == 4 and max_length > 32:
        return None

    if network.version == 6 and max_length > 128:
        return None

    return max_length


def build_roa_radix(rpki_df):
    required_columns = [
        "IP Prefix",
        "ASN",
        "Max Length",
        "trust_anchor",
    ]

    for column in required_columns:
        if column not in rpki_df.columns:
            raise RuntimeError(
                f"Missing RPKI column: {column}"
            )

    print()
    print("=" * 70)
    print("Building RPKI radix tree...")
    print("=" * 70)

    tree = radix.Radix()
    seen_vrps = set()

    inserted = 0
    skipped = 0
    duplicates = 0

    columns = rpki_df[
        [
            "IP Prefix",
            "ASN",
            "Max Length",
            "trust_anchor",
        ]
    ]

    for (
        prefix_value,
        asn_value,
        max_length_value,
        trust_anchor,
    ) in columns.itertuples(index=False, name=None):

        try:
            network = ipaddress.ip_network(
                str(prefix_value).strip(),
                strict=False,
            )
        except ValueError:
            skipped += 1
            continue

        asn = parse_asn(asn_value)

        if asn is None:
            skipped += 1
            continue

        max_length = parse_max_length(
            max_length_value,
            network,
        )

        if max_length is None:
            skipped += 1
            continue

        prefix = str(network)

        key = (
            prefix,
            asn,
            max_length,
        )

        if key in seen_vrps:
            duplicates += 1
            continue

        seen_vrps.add(key)

        node = tree.add(prefix)

        if "vrps" not in node.data:
            node.data["vrps"] = []

        node.data["vrps"].append(
            {
                "asn": asn,
                "max_length": max_length,
                "trust_anchor": trust_anchor,
            }
        )

        inserted += 1

    print(f"Unique VRPs inserted: {inserted:,}")
    print(f"Duplicate VRPs skipped: {duplicates:,}")
    print(f"Malformed rows skipped: {skipped:,}")
    print(f"Radix nodes: {len(tree.prefixes()):,}")

    return tree


# ============================================================
# 7. FIND COVERING VRPs
# ============================================================

def get_covering_vrps(prefix, roa_tree):
    """
    Return every VRP whose prefix covers the BGP prefix.

    This preserves the working radix-tree method: starting at
    the BGP prefix, walk toward /0 and perform exact radix
    lookups rather than scanning the full VRP table.
    """

    try:
        network = ipaddress.ip_network(
            prefix,
            strict=False,
        )
    except ValueError:
        return None, []

    vrps = []
    current = network

    while True:
        node = roa_tree.search_exact(str(current))

        if node is not None:
            vrps.extend(node.data.get("vrps", []))

        if current.prefixlen == 0:
            break

        current = current.supernet()

    return network, vrps


# ============================================================
# 8. VALIDATE ONE BGP PREFIX
# ============================================================

def validate_prefix(prefix, origin_asn, roa_tree):
    network, candidates = get_covering_vrps(
        prefix,
        roa_tree,
    )

    if network is None:
        return "UNKNOWN"

    if not candidates:
        return "UNKNOWN"

    prefix_length = network.prefixlen
    matching_asn = []

    # VALID has highest priority.
    for vrp in candidates:
        if vrp["asn"] != origin_asn:
            continue

        matching_asn.append(vrp)

        if prefix_length <= vrp["max_length"]:
            return "VALID"

    # A covering VRP authorizes the ASN, but not this
    # more-specific prefix length.
    if matching_asn:
        return "INVALID LENGTH"

    # Covering VRPs exist, but none authorize the origin ASN.
    return "INVALID ASN"


# ============================================================
# 9. VALIDATE ALL PREFIXES FOR ONE ASN
# ============================================================

def validate_asn(asn, prefixes, roa_tree):
    print()
    print("=" * 70)
    print(f"Validating BGP prefixes for AS{asn}")
    print("=" * 70)

    counts = {
        "VALID": 0,
        "INVALID ASN": 0,
        "INVALID LENGTH": 0,
        "UNKNOWN": 0,
    }

    total = len(prefixes)

    for index, prefix in enumerate(
        prefixes,
        start=1,
    ):
        status = validate_prefix(
            prefix,
            asn,
            roa_tree,
        )

        counts[status] += 1

        if index % 1000 == 0 or index == total:
            percent = (
                index / total * 100
            ) if total else 100

            print(
                f"Validated {index:,}/{total:,} "
                f"({percent:.1f}%)"
            )

    return counts


# ============================================================
# 10. BUILD ONE RESULT ROW
# ============================================================

def build_result_row(
    asn_info,
    prefixes,
    counts,
):
    valid = counts["VALID"]
    invalid_asn = counts["INVALID ASN"]
    invalid_length = counts["INVALID LENGTH"]
    unknown = counts["UNKNOWN"]

    invalid = invalid_asn + invalid_length
    covered = valid + invalid
    total = valid + invalid + unknown

    if total > 0:
        coverage = covered / total * 100
        invalid_percent = invalid / total * 100
    else:
        coverage = 0.0
        invalid_percent = 0.0

    ipv4_count = sum(
        1 for prefix in prefixes
        if ":" not in prefix
    )
    ipv6_count = len(prefixes) - ipv4_count

    return {
        "Country Rank": asn_info["country_rank"],
        "ASN": f"AS{asn_info['asn']}",
        "AS Name": asn_info["name"],
        "ASRank": asn_info["asrank"],
        "IPv4 Prefixes": ipv4_count,
        "IPv6 Prefixes": ipv6_count,
        "BGP Prefixes": len(prefixes),
        "Valid": valid,
        "Invalid ASN": invalid_asn,
        "Invalid Length": invalid_length,
        "Unknown": unknown,
        "RPKI Coverage": f"{coverage:.2f}%",
        "Invalid": f"{invalid_percent:.2f}%",
    }


# ============================================================
# MAIN
# ============================================================

def main():
    country_input = input(
        "Enter a country name or country code: "
    ).strip()

    try:
        country = get_country(country_input)
    except ValueError as error:
        print(error)
        return

    country_code = country["code"]
    country_name = country["name"]

    print()
    print(f"Country: {country_name} ({country_code})")

    # --------------------------------------------------------
    # Get the top 15 ASNs for the selected country.
    # --------------------------------------------------------

    print()
    print(
        f"Getting top {TOP_N} ASNs "
        "from CAIDA ASRank..."
    )

    try:
        asns = get_top_country_asns(
            country_code,
            TOP_N,
        )
    except Exception as error:
        print(f"CAIDA query failed: {error}")
        return

    if not asns:
        print("No ASNs were found for this country.")
        return

    print()
    print("Top ASNs:")

    for item in asns:
        print(
            f"{item['country_rank']:>2}. "
            f"AS{item['asn']:<10} "
            f"{item['name']:<35} "
            f"Global Rank: {item['asrank']}"
        )

    if len(asns) < TOP_N:
        print()
        print(
            f"Note: CAIDA returned only {len(asns)} "
            f"matching ASN(s) for {country_code}."
        )

    # --------------------------------------------------------
    # Use the last 14 complete UTC days.
    # --------------------------------------------------------

    try:
        starttime, endtime, rpki_date = (
            get_analysis_window()
        )
    except ValueError as error:
        print(error)
        return

    print()
    print("Analysis period:")
    print(f"  BGP start: {starttime} UTC")
    print(f"  BGP end:   {endtime} UTC (exclusive)")
    print(f"  RPKI snapshot: {rpki_date}")

    # --------------------------------------------------------
    # Load the RPKI snapshot ONCE and build ONE radix tree.
    # Every ASN below reuses this same tree.
    # --------------------------------------------------------

    try:
        raw_roas = download_all_roas(rpki_date)
        roa_tree = build_roa_radix(raw_roas)
        del raw_roas
    except Exception as error:
        print(f"RPKI loading failed: {error}")
        return

    # --------------------------------------------------------
    # Validate every top-country ASN using local radix lookups.
    # --------------------------------------------------------

    rows = []

    for asn_info in asns:
        asn = asn_info["asn"]

        try:
            prefixes = get_bgp_prefixes(
                asn,
                starttime,
                endtime,
            )

            counts = validate_asn(
                asn,
                prefixes,
                roa_tree,
            )

            rows.append(
                build_result_row(
                    asn_info,
                    prefixes,
                    counts,
                )
            )

        except Exception as error:
            print()
            print(
                f"AS{asn} failed: {error}"
            )

            # Keep the ASN visible in the final table even if
            # its BGP lookup fails.
            rows.append(
                {
                    "Country Rank": asn_info["country_rank"],
                    "ASN": f"AS{asn}",
                    "AS Name": asn_info["name"],
                    "ASRank": asn_info["asrank"],
                    "IPv4 Prefixes": 0,
                    "IPv6 Prefixes": 0,
                    "BGP Prefixes": 0,
                    "Valid": 0,
                    "Invalid ASN": 0,
                    "Invalid Length": 0,
                    "Unknown": 0,
                    "RPKI Coverage": "N/A",
                    "Invalid": "N/A",
                }
            )

    # --------------------------------------------------------
    # Final summary table.
    # --------------------------------------------------------

    table = pd.DataFrame(rows)

    print()
    print("=" * 150)
    print(
        f"RPKI RADIX-TREE SUMMARY - "
        f"{country_name} ({country_code})"
    )
    print("=" * 150)
    print(table.to_string(index=False))

    # --------------------------------------------------------
    # Save CSV.
    # --------------------------------------------------------

    filename = (
        f"{country_code.lower()}_rpki_radix_summary.csv"
    )

    table.to_csv(
        filename,
        index=False,
    )

    print()
    print(f"Saved: {filename}")


if __name__ == "__main__":
    main()