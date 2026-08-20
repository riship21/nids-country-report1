import csv
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import pycountry
import requests


# ============================================================
# CONFIGURATION
# ============================================================

TOP_N = 15
PAGE_SIZE = 5000
BGP_WINDOW_DAYS = 14
MAX_WORKERS = 6


CAIDA_URL = "https://api.asrank.caida.org/v2/graphql"

ANNOUNCED_PREFIXES_URL = (
    "https://stat.ripe.net/data/announced-prefixes/data.json"
)

RPKI_VALIDATION_URL = (
    "https://stat.ripe.net/data/rpki-validation/data.json"
)


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
# COUNTRY INPUT
# ============================================================

def get_country(country_input):

    try:

        country = pycountry.countries.lookup(
            country_input
        )

        return {
            "code": country.alpha_2,
            "name": country.name,
        }

    except LookupError:

        raise ValueError(
            f"Could not recognize country: {country_input}"
        )


# ============================================================
# GET TOP 15 ASNs FROM CAIDA
# ============================================================

def get_top_country_asns(
    country_code,
    top_n=TOP_N,
):

    country_code = country_code.upper()

    print()
    print(
        f"Scanning CAIDA ASRank for "
        f"{country_code}..."
    )

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
                f"CAIDA GraphQL error: "
                f"{payload['errors']}"
            )

        data = payload[
            "data"
        ][
            "asns"
        ]

        edges = data.get(
            "edges",
            [],
        )

        if not edges:
            break

        for edge in edges:

            node = edge.get(
                "node"
            )

            if not node:
                continue

            country = node.get(
                "country"
            )

            if not country:
                continue

            if country.get(
                "iso"
            ) != country_code:

                continue

            asn = str(
                node.get(
                    "asn"
                )
            )

            if asn in seen_asns:
                continue

            seen_asns.add(
                asn
            )

            results.append(
                {
                    "asn":
                        asn,

                    "name":
                        node.get(
                            "asnName"
                        )
                        or
                        "Unknown",

                    "asrank":
                        node.get(
                            "rank"
                        ),

                    "country_rank":
                        len(results) + 1,
                }
            )

            # ---------------------------------------
            # IMPORTANT:
            # Stop immediately after top 15 found
            # ---------------------------------------

            if len(results) >= top_n:
                break

        print(
            f"Page {page} "
            f"| Found "
            f"{len(results)}/{top_n} "
            f"ASNs"
        )

        if len(results) >= top_n:
            break

        if not data[
            "pageInfo"
        ][
            "hasNextPage"
        ]:

            break

        offset += PAGE_SIZE
        page += 1

    return results


# ============================================================
# TIME WINDOW
# ============================================================

def get_time_window(
    days=BGP_WINDOW_DAYS,
):

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time
        -
        timedelta(
            days=days
        )
    )

    starttime = (
        start_time.strftime(
            "%Y-%m-%dT%H:%M"
        )
    )

    endtime = (
        end_time.strftime(
            "%Y-%m-%dT%H:%M"
        )
    )

    return (
        starttime,
        endtime,
    )


# ============================================================
# GET ANNOUNCED PREFIXES
# ============================================================

def get_announced_prefixes(
    asn,
    starttime,
    endtime,
):

    params = {
        "resource":
            f"AS{asn}",

        "starttime":
            starttime,

        "endtime":
            endtime,

        "min_peers_seeing":
            10,
    }

    response = requests.get(
        ANNOUNCED_PREFIXES_URL,
        params=params,
        timeout=60,
    )

    response.raise_for_status()

    payload = response.json()

    if payload.get(
        "status"
    ) != "ok":

        raise RuntimeError(
            payload.get(
                "message",
                "RIPEstat error",
            )
        )

    prefixes = []

    data = payload.get(
        "data",
        {},
    )

    for item in data.get(
        "prefixes",
        [],
    ):

        prefix = item.get(
            "prefix"
        )

        if prefix:

            prefixes.append(
                prefix
            )

    return sorted(
        set(
            prefixes
        )
    )


# ============================================================
# RPKI VALIDATION
# ============================================================

def validate_prefix(
    asn,
    prefix,
):

    params = {
        "resource":
            str(asn),

        "prefix":
            prefix,
    }

    try:

        response = requests.get(
            RPKI_VALIDATION_URL,
            params=params,
            timeout=30,
        )

        response.raise_for_status()

        payload = response.json()

        if payload.get(
            "status"
        ) != "ok":

            return {
                "prefix":
                    prefix,

                "status":
                    "api_error",

                "description":
                    payload.get(
                        "message",
                        "RIPEstat error",
                    ),
            }

        data = payload.get(
            "data",
            {},
        )

        return {
            "prefix":
                prefix,

            "status":
                data.get(
                    "status",
                    "unknown",
                ),

            "description":
                data.get(
                    "description",
                    "",
                ),
        }

    except Exception as error:

        return {
            "prefix":
                prefix,

            "status":
                "api_error",

            "description":
                str(error),
        }


# ============================================================
# ANALYZE ONE ASN
# ============================================================

def analyze_asn(
    asn_info,
    starttime,
    endtime,
):

    asn = asn_info[
        "asn"
    ]

    name = asn_info[
        "name"
    ]

    print()
    print("=" * 70)

    print(
        f"Analyzing "
        f"AS{asn} - {name}"
    )

    print(
        f"Country Rank: "
        f"{asn_info['country_rank']}"
    )

    print(
        f"CAIDA Global Rank: "
        f"{asn_info['asrank']}"
    )

    # --------------------------------------------------------
    # Announced prefixes
    # --------------------------------------------------------

    try:

        prefixes = (
            get_announced_prefixes(
                asn,
                starttime,
                endtime,
            )
        )

    except Exception as error:

        print(
            f"Could not get prefixes: "
            f"{error}"
        )

        return {
            **asn_info,

            "total_prefixes":
                0,

            "valid":
                0,

            "invalid_asn":
                0,

            "invalid_length":
                0,

            "unknown":
                0,

            "api_errors":
                1,

            "coverage_percent":
                0,

            "invalid_percent":
                0,

            "problem_prefixes":
                [],
        }

    print(
        f"Observed BGP prefixes: "
        f"{len(prefixes)}"
    )

    # --------------------------------------------------------
    # Counters
    # --------------------------------------------------------

    counts = {
        "valid":
            0,

        "invalid_asn":
            0,

        "invalid_length":
            0,

        "unknown":
            0,

        "api_error":
            0,
    }

    problems = []

    # --------------------------------------------------------
    # Validate prefixes
    # --------------------------------------------------------

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = [
            executor.submit(
                validate_prefix,
                asn,
                prefix,
            )
            for prefix in prefixes
        ]

        completed = 0

        for future in as_completed(
            futures
        ):

            result = (
                future.result()
            )

            status = result[
                "status"
            ]

            if status in counts:

                counts[
                    status
                ] += 1

            else:

                counts[
                    "api_error"
                ] += 1

            if status in (
                "invalid_asn",
                "invalid_length",
                "unknown",
            ):

                problems.append(
                    {
                        "asn":
                            f"AS{asn}",

                        "as_name":
                            name,

                        "prefix":
                            result[
                                "prefix"
                            ],

                        "status":
                            status,

                        "description":
                            result[
                                "description"
                            ],
                    }
                )

            completed += 1

            if (
                completed % 100 == 0
                or
                completed == len(
                    prefixes
                )
            ):

                print(
                    f"Validated "
                    f"{completed}/"
                    f"{len(prefixes)}"
                )

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    checked = (
        counts[
            "valid"
        ]
        +
        counts[
            "invalid_asn"
        ]
        +
        counts[
            "invalid_length"
        ]
        +
        counts[
            "unknown"
        ]
    )

    covered = (
        counts[
            "valid"
        ]
        +
        counts[
            "invalid_asn"
        ]
        +
        counts[
            "invalid_length"
        ]
    )

    invalid = (
        counts[
            "invalid_asn"
        ]
        +
        counts[
            "invalid_length"
        ]
    )

    if checked > 0:

        coverage_percent = (
            covered
            /
            checked
            *
            100
        )

        invalid_percent = (
            invalid
            /
            checked
            *
            100
        )

    else:

        coverage_percent = 0
        invalid_percent = 0

    return {
        **asn_info,

        "total_prefixes":
            len(prefixes),

        "valid":
            counts[
                "valid"
            ],

        "invalid_asn":
            counts[
                "invalid_asn"
            ],

        "invalid_length":
            counts[
                "invalid_length"
            ],

        "unknown":
            counts[
                "unknown"
            ],

        "api_errors":
            counts[
                "api_error"
            ],

        "coverage_percent":
            coverage_percent,

        "invalid_percent":
            invalid_percent,

        "problem_prefixes":
            problems,
    }


# ============================================================
# PRINT REPORT
# ============================================================

def print_report(
    country_name,
    country_code,
    results,
):

    print()
    print("=" * 135)

    print(
        "REPORT 2: ROUTING SECURITY "
        "AND RPKI READINESS"
    )

    print(
        f"Country: "
        f"{country_name} "
        f"({country_code})"
    )

    print("=" * 135)

    print(
        f"{'C.Rank':<8}"
        f"{'ASN':<12}"
        f"{'AS Name':<30}"
        f"{'ASRank':>9}"
        f"{'Prefixes':>10}"
        f"{'Valid':>9}"
        f"{'Inv ASN':>10}"
        f"{'Inv Len':>10}"
        f"{'Unknown':>10}"
        f"{'Coverage':>12}"
        f"{'Invalid':>11}"
    )

    print(
        "-" * 135
    )

    for result in results:

        name = result[
            "name"
        ]

        if len(
            name
        ) > 27:

            name = (
                name[:27]
                + "..."
            )

        print(
            f"{result['country_rank']:<8}"
            f"{'AS' + result['asn']:<12}"
            f"{name:<30}"
            f"{result['asrank']:>9}"
            f"{result['total_prefixes']:>10}"
            f"{result['valid']:>9}"
            f"{result['invalid_asn']:>10}"
            f"{result['invalid_length']:>10}"
            f"{result['unknown']:>10}"
            f"{result['coverage_percent']:>11.2f}%"
            f"{result['invalid_percent']:>10.2f}%"
        )


# ============================================================
# SAVE CSV
# ============================================================

def save_summary(
    country_code,
    results,
):

    filename = (
        f"{country_code.lower()}"
        "_rpki_summary.csv"
    )

    fields = [
        "country_rank",
        "asn",
        "name",
        "asrank",
        "total_prefixes",
        "valid",
        "invalid_asn",
        "invalid_length",
        "unknown",
        "api_errors",
        "coverage_percent",
        "invalid_percent",
    ]

    with open(
        filename,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fields,
        )

        writer.writeheader()

        for result in results:

            writer.writerow(
                {
                    field:
                        result.get(
                            field
                        )
                    for field in fields
                }
            )

    return filename


# ============================================================
# MAIN
# ============================================================

def main():

    country_input = input(
        "Enter a country name "
        "or country code: "
    ).strip()

    try:

        country = get_country(
            country_input
        )

    except ValueError as error:

        print(
            error
        )

        return

    country_code = (
        country[
            "code"
        ]
    )

    country_name = (
        country[
            "name"
        ]
    )

    print()
    print(
        f"Country: "
        f"{country_name} "
        f"({country_code})"
    )

    # --------------------------------------------------------
    # CAIDA top 15
    # --------------------------------------------------------

    print()
    print(
        f"Getting top {TOP_N} ASNs "
        f"from CAIDA ASRank..."
    )

    try:

        asns = (
            get_top_country_asns(
                country_code
            )
        )

    except Exception as error:

        print(
            f"CAIDA query failed: "
            f"{error}"
        )

        return

    print()
    print(
        "Top ASNs:"
    )

    for item in asns:

        print(
            f"{item['country_rank']:>2}. "
            f"AS{item['asn']:<10} "
            f"{item['name']:<35} "
            f"Global Rank: "
            f"{item['asrank']}"
        )

    # --------------------------------------------------------
    # BGP window
    # --------------------------------------------------------

    (
        starttime,
        endtime,
    ) = get_time_window()

    print()
    print(
        "BGP observation window:"
    )

    print(
        f"{starttime} "
        f"to "
        f"{endtime} UTC"
    )

    # --------------------------------------------------------
    # RPKI analysis
    # --------------------------------------------------------

    results = []

    for asn_info in asns:

        result = analyze_asn(
            asn_info,
            starttime,
            endtime,
        )

        results.append(
            result
        )

    # --------------------------------------------------------
    # Final report
    # --------------------------------------------------------

    print_report(
        country_name,
        country_code,
        results,
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    filename = (
        save_summary(
            country_code,
            results,
        )
    )

    print()
    print(
        f"Saved report to: "
        f"{filename}"
    )


if __name__ == "__main__":
    main()