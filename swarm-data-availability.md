# Swarm as a data-availability layer: what loopmarket learned, and the ask

Status: memo, 2026-09-09. Author: Peter Földiák (drafted with Claude).
Audience: the Swarm core team (GSOC/pub-sub and storage-incentives
owners) and Solar Punk. Prior mention: the Solar Punk ideabox thread of
2024-07-10
(<https://solar-punk-workspace.slack.com/archives/C079F2JEV5L/p1720597650797939>),
which quoted Vitalik Buterin's 2024-05-17 post on decentralization
(storing Ethereum's old history in a peer-to-peer network with erasure
coding, because relying on a few large archive operators is a 1-of-N
trust assumption with a small N, and Portal Network had not received
attention "commensurate with its importance"). Sándor called blockchain
data storage a naturally fitting Swarm use case; an AI assessment in
the same thread judged it "feasible but niche": a clean technical fit,
but a cold, write-once archive fights a postage model where the
publisher pays up front regardless of reads. This memo is the clearer
formulation two years on, informed by building a Swarm-backed
marketplace that has to satisfy an on-chain verifier. Section 1
separates the pieces, and §6 answers the cold-archive objection
directly.
Conventions follow the loopmarket plan corpus. A verification pass was
done on 2026-09-09: every external number carries its source and date,
and where a figure could not be found (EigenDA's per-GB rate, Avail's
retention window) the memo says so in place rather than guessing.
Vocabulary as in loopmarket's `README.md` (clearing = the atomic
commit, settlement = delivery). File paths in this memo refer to the
loopmarket repository (github.com/petfold/loopmarket) unless another
repository is named; the memo itself lives in its own folder,
`swarm-da/`, beside that repository.
Addendum 2026-09-11: §3.5 adds the axis the landscape table lacks —
ordering and throughput — with 2026 capacities measured against
card-network volume and Swarm's own reserve as the yardstick, and §5
gains a second consumer shape for receipts. Both come from the
loopmarket discussion recorded in its `docs/plans/P1-federated-book.md`
§4a ("anchoring offers on chain").

---

## 0. Summary

loopmarket keeps its whole offer book off-chain in a canonical trie on
Swarm and anchors only a 32-byte root on Gnosis Chain. Its P2 clearing
contract never reads Swarm: every claim it needs arrives as a trie proof
in calldata, verified against the anchored root. That is the shape of a
validium, with Swarm playing the data-availability (DA) layer. Building
it taught us precisely which DA promises Swarm already keeps and which
it does not.

The claim of this memo: **Swarm should not compete for short-window DA
against Ethereum blobs, Celestia and EigenDA. It should own the window
those layers deliberately abandon.** Every incumbent prunes: Ethereum
after roughly eighteen days, EigenDA after fourteen, Celestia after
seven. Ethereum's own history expiry is arriving in a 2026 hard fork.
Rollups, indexers and dispute systems need that data for years, and no
incentive layer except Swarm's is built for paid, permissionless,
long-horizon retention. Two additions turn Swarm from "a storage network
rollups could archive into" into "a DA layer a contract can rely on":
**publication receipts** (a verifiable statement that chunks were
released to the network by a given time; Bee already signs a per-chunk
storer receipt inside push-sync and then throws it away, so this is
exposure and anchoring, not new cryptography) and a **blob-mirror
pipeline** with a bonded binding between the chain's commitment and the
Swarm reference. loopmarket is a committed first consumer and can supply the
proof library, the verifier contract shape and the measurement rig.

## 0.5 What changed since the 2024 thread

Three things, and they turn a niche into a position.

1. **The demand is now scheduled.** In 2024 history expiry was a
   roadmap item; the "who stores old history" question could be
   deferred. Partial history expiry shipped in 2025 across all execution
   clients, and a rolling window is planned for a 2026 fork. Meanwhile
   every alternative DA layer has shortened its retention, Celestia from
   thirty days to seven. The market for "after pruning" is being created
   by the incumbents themselves, on a calendar.
2. **The object is not only Ethereum's history.** The 2024 framing was
   one chain's archive. Today the same shape recurs for every rollup's
   blobs, for every validium's off-chain state, and for applications
   like loopmarket whose whole state is a trie a contract only ever sees
   as a root. That is many paying publishers, not one public good.
3. **The ask is verifiability, not storage.** The 2024 pitch was "Swarm
   can hold the bytes". The 2024 assessment was right that this alone is
   unglamorous: storage is a commodity. What a contract, a rollup or a
   dispute needs is the *guarantee* around the bytes: that they were
   published by a time, that they are retrievable for a window, and
   that a root on chain provably names them. Those guarantees are the
   product. Swarm has the substrate for them and none of the packaging.

## 1. What a DA layer actually promises

"Data availability" is a bundle of four promises. Separating them is the
whole argument, because Swarm keeps two and a half of them today.

1. **Publication.** The bytes behind an on-chain commitment were
   released to the public at a known time, so the poster cannot publish
   a root and withhold the data. This is the load-bearing promise: a
   rollup's fraud-proof window, a validium's exit, a dispute's evidence
   all fail if the bytes were never released. Ethereum gets it from
   consensus (the blob is part of the block), Celestia from
   data-availability sampling by light nodes, EigenDA and Avail from a
   staked committee's attestation.
2. **Retrievability for a window.** Anyone can fetch the bytes for long
   enough to act on them. The incumbents choose short windows on
   purpose: retention is their dominant cost.
3. **A commitment a contract can verify.** The on-chain root must let a
   contract check "these bytes are the committed ones" cheaply. KZG
   commitments for blobs, Merkle roots elsewhere.
4. **A price.** Predictable, denominated, ideally per byte-time.

Swarm keeps 2 (with caveats below), keeps 3 (BMT is keccak, the EVM's
native hash), keeps 4 (postage stamps are literally byte-time pricing).
It half-keeps 1: the protocol produces a signed storer receipt for every
chunk pushed, but discards it inside the node (§4.1). Turning that
internal handshake into a verifiable, anchored artifact is the entire
distance between "storage" and "DA".

## 2. How loopmarket uses Swarm, and what it learned

The pattern, as specified in `docs/plans/proof-fabric.md` and
`docs/plans/P2-batch-auction.md`:

- **Data on Swarm.** Every maker's offer book is a recordstore trie
  whose blobs live on Swarm under the maker's own postage batch, its
  head in the maker's own signed feed. An aggregator folds the books
  and publishes a manifest of four roots.
- **Root on chain.** At each clearing beat's cutoff the pinned
  `book_root` is anchored in the clearing contract.
- **Proofs in calldata.** A clearing submission carries, per leg, a trie
  inclusion proof for the offer and a trie *absence* proof for its fill,
  both against the anchored root. recordstore ships both (v0.16.0);
  verification is hash-chain recomputation against 32 bytes with no
  store access.
- **The contract is blind.** It verifies the proofs, checks its own fill
  state, records fills. Pure function of chain state and calldata, so
  thousands of nodes replaying it touch nothing outside the chain.
- **Swarm is written afterwards, by anyone.** The chain's event log is
  the authority; the Swarm clearing book is a mirror rebuildable by any
  follower. Content-addressed blobs make concurrent uploaders harmless.
  Only a feed head needs a single writer.

What building this taught us about Swarm as a DA substrate, all
recorded in `docs/plans/P1-federated-book.md` §6 to §7:

- **Feed heads are the weak link.** A feed's SOC head is a single chunk:
  no erasure coding, only neighbourhood replication, and compare-and-set
  on a feed index is best-effort. We answered by never letting
  atomicity or authority rest on a feed. A DA layer must do the same, or
  fix feeds.
- **TTL is the data's real lifetime.** When a batch expires the data is
  gone, silently. We made "validity outlives stamp" unrepresentable and
  run a TTL monitor because Bee has no auto-top-up
  (ethersphere/bee#4992). This is a bug for a marketplace and a
  *feature* for archival DA, if surfaced honestly: retention is an
  explicit, priced, renewable commitment.
- **Permissionless top-up is a new economic primitive.** Anyone with
  BZZ can extend anyone's batch. For a marketplace that means a solver
  can keep alive the offers it profits from. For DA it means a rollup's
  history can be kept alive by whoever values it, without the rollup's
  cooperation. No other DA layer has this.
- **The network is thin and concentrated, and shrinking.** Swarmscan on
  2026-09-09: 3,824 nodes, 3,692 reachable, in 256 neighbourhoods of
  13 to 18 nodes each; Germany 1,114 and Finland 913 among nodes with a
  known location, 1,768 unlocated. The Foundation's January 2026 report
  had 4,270 reachable full nodes and 1,939 staking, itself down from
  December, so reachable nodes fell about 14% in eight months
  (swarmscan does not expose a live staking count; the January figure
  stands). The reachable figure is noisy day to day: 3,068 on
  2026-09-10 against 3,692 the day before, with the country split
  moving too, so quote it with its date and prefer the Foundation's
  monthly series for trend. A hosting outage is a correlated failure that replication
  math ignores. Our mitigation is one
  self-hosted always-on pinning node. A DA pitch has to state this
  plainly and show the erasure-coding and pinning story that offsets it.
- **Reads take seconds.** Feed lookups are second-scale. Fine for a
  dispute window measured in days, wrong for a sequencer's hot path.
  Archival DA sits on the right side of that line.

## 3. The landscape

| Layer | Publication promise | Retention | On-chain verifier | Pricing | Notes |
|---|---|---|---|---|---|
| Ethereum blobs (EIP-4844) | consensus: blob is in the block | 4096 epochs, about 18 days, then pruned; the KZG commitment stays | KZG point evaluation precompile | separate blob-gas market, floored since Fusaka (2025-12) at a fraction of the execution base fee (EIP-7918). Measured on blobscan's daily series for 2026-08-10 to 2026-09-08: blob gas price 0.007 gwei (7-day mean) to 0.011 gwei (30-day mean), i.e. $0.007 to $0.011 per 128 KB blob at ETH $2,484, about $0.055 to $0.09 per MB, with one spike day at $0.06 per blob; about 7 blobs per block against a 14-blob target. Conduit measured $20.56 per MB over Mar–Oct 2024, before Pectra and Fusaka widened capacity | Full history expiry (EIP-4444) is in phased rollout; pre-Merge history already droppable, a rolling ~1-year window planned for a 2026 fork |
| Celestia | data-availability sampling by light nodes | pruning window lowered from 30 days to 7 days + 1 hour (CIP-34), aligned with a 7-day sampling window (CIP-36) | Blobstream relays roots to EVM chains | per-blob fee in TIA. Conduit measured $7.31 per MB over Jan–Oct 2024 and $0.81 with SuperBlobs; a 2026-01 analysis cites about $0.07 per MB for one heavy user. TIA was $0.39 on 2026-09-09, roughly 98% below its late-2024 high, so the fiat price is mostly token price | Explicitly optimizing storage cost down, not retention up |
| EigenDA | staked operator committee attests | 14 days, then not archived by anyone | attestation verification | on-demand or reserved bandwidth, payable in ETH, EIGEN or the rollup's own token; a tenfold cut and a free tier of 1.28 KiB/s for twelve months announced 2024-08-19. The numeric per-GB schedule is published only as an image and "get in touch"; no rate in text anywhere we could reach (checked 2026-09-09) | Documentation tells users to archive themselves |
| Avail | validator set with KZG + DAS | no protocol retention window documented; L2BEAT lists "duration of storage" as unspecified; full nodes prune by default, archive mode is an operator flag (checked 2026-09-09) | Vector bridge to EVM; L2BEAT notes that without a DA bridge Ethereum has no proof of availability for a given deployment | formula: 0.124 AVAIL base fee + length fee + weight fee × congestion multiplier; no per-MB figure published | Same shape as Celestia; retention is whatever archive operators choose to keep |
| EthStorage | inherits Ethereum L1 publication, then stores long-term | "permanently replicated" by rewarded providers | storage L2 posting zk storage proofs to L1 | marketing only: "~0.1% of L1 cost", "1000x cheaper"; no per-GB price published anywhere we could find (checked 2026-09-09: docs, rollup guide, launch post, 2025 annual report) | Mainnet Alpha since 2025-10-14 with **whitelisted** storage providers; no disclosed node count, data volume or live customer; Optimism, Taiko and Celestia named as "ongoing integrations"; grant-funded (two EF grants, one Optimism grant); no token |
| Arweave | none at protocol level for third-party chains | permanent, pay-once endowment | via bridges/oracles only | one-off per byte | Permanence without renewal; no EVM-native hash |
| **Swarm** | **internal only**: push-sync returns a per-chunk receipt signed by the storing node (address, signature, nonce, storage radius); the uploader verifies it and drops it; nothing time-anchored or exposed | as long as the batch is stamped; renewable by anyone | BMT is keccak; a POT/BMT path verifier exists (`ethersphere/proximity-order-trie`), gas unbenchmarked | postage stamps: explicit byte-time price in BZZ | erasure coding on blobs (Bee 2.7+), not on single-chunk heads |

Two readings of the table:

- **The short window is a solved, crowded, cheap market.** Post-4844 the
  price floor for eighteen days of DA is set by Ethereum itself and
  undercut by the alternatives. Entering it means competing on price
  against layers whose main design goal is to prune faster.
- **The long window is nearly empty, and its demand is scheduled.** The
  moment Ethereum's rolling history expiry activates, every rollup that
  relied on "someone has the old blobs" needs an answer. EthStorage is
  the only purpose-built one, and Arweave the only durable generalist.
  Neither has renewable, permissionlessly-fundable, per-object
  retention.

## 3.5 The other axis: ordering and throughput (added 2026-09-11)

§1's four promises are about *bytes*: released, retrievable, committed,
priced. A marketplace asked a fifth question of the same substrates,
recorded in loopmarket's `P1-federated-book.md` §4a: **who orders the
events?** An offer's withdrawal racing its clearing, a beat's cutoff, an
aggregator's omission — each needs a total order, and none of §1's
promises supplies one. The incumbents bundle ordering with publication
(a blob is *in a block*; Celestia orders the blobs it samples). EigenDA
does not: the rollup orders, the committee attests. Swarm does not
either: feeds are single-writer, GSOC is many-to-one with no delivery
order, and the redistribution game orders nothing. So the question
became *what must a chain hold so that Swarm can hold the rest*, and the
answer sizes both halves.

**What a marketplace puts where.** The unit of commitment is a 32-byte
content address, the offer id. The body — 571 bytes canonical, measured
on a real offer — goes to Swarm; the id goes wherever ordering is bought:
~25k gas and ~240 bytes as a standalone L1 transaction (envelope, 65-byte
signature, log), ~120 bytes compressed inside a rollup batch (signatures
do not compress), ~50 bytes only with signature aggregation, which is a
batcher. Yardstick: card-network volume — Visa processed 257.5 B
transactions in FY2025 (~8,200/s average), Mastercard switched ~178 B in
2025 (~5,600/s); peaks run 2–3× average. At the combined 13,800/s the
ids are ~1.7 MB/s to a chain and the bodies ~7 MB/s, ~220 TB a year, to
Swarm. **The ordering layer carries 5% of the bytes and the data layer
95%** — the memo's thesis in one number.

| substrate (2026) | per-object anchors/s | ordering, permission | window | Visa 8,200/s | both 13,800/s |
|---|---|---|---|---|---|
| Gnosis L1 (30M gas / 5 s; 0.01 gwei) | ~240 | permissionless validators | history, forever | 34× over | 58× over |
| Ethereum L1 (60M gas; 200M with Glamsterdam, H2 2026) | ~200 → ~670 | permissionless | history, expiring | 12× over | 21× over |
| Ethereum blobs (14/21 since 2026-01-07; 48 planned mid-2026; 128 at full danksharding) | ~1,240 → ~4,300 → ~11,400 | shared by every rollup; each rollup's sequencer orders | ~18 days | fits only at 128 | 1.2× over at 128 |
| Arbitrum One (7M gas/s) | ~280, blob-bound | one sequencer; forced inclusion ≈ 1 day | blobs | no | no |
| Base (125–150 Mgas/s; 400–500 targeted 2026) | 5,000–20,000 execution, blob-bound | one sequencer; forced inclusion ≈ 12 h | blobs | execution yes, DA no until 48+ blobs | no until danksharding |
| Hedera Consensus Service | 10,000 governed cap; bursts 16,000 | hashgraph aBFT, fair ordering, built as exactly this service; **council-run nodes**; $0.0008/message since 2026-01 | mirror nodes | at average, not peak | no |
| Solana | 1,600–3,800 sustained real; Alpenglow, Firedancer pending | permissionless, heavy hardware | history | no today | no |
| Celestia (8 MB / 6 s; 21 MB/s on testnet) | ~11,000 as DA | permissionless DA; orders its blobs; execution in a rollup | 7 days | fits | 1.25× over |
| EigenDA V2 (100 MB/s) | ~800,000 as DA | a committee — an aggregator | 14 days | fits | fits |
| **Swarm** | **n/a — no ordering** | — | as long as stamped; renewable by anyone | bodies 7 MB/s: see the reserve yardstick below | |

Three readings, in the order they matter for this memo:

1. **Short-window layers sell ordering *and* publication.** That is what a
   marketplace rents from them, and it is the half Swarm cannot offer:
   Swarm's retention sits *behind* an ordering layer, never in place of
   one. §0's "own the window they abandon" is the same statement from the
   other side.
2. **At scale everyone batches, then anchors — and the batcher is the
   question.** Per-object anchors on Gnosis or Base carry a marketplace
   for years (a few hundred to a few thousand objects a second). Card
   volume on any substrate means a batcher orders, posts a root, and the
   base chain holds the escape hatch: one sequencer is one aggregator; a
   shared sequencer (Espresso, Astria) or a BFT/hashgraph run by the
   several aggregators a censorship-proof market needs anyway is a plural
   one. The root they anchor is precisely the artifact §4.1's receipt
   certifies — so **a receipt primitive has a second consumer**: not only
   "these bytes were released by T" but "this root, in this order". When
   the batcher writes to Swarm first, the DA receipt *is* the per-root
   anchor (§5).
3. **The proof-in-calldata shape (§2) has its own ceiling.** A clearing
   leg with a trie inclusion proof costs ~900 bytes and ~100k gas — more
   than anchoring the object it proves. At card scale that is 7 MB/s of
   proof data, five times full danksharding, so the validium's proofs
   must aggregate into a validity proof with only the state diff landing.
   §4.5's per-path gas headline therefore rules the small end, and the
   BMT verifier is the per-leg building block whose *aggregation* cost
   decides the large end.

**Swarm's own capacity, as the yardstick demands.** Bee's
`DefaultReserveCapacity` is 2²² = 4,194,304 chunks, 16 GiB per node
(`pkg/storer/storer.go`, master, read 2026-09-11). Every node in a
neighbourhood holds that neighbourhood's whole share, so with the 256
neighbourhoods swarmscan showed on 2026-09-09 (§2) the network's *unique*
live reserve is about 256 × 16 GiB ≈ **4 TiB**, from roughly 60 TiB raw
across ~3,800 nodes — about 15× replication, before caches and pins,
which do not count toward DA. A card-scale marketplace's *live* body set
— offers standing ~30 days — is ~18 TB, four to five times today's whole
reserve; the cumulative year is fifty times. Reserve capacity grows
with nodes (one more bit of depth doubles it), and Swarm is designed so
that node count follows demand: postage revenue is what recruits storers,
so a card-scale book is not a ceiling but the incentive the network was
built to answer. Today's figure is the supply side of §2's "thin and
shrinking" finding with the demand side now quantified; the question it
poses is how fast the storer population can follow a demand step, not
whether the protocol allows it. Two things are structural in
Swarm's favour: postage TTL makes the *live* set the load rather than the
cumulative one (the marketplace's friend, §2 — a card-scale book expires
as fast as it grows), and the pruning incumbents hit the same wall from
the other side — Ethereum's 128-blob endgame publishes 1.4 MB/s and then
forgets it after eighteen days, so the bodies still need a home, which
is §0's point.

Disposition (loopmarket, 2026-09-11): not urgent at zero volume, and the
substrate table will be stale before it matters. Recorded so the two axes
are not confused again: **retention is Swarm's to sell; ordering is
rented.**

## 4. What Swarm would need to add

Ranked by how much each closes the DA gap.

### 4.1 Publication receipts (the one that matters)

A contract needs to check "chunk set C, with root R, was released to
the network no later than time T". Swarm is closer to this than the
2024 thread or our first draft assumed. **Bee already issues receipts.**
In push-sync (`pkg/pushsync`, checked against `master` 2026-09-09) the
node that stores a chunk in its reserve signs the chunk address with
its node key and returns `Receipt{Address, Signature, Nonce,
StorageRadius}`. The uploading node recovers the public key, recomputes
the storer's overlay from key and nonce, checks the storer is deep
enough in the chunk's neighbourhood (the "shallow receipt" rule), and
then **discards the receipt**: the pusher only marks the chunk synced,
and the HTTP API exposes nothing but per-tag counters (split, stored,
sent, synced). The Book of Swarm's receipt and litigation lineage is
therefore not dead; it is implemented as an internal handshake.

What separates that handshake from a DA-grade publication proof:

- **Persistence and exposure.** Return the receipts to the API caller
  (per chunk, or as a Merkle set per upload) instead of dropping them.
  Zero protocol change; a Bee API addition.
- **What is signed.** Today: the chunk address alone. A DA receipt
  needs the batch id and a time anchor (a Gnosis block number or hash)
  in the signed payload, so "stored by block N under stamp S" is a
  statement rather than an inference. Small protocol change.
- **Linkage to stake.** Already possible: the receipt's signer address
  is the stake owner in the staking contract, whose record holds the
  overlay; a verifier recomputes the overlay from key and nonce and
  matches it. The contract already has `freezeDeposit` and
  `slashDeposit`, callable by the redistribution role. What is missing
  is a **challenge path**: "here is a receipt signed by staked node X
  for chunk C at block N; X cannot serve C inside the stamped window;
  slash." That is a new contract function and a retrieval-challenge
  protocol, not new cryptography.
- **Breadth.** One receipt comes from the single closest storer. A DA
  claim wants several storers of the neighbourhood, so the upload
  either fans out for receipts (Bee already pushes to multiple peers
  and picks the best receipt; it could keep all of them) or aggregates
  them (BLS if node keys allow, else a Merkle set of ECDSA receipts).
- **Meaning.** A receipt proves *acceptance into a reserve at push
  time*, not continued custody and not availability to everyone.
  Continued custody is the redistribution game's job, and it is worth
  being exact about what that game checks, because it is often
  described as "failed retrieval gets slashed" and it is not that
  (`Redistribution.sol` and Bee's `storageincentives` agent, read
  2026-09-10). Each round a neighbourhood is selected by an anchor;
  every node there hashes a *sample of its own reserve* (transformed
  addresses of chunks within the committed depth, keyed by the anchor,
  expired batches excluded), commits the hash, then reveals it. The
  stake-weighted majority hash is the round's truth. A node whose
  reveal disagrees is **frozen**, not slashed (the slash call is
  commented out, marked for a later phase); a node that committed and
  did not reveal is frozen for longer. A winner is drawn among the
  agreeing revealers and must present, in `claim`, BMT inclusion proofs
  for three sampled chunks plus their postage-stamp validity (batch
  owner signature, bucket alignment, batch alive) before the pot pays
  out. Push-sync receipts appear nowhere in this game.

  So the lottery proves *"every node here holds the same set, and the
  winner really holds three random members of it"*. It does not prove
  that any particular chunk is in that set: a chunk the whole
  neighbourhood dropped, or never received, is simply absent from every
  sample and every reveal agrees. That is exactly the hole a receipt
  fills. The receipt is the uploader's external evidence that chunk C
  was accepted by a staked node; the lottery is the network's internal
  evidence that what was accepted is still held in common. Neither
  alone is a DA guarantee; together, with a challenge path, they are.
  Neighbourhoods are small (mid-teens to twenties of nodes against a
  target redundancy of four), so collusion within one is cheap and the
  design must assume it.

Without this, Swarm is a storage network that a validium can *choose*
to trust. With it, Swarm is a DA layer a contract can *verify*. It is
the difference between the two halves of §1, and most of the pieces are
already in the codebase.

### 4.2 A blob-mirror pipeline with a bonded binding

The concrete product for rollups: a service (anyone can run it) that
watches a chain, fetches each blob before it is pruned, uploads it under
an immutable batch with erasure coding, and publishes a mapping from
the chain's commitment (the KZG versioned hash) to the Swarm reference.

The hard part is the **binding**: a KZG commitment and a BMT root are
different functions of the same bytes, and no contract can check their
equality cheaply. Three routes, weakest to strongest:

1. **Trusted mirror.** The mirror operator signs the mapping. Cheap,
   and exactly the centralization DA exists to avoid.
2. **Bonded assertion, optimistically adjudicated.** The mapping is
   published as a bonded claim: "Swarm reference X holds the bytes with
   versioned hash Y". Anyone who fetches both and finds a mismatch
   wins the bond. This is the shape factbond (github.com/petfold/factbond)
   already specifies for assertions in general, and the claim is
   *mechanically* checkable by any challenger, which is the best case
   for optimistic adjudication. Our recommendation for the first
   version.
3. **Validity proof.** A SNARK that the KZG commitment and the BMT root
   commit to the same bytes. Correct, expensive, later.

### 4.3 Feed-head hardening

Single-chunk objects get no parity and no atomic index claim. For a DA
layer whose users will point at "the latest checkpoint" through a feed,
either erasure-code heads, or document loudly that heads are pointers,
never authority, and give users an anchored alternative (a chain
event). We chose the second; a product should offer the first.

### 4.4 A retrieval service level, measured

Publish measured retrieval latency and success rate for stamped,
erasure-coded blobs at one week, one month, one year, on the live
network. We planned exactly this "calendar experiment" for our own book
(publish on a short batch, watch it die) and have the harness. Rollup
teams will ask for these numbers first.

### 4.5 Verifier contracts and gas

A reference BMT inclusion verifier on Gnosis and Ethereum with published
gas numbers. `assertForkPathProof` exists but, as far as we found, no
gas benchmark has been published anywhere; our own estimate is "tens of
thousands of gas per path node" and nothing firmer. A DA layer's proof
cost is a headline number.

### 4.6 Pricing in the buyer's units

A public price per GB-year with the BZZ exposure hedged or at least
displayed, and a comparison against the incumbents' per-blob fees. The
comparison must be honest about units: the incumbents price a one-time
publication with a short window, Swarm prices retention time. Today's
reference points (2026-09-09, CoinGecko: ETH $2,484, TIA $0.39, BZZ
$0.038, EIGEN $0.21):

- Ethereum blob, measured 7-day mean to 2026-09-08: $0.007 per blob,
  about $0.055 per MB, once, for 18 days ($0.09 per MB on the 30-day
  mean).
- Celestia: about $0.07 to $0.81 per MB, once, for 7 days, depending on
  packing.
- Swarm at P1's reference stamp price: a depth-17 batch for a year is
  about 2 xBZZ, or $0.08, for up to 512 MB of theoretical slots. That is
  on the order of $0.15 per GB-year before bucket-utilisation loss,
  computed from `P1-federated-book.md` §6 and today's price; confirm
  against the live price oracle before quoting it outside.

Read together: keeping a megabyte on Swarm for a year costs less than
publishing it once through Celestia, and the two figures buy different
things. That framing is the one to lead with. Note also that EthStorage,
the only long-term claimant, publishes no price at all, and EigenDA
publishes none in text; a posted per-GB-year number would on its own be
a differentiator.

## 5. What loopmarket and Solar Punk can bring

- **A committed consumer with a real verifier.** The P2 clearing
  contract consumes inclusion and absence proofs against anchored roots.
  It is the test case that forces every item in §4 to be concrete.
- **The proof library.** recordstore's canonical trie with inclusion and
  absence proofs, self-describing envelopes, verification with no store
  access. A "verifiable key-value store on Swarm" is a reusable
  template for any application, and it exists.
- **The binding-assertion mechanism.** factbond's bonded assertions and
  optimistic adjudication are precisely §4.2's route 2, already
  specified.
- **The measurement rig.** A self-hosted pinning node, a TTL monitor,
  the follower that rebuilds a book from nothing but a feed address,
  and the planned expiry experiment. We can run §4.4 for a first
  rollup's blobs within weeks.
- **A second consumer shape for receipts** (added 2026-09-11). Loopmarket's
  anchoring alternative (`P1-federated-book.md` §4a) ends, at scale, at
  "batch, then anchor a root". A receipt saying "chunk set with root R
  was released by T" *is* that anchor whenever the batcher writes to
  Swarm first; the same primitive then serves ordering as well as
  availability, and §3.5 sizes the demand for it — ids at 5% of the
  bytes, bodies at 95%.
- **GSOC experience.** Solar Punk's `@solarpunkltd/gsoc` is the
  announcement channel in P1; a mirror pipeline needs the same
  many-to-one channel to publish mappings.

**What loopmarket would do differently the day §4.1 ships.** This is
the strongest form of the "committed consumer" claim: a real user whose
Swarm-specific scaffolding disappears when the primitive exists.

- *The beat anchor stops trusting the poster.* Today an aggregator can
  anchor a book root whose blobs it never released, and
  `audit_manifest` can only catch that if the blobs are fetchable,
  which is what withholding denies. With receipts, the anchoring
  transaction carries evidence that every trie blob under the root was
  accepted by staked nodes before the cutoff block; a root without
  receipts is refused. The T14 withholding threat shrinks from an
  unprovable liveness failure to a slashable one.
- *Withdrawal timing becomes provable.* A maker's tombstone receipt
  with a block anchor proves the withdrawal was published before a
  given beat's cutoff. Today that rests on the aggregator's provenance
  records. Disputes about "I withdrew before you cleared" get a
  third-party artifact, which is also a ready-made evidence class for
  factbond.
- *The pinning node becomes belt and braces.* Durability moves from "we
  run a node that pins the book" to "staked nodes receipted it and the
  lottery freezes anyone who drops it". We would still run the node,
  no longer as the load-bearing guarantee.
- *TTL discipline becomes verifiable.* If the receipt payload carries
  the batch id, "this offer is paid for until block M" is checkable by
  anyone, not only by our own monitor; P1's rule that validity must not
  outlive the stamp turns from an internal check into a fact a solver
  or counterparty can verify.
- *The catalogue and factbond ride along.* ontodag roots and factbond
  records are the same shape, blobs under a root, and inherit the same
  guarantee with no design work.

What does not change: the clearing contract stays blind and consumes
inclusion and absence proofs from calldata, and the chain remains the
authority for fills. Those are ordering and atomicity, which no data
layer supplies. Receipts prove acceptance by a handful of staked nodes,
not availability to everyone, so chain-as-authority and the
follower-rebuild pattern stay.

## 6. Honest counter-arguments

- **The cold-archive economics objection (the 2024 thread's verdict).**
  History is written once and read almost never. Swarm's bandwidth
  incentives and neighbourhood caching reward hot data; a cold archive
  gets neither, and its publisher pays stamp renewals forever for
  chunks nobody pulls. This is the strongest objection and it deserves
  a full answer rather than a rebuttal:
  - *Retention is the storage incentive's job, not the bandwidth
    incentive's.* The redistribution game pays storers for holding
    their reserve whether or not anyone reads it, and freezes a node
    whose reserve sample disagrees with its neighbours. Cold data is
    exactly the case that game exists for; SWAP and caching were never
    going to carry it. The question is whether "the neighbourhood agrees
    on its holdings" is strong enough for a DA-grade claim about a
    *named* chunk, which it is not on its own, and which is why §4.1
    pairs receipts with that game rather than inventing a new one.
  - *"Publisher pays regardless of readers" is the right shape for an
    archive.* An archive's value is to readers who do not exist yet. A
    read-funded model would let it starve. The defect is not the
    direction of payment but the *identity* of the payer: a public good
    has no publisher. Permissionless top-up (§2) is the mechanism that
    fixes this, and it exists today: a rollup DAO, a foundation, an
    indexer, or an anonymous well-wisher can extend the batch holding
    history they value, without coordination. No competitor lets a
    third party extend retention of someone else's data.
  - *Long-tail retrievability is a measurement problem, not a mystery.*
    "Four copies plus erasure coding" was rightly called an
    understatement. The answer is §4.4: publish the measured curve for
    stamped, erasure-coded, unpinned cold data at one week, one month,
    one year, and let it drive the redundancy defaults. If the curve is
    bad, that is a Bee fix with a benchmark, not a reason to abandon the
    market.
  - *The renewal burden is a product surface.* A stamp that must be
    topped up is a subscription. Surfacing it as one (expiry alarms,
    auto-top-up from a funded endowment contract on Gnosis, receipts
    for who paid) turns the 2024 objection into the billing model. Bee
    has no auto-top-up today (bee#4992); a DA product needs it.
  What survives of the objection: Swarm will not be the *cheapest*
  place to keep cold bytes. It can be the only place where keeping them
  is permissionless, verifiable and independent of any one operator,
  which is the property Vitalik's 1-of-N argument was asking for.
- **EthStorage is there first, on paper.** Checked 2026-09-09: its
  Mainnet Alpha has run since 2025-10-14 with a whitelist of storage
  providers, its own 2025 annual report discloses no node count, stored
  volume or live customer, the rollup integrations it names are
  described as ongoing, and no per-GB price is published in its docs,
  launch post or guides, only "about 0.1% of L1 cost". The 2024
  testnet race reported 170-plus nodes; the node repository has about
  800 GitHub stars. We could not corroborate a specific failure, but
  after eleven months of mainnet there is no public evidence of
  adoption either, which is the more telling fact: the long-term niche
  has a claimant and still no incumbent. Swarm's differentiators
  remain chain-agnostic content addressing, per-object renewable
  retention, permissionless top-up, and a permissionless storer set
  with a running incentive game, against a whitelisted alpha.
- **Rollups may just self-archive.** A bucket at a cloud provider is
  cheaper than any decentralized layer. The counter is that
  self-archived history is a trust assumption the rollup's users cannot
  verify, and history expiry makes that assumption visible.
- **Ethereum has the Portal Network** for its own history. It covers
  execution history, not other chains' blobs, and it is not a paid
  service anyone can extend. Complementary, not competing.
- **The network is thin, and the trend is down.** Under four thousand
  reachable nodes, a 14% fall since January, concentrated in two
  jurisdictions, is a fact a diligent rollup team will find in an
  afternoon, and it is Vitalik's own objection turned on Swarm: a
  1-of-N network whose N sits in two hosting providers is not yet the
  robustness his post asked for. The pitch must lead with erasure
  coding, pinning, and a plan for geographic spread, not hide it.
- **BZZ volatility** makes a per-GB-year quote unstable. Stamps priced
  by the oracle mitigate; the buyer still sees a floating bill.
- **"DA" is a contested word.** Without §4.1, calling Swarm a DA layer
  overclaims. Say "verifiable archival storage" until receipts are
  exposed and anchored.

## 7. Proposed next steps

1. Post this memo into the 2024-07-10 Slack thread, so Vitalik's
   framing, the 2024 assessment and this formulation live together.
2. A 45-minute call with the GSOC/pub-sub and storage-incentive owners
   on one question only: is a receipt primitive (§4.1) compatible with
   the redistribution game as it stands, and what is the smallest
   version that a contract could verify?
3. A four-week probe, loopmarket-run: mirror one small rollup's blobs
   to Swarm under immutable erasure-coded batches, publish the mapping
   as a bonded assertion, and measure retrieval at one, two and four
   weeks. Output: the §4.4 numbers and a gas benchmark for one BMT
   inclusion proof on Gnosis.
4. File the receipt question upstream as a Bee issue with this memo
   attached, so the design has a public home.

## Sources

- §3.5 substrates and volumes (all read 2026-09-11): Ethereum
  Foundation, "Checkpoint #8", 2026-01-20
  (<https://blog.ethereum.org/2026/01/20/checkpoint-8>) and "Protocol
  priorities update for 2026", 2026-02-18
  (<https://blog.ethereum.org/2026/02/18/protocol-priorities-update-2026>);
  ethereum.org, PeerDAS (<https://ethereum.org/roadmap/fusaka/peerdas/>);
  The Defiant, Glamsterdam 200M gas target
  (<https://thedefiant.io/news/blockchains/ethereum-glamsterdam-final-devnet-200m-gas-limit-target>);
  Base gas limit to 125 Mgas/s and 2026 targets
  (<https://finance.yahoo.com/news/network-increases-gas-limit-125-190944252.html>);
  Arbitrum gas speed limit
  (<https://docs.arbitrum.io/launch-orbit-chain/maintain-your-chain/guidance/state-size-limit>);
  GnosisScan gas tracker (<https://gnosisscan.io/gastracker>); Hedera,
  ConsensusSubmitMessage price update, 2026-01
  (<https://hedera.com/blog/price-update-to-consensussubmitmessage-in-consensus-service-january-2026/>)
  and throttling (<https://hedera.com/blog/throttling-in-hedera-ensuring-stability-and-fairness/>);
  Solana real TPS (<https://cryptobriefing.com/solana-true-tps-surpasses-2500/>);
  DA layer throughput 2026
  (<https://blockeden.xyz/blog/2026/02/24/modular-blockchain-wars-data-availability/>);
  Visa FY2025 (<https://www.electronicpaymentsinternational.com/news/visa-fy25-net-income/>);
  Mastercard Q3 2025
  (<https://www.digitaltransactions.net/a-strong-economy-lifts-mastercards-transaction-volumes-as-well-as-its-top-and-bottom-lines/>);
  Bee `DefaultReserveCapacity`
  (<https://github.com/ethersphere/bee/blob/master/pkg/storer/storer.go>).
- Blob retention and KZG persistence: ChainScore,
  "EIP-4844 blob retention rules"
  (<https://chainscorelabs.com/blog/the-ethereum-roadmap-merge-surge-verge/proto-danksharding/blob-retention-rules-introduced-by-eip-4844>);
  Consensys, "Dencun upgrade part 5, EIP-4844"
  (<https://consensys.io/blog/ethereum-evolved-dencun-upgrade-part-5-eip-4844>).
- History expiry: Ethereum Foundation, "Partial history expiry
  announcement", 2025-07-08
  (<https://blog.ethereum.org/2025/07/08/partial-history-exp>);
  EIP-7927 History Expiry Meta (<https://eips.ethereum.org/EIPS/eip-7927>).
- Celestia pruning window: CIP "Lower data pruning window to 7 days +
  1 hour" (<https://forum.celestia.org/t/cip-lower-data-pruning-window-to-7-days-1-hour/1965>).
- EigenDA retention: Crestal, "Understanding EigenDA: block time, costs,
  data retention"
  (<https://medium.com/@crestalnetwork/understanding-eigenda-key-learnings-on-block-time-costs-and-data-retention-43523dbe2137>);
  EigenDA V2 core architecture
  (<https://blog.eigencloud.xyz/eigenda-v2-core-architecture/>).
- Blob fees: blobscan daily series, global dimension, `avgBlobFee` and
  `avgBlobGasPrice` for 2026-08-10 to 2026-09-08
  (<https://api.blobscan.com/stats/timeseries?timeFrame=30d>, read
  2026-09-09; the same data drives <https://blobscan.com/stats>); fee
  floor rule EIP-7918 (<https://eips.ethereum.org/EIPS/eip-7918>).
  Units: the chart on blobscan.com/stats plots the bare blob gas price
  per unit of blob gas (about 0.006 gwei a day in early September 2026);
  the per-blob dollar figures here use blobscan's `avgBlobFee`, which
  also includes the carrier transaction's execution gas, so they read
  slightly higher than gas price × 131,072. The two do not disagree.
  `scripts/refresh_numbers.py` in this repo pulls every figure in this
  section and the Swarm and price figures in one run.
- Historical DA costs: Conduit, "Data availability costs: Ethereum
  blobs vs. Celestia", 2024-10-23
  (<https://www.conduit.xyz/blog/data-availability-costs-ethereum-blobs-celestia/>);
  BlockEden, Celestia blob economics, 2026-01-16
  (<https://blockeden.xyz/blog/2026/01/16/celestia-blob-economics-data-availability-rollup-costs/>).
- EigenDA payments: "Introducing updated EigenDA pricing", 2024-08-19
  (<https://www.eigenlabs.org/blog/eigenda-updated-pricing/>);
  EigenDA product page, payment-token statement
  (<https://eigencloud.xyz/da>).
- Avail: transaction pricing docs
  (<https://docs.availproject.org/docs/learn-about-avail/tx-pricing>);
  L2BEAT Avail DA listing
  (<https://l2beat.com/data-availability/projects/avail/no-bridge>).
- Token prices, 2026-09-09: CoinGecko simple price API
  (<https://api.coingecko.com/api/v3/simple/price?ids=ethereum,celestia,swarm-bzz,eigenlayer&vs_currencies=usd>).
- Long-term DA competitor: EthStorage mainnet alpha launch post,
  2025-10-14
  (<https://blog.ethstorage.io/ethstorage-mainnet-alpha-launch-petabyte-scale-decentralized-storage-on-ethereum/>);
  EthStorage 2025 annual report
  (<https://blog.ethstorage.io/ethstorage-2025-annual-report/>);
  storage-provider guide, whitelist wording
  (<https://docs.ethstorage.io/storage-provider-guide>); node repository
  (<https://github.com/ethstorage/es-node>).
- Swarm network state: swarmscan API network stats, read 2026-09-09
  (<https://api.swarmscan.io/v1/network/stats>); Swarm Foundation,
  "State of the Network: January 2026"
  (<https://blog.ethswarm.org/foundation/2026/state-of-the-network-january-2026/>).
- Prior art: Vitalik Buterin, "The near and mid-term future of
  improving the Ethereum network's permissionlessness and
  decentralization", 2024-05-17
  (<https://vitalik.eth.limo/general/2024/05/17/decentralization.html>),
  as quoted in the Solar Punk ideabox thread of 2024-07-10.
- Bee push-sync receipts: `pkg/pushsync/pb/pushsync.proto` and
  `pkg/pushsync/pushsync.go` (receipt struct, signing of the chunk
  address, `checkReceipt` overlay and depth check), `pkg/pusher/pusher.go`
  (receipt consumed, chunk reported synced), `pkg/api/tag.go` (only
  counters exposed), all on `ethersphere/bee` `master`, read 2026-09-09;
  staking contract `src/Staking.sol` in `ethersphere/storage-incentives`
  (`stakes[owner].overlay`, `freezeDeposit`, `slashDeposit`);
  `src/Redistribution.sol` in the same repo (commit, reveal, claim;
  `inclusionFunction`, `stampFunction`; freezing on disagreement and
  non-reveal, slashing commented out for a later phase), with Bee's
  `pkg/storer/sample.go` and `pkg/storageincentives/agent.go` for the
  reserve sample and `pkg/storageincentives/redistribution/inclusionproof.go`
  for the claim payload, all read 2026-09-10.
- Swarm facts: loopmarket `docs/plans/P1-federated-book.md` §6 to §7
  (postage economics, feed CAS, network state, erasure coding) and
  `docs/plans/proof-fabric.md` §1 (POT verifier, gas), both with their
  own citations.

---

## Appendix: the rollup vocabulary, for a Swarm audience

Loopmarket's shape is easiest to explain to people who know rollups,
provided the one inversion is stated.

- **Rollup-like for reads.** Full state off-chain in a canonical trie,
  a 32-byte root anchored on chain, a contract that accepts claims only
  with proofs against that root. Because the bytes go to Swarm rather
  than into Ethereum calldata, the closest named variant is a
  *validium*, and it inherits the validium's known weakness: if the
  data layer loses the bytes, the root is unverifiable. §4 is about
  closing that weakness.
- **An ordinary contract for the one write.** In a rollup the state
  transition happens off-chain and the contract verifies a proof of it.
  In loopmarket the contract performs the decisive transition itself:
  it checks per-leg inclusion and fill-absence proofs and records the
  fills. Everything else in the book, offers and tombstones, is speech
  that needs no chain at all.
- **Solvers as permissionless sequencing.** A rollup sequencer picks
  the next batch. Solvers do that job here, in competition, sealed, with
  a deterministic selection deciding whose batch wins and one clearing
  commit per beat. That resembles based or shared sequencing more than
  a single operator, and it is why two incompatible proposals in one
  block never race: selection resolves them before anything reaches the
  contract.
- **Optimistic pieces where proofs run out.** Re-execution certificates
  are closer to fraud-proof-style re-execution than to validity proofs.
  Settlement, the makers actually delivering, is adjudicated
  optimistically through factbond's bonded assertions and challenge
  windows, because no proof can settle "did the lesson happen".
- **Not a sidechain.** Loopmarket runs no consensus of its own; it
  borrows Gnosis's ordering and finality. Swarm likewise runs no
  consensus for availability, which is exactly why §4.1's receipts need
  a chain anchor to say *when*.
