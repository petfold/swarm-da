# swarm-da

Swarm as a data-availability layer: what building loopmarket on Swarm
taught about the promises Swarm keeps and the ones it does not, the
archival-DA opportunity the pruning incumbents leave open, and the ask to
the Swarm core team (expose and anchor the push-sync receipts Bee already
signs; a blob-mirror pipeline with a bonded KZG-to-BMT binding).

- [`swarm-data-availability.md`](swarm-data-availability.md) — the memo (2026-09-09, verified 2026-09-10; addendum 2026-09-11, §3.5: ordering and throughput — 2026 substrate capacities against card-network volume, and Swarm's own reserve as the yardstick), with an appendix mapping loopmarket onto rollup vocabulary.
- [`scripts/refresh_numbers.py`](scripts/refresh_numbers.py) — pulls every external figure the memo quotes (swarmscan node state, blobscan daily blob fees, CoinGecko prices) and prints them with today's date; standard library only.

Companion repositories: [loopmarket](https://github.com/petfold/loopmarket),
[recordstore](https://github.com/petfold/recordstore),
[ontodag](https://github.com/petfold/ontodag),
[factbond](https://github.com/petfold/factbond).
