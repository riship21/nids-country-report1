import io
import lzma
import os
import ipaddress

import requests
import radix
import pandas as pd
import pycountry


# ============================================================
# CONFIGURATION
# ============================================================

TOP_N = 15

# Change this to the country you want
COUNTRY_INPUT = "US"

# RPKI snapshot
RPKI_DATE = "2026-08-20"

# CAIDA ASRank
CAIDA_URL = (
    "https://api.asrank.caida.org/v2/graphql"
)

# RIPEstat announced prefixes
BGP_URL = (
    "https://stat.ripe.net/data/announced-prefixes/data.json"
)

# RIPE RPKI archive
RPKI_BASE_URL = (
    "https://ftp.ripe.net/rpki"
)

# RPKI trust anchors
TRUST_ANCHORS = [
    "afrinic",
    "apnic",
    "arin",
    "lacnic",
    "ripencc"
]

# Local cache directory
RPKI_CACHE_DIR = "rpki_cache"


# ============================================================
# COUNTRY
# ============================================================

def get_country(country_input):

    try:

        country = pycountry.countries.lookup(
            country_input
        )

        return {
            "name": country.name,
            "code": country.alpha_2
        }

    except LookupError:

        return None


# ============================================================
# CAIDA ASRANK
# GET TOP ASes FOR COUNTRY
# ============================================================

def get_top_asns(
    country_code,
    top_n=15
):

    print()
    print("=" * 80)

    print(
        f"Finding top {top_n} ASes "
        f"for {country_code}"
    )

    print("=" * 80)

    query = """
    query GetASNs(
        $first: Int!,
        $offset: Int!
    ) {

        asns(
            first: $first
            offset: $offset
            sort: "rank"
        ) {

            edges {

                node {

                    asn
                    asnName
                    rank

                    country {
                        iso
                    }

                }

            }

        }

    }
    """

    response = requests.post(
        CAIDA_URL,
        json={
            "query": query,
            "variables": {
                "first": 5000,
                "offset": 0
            }
        },
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    if "errors" in data:

        raise RuntimeError(
            data["errors"]
        )

    edges = (
        data["data"]["asns"]["edges"]
    )

    results = []

    for edge in edges:

        item = edge["node"]

        country = (
            item.get("country")
            or {}
        ).get(
            "iso"
        )

        if country != country_code:

            continue

        results.append(
            {
                "asn": int(
                    item["asn"]
                ),

                "name": item.get(
                    "asnName",
                    "Unknown"
                ),

                "rank": item.get(
                    "rank"
                )
            }
        )

        if len(results) >= top_n:

            break

    return results


# ============================================================
# RIPESTAT
# GET BGP PREFIXES FOR ASN
# ============================================================

def get_bgp_prefixes(asn):

    print()
    print(
        f"Getting BGP prefixes "
        f"for AS{asn}..."
    )

    response = requests.get(
        BGP_URL,
        params={
            "resource": f"AS{asn}"
        },
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    if data.get("status") != "ok":

        raise RuntimeError(
            data.get(
                "message",
                "RIPEstat error"
            )
        )

    prefixes = []

    for item in (
        data
        .get("data", {})
        .get("prefixes", [])
    ):

        prefix = item.get(
            "prefix"
        )

        if prefix:

            prefixes.append(
                prefix
            )

    # Remove duplicates
    prefixes = sorted(
        set(prefixes)
    )

    print(
        f"BGP prefixes found: "
        f"{len(prefixes):,}"
    )

    return prefixes


# ============================================================
# DOWNLOAD ONE RPKI FILE
# ============================================================

def download_roa_file(
    trust_anchor,
    date
):

    year = date[:4]
    month = date[5:7]
    day = date[8:10]

    os.makedirs(
        RPKI_CACHE_DIR,
        exist_ok=True
    )

    cache_file = (
        f"{RPKI_CACHE_DIR}/"
        f"{trust_anchor}_{date}.csv"
    )

    # --------------------------------------------------------
    # Use cached file
    # --------------------------------------------------------

    if os.path.exists(
        cache_file
    ):

        print(
            f"Using cached "
            f"{trust_anchor}"
        )

        return pd.read_csv(
            cache_file
        )

    # --------------------------------------------------------
    # Build archive URL
    # --------------------------------------------------------

    url = (
        f"{RPKI_BASE_URL}/"
        f"{trust_anchor}.tal/"
        f"{year}/{month}/{day}/"
        f"roas.csv.xz"
    )

    print()
    print(
        f"Downloading "
        f"{trust_anchor}..."
    )

    print(url)

    try:

        response = requests.get(
            url,
            timeout=120
        )

    except requests.RequestException as e:

        print(
            f"Download error: {e}"
        )

        return None

    if response.status_code != 200:

        print(
            f"HTTP "
            f"{response.status_code}"
        )

        return None

    # --------------------------------------------------------
    # Decompress XZ
    # --------------------------------------------------------

    try:

        decompressed = lzma.decompress(
            response.content
        )

    except lzma.LZMAError as e:

        print(
            f"XZ decompression error: "
            f"{e}"
        )

        return None

    # --------------------------------------------------------
    # Read CSV
    # --------------------------------------------------------

    df = pd.read_csv(
        io.BytesIO(
            decompressed
        )
    )

    # Remove whitespace
    df.columns = [
        column.strip()
        for column in df.columns
    ]

    # Add trust anchor
    df["trust_anchor"] = (
        trust_anchor
    )

    print(
        f"Downloaded "
        f"{len(df):,} ROAs"
    )

    # --------------------------------------------------------
    # Cache
    # --------------------------------------------------------

    df.to_csv(
        cache_file,
        index=False
    )

    print(
        f"Cached as "
        f"{cache_file}"
    )

    return df


# ============================================================
# DOWNLOAD ALL RPKI DATA
# ============================================================

def download_all_roas(
    date
):

    print()
    print("=" * 80)

    print(
        f"Loading RPKI snapshot "
        f"{date}"
    )

    print("=" * 80)

    frames = []

    for trust_anchor in TRUST_ANCHORS:

        df = download_roa_file(
            trust_anchor,
            date
        )

        if df is not None:

            frames.append(
                df
            )

    if not frames:

        raise RuntimeError(
            "No RPKI data could be loaded."
        )

    combined = pd.concat(
        frames,
        ignore_index=True
    )

    print()
    print(
        f"Total RPKI ROAs loaded: "
        f"{len(combined):,}"
    )

    return combined


# ============================================================
# BUILD RADIX TREE
# ============================================================

def build_radix_tree(
    rpki_df
):

    print()
    print("=" * 80)

    print(
        "Building RPKI radix tree..."
    )

    print("=" * 80)

    tree = radix.Radix()

    inserted = 0

    for _, row in rpki_df.iterrows():

        prefix = str(
            row["IP Prefix"]
        ).strip()

        try:

            network = ipaddress.ip_network(
                prefix,
                strict=False
            )

        except ValueError:

            continue

        node = tree.add(
            str(network)
        )

        # A prefix can have
        # multiple ROAs.

        if "roas" not in node.data:

            node.data["roas"] = []

        # Normalize ASN

        asn_string = str(
            row["ASN"]
        )

        asn_string = (
            asn_string
            .replace(
                "AS",
                ""
            )
            .strip()
        )

        try:

            roa_asn = int(
                asn_string
            )

        except ValueError:

            continue

        # Normalize max length

        try:

            max_length = int(
                row["Max Length"]
            )

        except (
            ValueError,
            TypeError
        ):

            continue

        node.data[
            "roas"
        ].append(
            {
                "asn":
                    roa_asn,

                "max_length":
                    max_length,

                "trust_anchor":
                    row[
                        "trust_anchor"
                    ]
            }
        )

        inserted += 1

    print(
        f"Inserted "
        f"{inserted:,} ROAs"
    )

    print(
        "Radix tree ready."
    )

    return tree


# ============================================================
# VALIDATE ONE PREFIX
# ============================================================

def validate_prefix(
    prefix,
    origin_asn,
    tree
):

    try:

        network = ipaddress.ip_network(
            prefix,
            strict=False
        )

    except ValueError:

        return "UNKNOWN"

    # --------------------------------------------------------
    # Find ROAs covering this prefix
    # --------------------------------------------------------

    covered_nodes = (
        tree.search_covering(
            str(network)
        )
    )

    if not covered_nodes:

        return "UNKNOWN"

    # --------------------------------------------------------
    # Collect ROAs
    # --------------------------------------------------------

    roas = []

    for node in covered_nodes:

        roas.extend(
            node.data.get(
                "roas",
                []
            )
        )

    if not roas:

        return "UNKNOWN"

    # --------------------------------------------------------
    # Find ROAs authorizing this ASN
    # --------------------------------------------------------

    matching_roas = [
        roa
        for roa in roas
        if roa["asn"] == origin_asn
    ]

    # --------------------------------------------------------
    # ROA exists but authorizes
    # a different ASN
    # --------------------------------------------------------

    if not matching_roas:

        return "INVALID ASN"

    # --------------------------------------------------------
    # Check prefix length
    # --------------------------------------------------------

    prefix_length = (
        network.prefixlen
    )

    for roa in matching_roas:

        if (
            prefix_length
            <=
            roa["max_length"]
        ):

            return "VALID"

    # --------------------------------------------------------
    # ASN authorized, but prefix
    # is too specific
    # --------------------------------------------------------

    return "INVALID LENGTH"


# ============================================================
# VALIDATE ALL PREFIXES FOR ONE ASN
# ============================================================

def validate_asn(
    asn,
    prefixes,
    tree
):

    print()
    print("-" * 80)

    print(
        f"Validating AS{asn}"
    )

    print("-" * 80)

    counts = {
        "VALID": 0,
        "INVALID ASN": 0,
        "INVALID LENGTH": 0,
        "UNKNOWN": 0
    }

    total = len(
        prefixes
    )

    for index, prefix in enumerate(
        prefixes,
        start=1
    ):

        status = validate_prefix(
            prefix,
            asn,
            tree
        )

        counts[
            status
        ] += 1

        # ----------------------------------------------------
        # Progress every 1,000
        # ----------------------------------------------------

        if (
            index % 1000 == 0
            or
            index == total
        ):

            percentage = (
                index
                /
                total
                *
                100
            )

            print(
                f"  Validated "
                f"{index:,}/"
                f"{total:,} "
                f"("
                f"{percentage:.1f}%"
                f")"
            )

    return counts


# ============================================================
# CREATE SUMMARY
# ============================================================

def create_summary(
    asn,
    name,
    caida_rank,
    prefixes,
    counts
):

    total = len(
        prefixes
    )

    valid = counts[
        "VALID"
    ]

    invalid_asn = counts[
        "INVALID ASN"
    ]

    invalid_length = counts[
        "INVALID LENGTH"
    ]

    unknown = counts[
        "UNKNOWN"
    ]

    # --------------------------------------------------------
    # Total invalid
    # --------------------------------------------------------

    invalid = (
        invalid_asn
        +
        invalid_length
    )

    # --------------------------------------------------------
    # RPKI-covered announcements
    #
    # Valid + Invalid
    #
    # Unknown = no applicable ROA
    # --------------------------------------------------------

    covered = (
        valid
        +
        invalid
    )

    if total > 0:

        coverage = (
            covered
            /
            total
            *
            100
        )

        invalid_percentage = (
            invalid
            /
            total
            *
            100
        )

    else:

        coverage = 0.0
        invalid_percentage = 0.0

    return {
        "ASN":
            f"AS{asn}",

        "AS Name":
            name,

        "CAIDA Rank":
            caida_rank,

        "BGP Prefixes":
            total,

        "Valid":
            valid,

        "Invalid ASN":
            invalid_asn,

        "Invalid Length":
            invalid_length,

        "Invalid":
            invalid,

        "Unknown":
            unknown,

        "RPKI Coverage":
            f"{coverage:.2f}%",

        "Invalid %":
            f"{invalid_percentage:.2f}%"
    }


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # Country
    # --------------------------------------------------------

    country = get_country(
        COUNTRY_INPUT
    )

    if country is None:

        print(
            "Country not found."
        )

        return

    country_name = (
        country["name"]
    )

    country_code = (
        country["code"]
    )

    print()
    print("=" * 80)

    print(
        f"RPKI REPORT FOR "
        f"{country_name} "
        f"({country_code})"
    )

    print("=" * 80)

    # --------------------------------------------------------
    # Step 1
    # Get top 15 ASes
    # --------------------------------------------------------

    top_asns = get_top_asns(
        country_code,
        TOP_N
    )

    if not top_asns:

        print(
            "No ASes found."
        )

        return

    print()
    print(
        f"Top {len(top_asns)} ASes:"
    )

    print()

    for position, item in enumerate(
        top_asns,
        start=1
    ):

        print(
            f"{position:2}. "
            f"AS{item['asn']:<8} "
            f"{item['name']:<35} "
            f"CAIDA Rank: "
            f"{item['rank']}"
        )

    # --------------------------------------------------------
    # Step 2
    # Download RPKI ONCE
    # --------------------------------------------------------

    rpki_df = download_all_roas(
        RPKI_DATE
    )

    # --------------------------------------------------------
    # Step 3
    # Build radix tree ONCE
    # --------------------------------------------------------

    tree = build_radix_tree(
        rpki_df
    )

    # --------------------------------------------------------
    # Step 4
    # Process each AS
    # --------------------------------------------------------

    results = []

    for position, item in enumerate(
        top_asns,
        start=1
    ):

        asn = item[
            "asn"
        ]

        name = item[
            "name"
        ]

        caida_rank = item[
            "rank"
        ]

        print()
        print()
        print("=" * 100)

        print(
            f"[{position}/{len(top_asns)}] "
            f"AS{asn} - {name}"
        )

        print("=" * 100)

        # ----------------------------------------------------
        # Get BGP prefixes
        # ----------------------------------------------------

        try:

            prefixes = get_bgp_prefixes(
                asn
            )

        except Exception as e:

            print(
                f"Error getting BGP "
                f"prefixes for AS{asn}: "
                f"{e}"
            )

            continue

        if not prefixes:

            print(
                "No BGP prefixes found."
            )

            continue

        # ----------------------------------------------------
        # Validate locally
        # ----------------------------------------------------

        try:

            counts = validate_asn(
                asn,
                prefixes,
                tree
            )

        except Exception as e:

            print(
                f"Validation error "
                f"for AS{asn}: {e}"
            )

            continue

        # ----------------------------------------------------
        # Create result
        # ----------------------------------------------------

        result = create_summary(
            asn,
            name,
            caida_rank,
            prefixes,
            counts
        )

        results.append(
            result
        )

        # ----------------------------------------------------
        # Show individual result
        # ----------------------------------------------------

        print()

        print(
            f"AS{asn} result:"
        )

        print(
            f"  BGP Prefixes: "
            f"{result['BGP Prefixes']:,}"
        )

        print(
            f"  Valid: "
            f"{result['Valid']:,}"
        )

        print(
            f"  Invalid ASN: "
            f"{result['Invalid ASN']:,}"
        )

        print(
            f"  Invalid Length: "
            f"{result['Invalid Length']:,}"
        )

        print(
            f"  Unknown: "
            f"{result['Unknown']:,}"
        )

        print(
            f"  RPKI Coverage: "
            f"{result['RPKI Coverage']}"
        )

    # --------------------------------------------------------
    # No results
    # --------------------------------------------------------

    if not results:

        print()
        print(
            "No RPKI results were produced."
        )

        return

    # --------------------------------------------------------
    # Final DataFrame
    # --------------------------------------------------------

    final_df = pd.DataFrame(
        results
    )

    # --------------------------------------------------------
    # Print final table
    # --------------------------------------------------------

    print()
    print()
    print("=" * 140)

    print(
        f"TOP {len(results)} AS RPKI REPORT - "
        f"{country_name}"
    )

    print("=" * 140)

    print(
        final_df.to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # Save CSV
    # --------------------------------------------------------

    filename = (
        f"{country_code}_"
        f"top_{len(results)}_"
        f"rpki_report.csv"
    )

    final_df.to_csv(
        filename,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print(
        "=" * 80
    )

    print(
        f"Report saved to: "
        f"{filename}"
    )

    print(
        "=" * 80
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()