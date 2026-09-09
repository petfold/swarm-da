#!/usr/bin/env python3
"""Refresh the external numbers quoted in swarm-data-availability.md.

Pulls, with the standard library only:
  - Swarm network state from swarmscan (node counts, countries, neighbourhoods)
  - Ethereum blob fees from blobscan's daily series (the JavaScript-only
    stats page at https://blobscan.com/stats is rendered from this endpoint;
    it is not in their public docs and was found in the router source,
    packages/api/src/routers/stats/getTimeseries.ts)
  - token prices from CoinGecko (ids matter: swarm-bzz, not bzz)

and prints the figures the memo's landscape table and §4.6 quote, with
today's date, so a refresh is one run. Nothing is written; paste by hand
and keep the memo's "checked <date>" wording honest.

Usage:  python3 scripts/refresh_numbers.py [--days 30]
"""
import argparse
import datetime as dt
import json
import statistics
import sys
import urllib.request

UA = "swarm-da-refresh/1.0 (+https://github.com/petfold/swarm-da)"
BLOB_GAS = 131_072            # blob gas per blob (EIP-4844)
BLOB_BYTES = 4096 * 31        # usable bytes per blob (field elements are 31 bytes)
P1_BATCH_XBZZ_PER_YEAR = 2.0  # depth-17 batch at the reference price, P1-federated-book.md §6
P1_BATCH_SLOTS_MB = 512       # 2^17 chunks x 4 KB, theoretical


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def swarmscan():
    d = get("https://api.swarmscan.io/v1/network/stats")
    nodes = d.get("count")
    unreachable = d.get("unreachableCount", 0)
    countries = d.get("countries") or d.get("countryCounts") or {}
    if not countries:  # key name has changed before; find the dict with 'Germany'
        for v in d.values():
            if isinstance(v, dict) and "Germany" in v:
                countries = v
                break
    neigh = d.get("neighborhoods") or d.get("neighbourhoods") or {}
    if not neigh:
        for v in d.values():
            if isinstance(v, dict) and any(k.startswith("0b") for k in v):
                neigh = v
                break
    sizes = list(neigh.values()) if neigh else []
    return {
        "nodes": nodes,
        "reachable": (nodes - unreachable) if nodes is not None else None,
        "germany": countries.get("Germany"),
        "finland": countries.get("Finland"),
        "unlocated": countries.get(""),
        "neighbourhoods": len(neigh),
        "neigh_min": min(sizes) if sizes else None,
        "neigh_max": max(sizes) if sizes else None,
    }


def blobscan(days):
    d = get(f"https://api.blobscan.com/stats/timeseries?timeFrame={days}d")["data"]
    ts = d["timestamps"]
    g = next(s for s in d["series"] if s["dimension"]["type"] == "global")
    m = g["metrics"]
    fee_eth = [f / 1e18 for f in m["avgBlobFee"]]          # per blob, incl. carrier tx gas
    gp_gwei = [p / 1e9 for p in m["avgBlobGasPrice"]]      # per blob gas
    bpb = [b / k for b, k in zip(m["totalBlobs"], m["totalBlocks"])]
    return {
        "first_day": ts[-1][:10], "last_day": ts[0][:10],
        "fee7": statistics.mean(fee_eth[:7]), "fee_all": statistics.mean(fee_eth),
        "gp7": statistics.mean(gp_gwei[:7]), "gp_all": statistics.mean(gp_gwei),
        "gp_max": max(gp_gwei), "gp_max_day": ts[gp_gwei.index(max(gp_gwei))][:10],
        "fee_max": max(fee_eth),
        "blobs_per_block7": statistics.mean(bpb[:7]),
    }


def prices():
    d = get("https://api.coingecko.com/api/v3/simple/price"
            "?ids=ethereum,celestia,swarm-bzz,eigenlayer&vs_currencies=usd")
    return {k: v["usd"] for k, v in d.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30, choices=[7, 15, 30])
    a = ap.parse_args()
    today = dt.date.today().isoformat()
    print(f"# swarm-da numbers, refreshed {today}\n")

    try:
        p = prices()
        eth, tia, bzz, eigen = p["ethereum"], p["celestia"], p["swarm-bzz"], p["eigenlayer"]
        print(f"Prices (CoinGecko): ETH ${eth:,.0f}  TIA ${tia:.2f}  BZZ ${bzz:.3f}  EIGEN ${eigen:.2f}\n")
    except Exception as e:  # noqa: BLE001
        print(f"prices: FAILED ({e})\n", file=sys.stderr); eth = bzz = None

    try:
        s = swarmscan()
        print("Swarm (swarmscan /v1/network/stats)")
        print(f"  nodes {s['nodes']}, reachable {s['reachable']}, "
              f"{s['neighbourhoods']} neighbourhoods of {s['neigh_min']} to {s['neigh_max']} nodes")
        print(f"  Germany {s['germany']}, Finland {s['finland']}, unlocated {s['unlocated']}")
        print("  (no live staking count is exposed; use the Foundation's latest State of the Network post)\n")
    except Exception as e:  # noqa: BLE001
        print(f"swarmscan: FAILED ({e})\n", file=sys.stderr)

    try:
        b = blobscan(a.days)
        print(f"Ethereum blobs (blobscan daily series, {b['first_day']} to {b['last_day']})")
        print(f"  blob gas price: 7-day mean {b['gp7']:.4f} gwei, {a.days}-day mean {b['gp_all']:.4f} gwei, "
              f"max {b['gp_max']:.4f} gwei on {b['gp_max_day']}")
        print(f"  blobs per block, 7-day mean: {b['blobs_per_block7']:.1f} (target 14 since the Jan 2026 BPO fork)")
        if eth:
            per_mb = 1_048_576 / BLOB_BYTES
            print(f"  per blob incl. carrier tx: 7-day ${b['fee7']*eth:.4f}, {a.days}-day ${b['fee_all']*eth:.4f}, "
                  f"worst day ${b['fee_max']*eth:.3f}")
            print(f"  per MB ({per_mb:.2f} blobs): 7-day ${b['fee7']*eth*per_mb:.3f}, {a.days}-day ${b['fee_all']*eth*per_mb:.3f}")
            print("  note: the chart on blobscan.com/stats shows the bare gas price; the per-blob fee field\n"
                  "        also includes the carrier transaction's execution gas, hence slightly higher.\n")
    except Exception as e:  # noqa: BLE001
        print(f"blobscan: FAILED ({e})\n", file=sys.stderr)

    if bzz:
        usd_year = P1_BATCH_XBZZ_PER_YEAR * bzz
        print("Swarm retention at P1's reference stamp price (computed, not measured)")
        print(f"  depth-17 batch for a year: {P1_BATCH_XBZZ_PER_YEAR} xBZZ = ${usd_year:.3f} "
              f"for up to {P1_BATCH_SLOTS_MB} MB theoretical")
        print(f"  = ${usd_year / P1_BATCH_SLOTS_MB * 1024:.3f} per GB-year before bucket-utilisation loss; "
              "confirm the stamp price against the live oracle before quoting")


if __name__ == "__main__":
    main()
