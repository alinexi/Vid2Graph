"""Pre-seeded demo graph: a (synthetic) interview with a distributed-systems engineer.

It demonstrates all three layers, multi-timestamp merged nodes, difficulty levels and
relation edges — and the reference scenario at 14:15 ("Split-Brain … Paxos → Raft").
The transcript is fictional and written for this demo; it is not a real recording.
"""
from __future__ import annotations

from app.core.config import settings
from app.db.database import Database
from app.models.schemas import Chunk, Edge, Graph, Mention, Node, TranscriptSegment
from app.pipeline.chunker import chunk_transcript
from app.pipeline.extractor import is_youtube, youtube_id

DEMO_ID = "demo-distributed-systems"

# (start_seconds, text) — ends are derived from the next start.
_SCRIPT: list[tuple[int, str]] = [
    (0, "Welcome back to the show. Today I'm sitting down with a staff engineer who spent the last six years running the storage platform at a payments company."),
    (12, "Thanks for having me. I'm excited to talk about the boring parts of infrastructure, because the boring parts are where the outages live."),
    (24, "Let's start with the big picture. What does your platform actually do?"),
    (31, "At its core we run a replicated key-value store that every service depends on for configuration, leases, and coordination. Think of it as the thing that answers who is the leader right now."),
    (49, "So when people say coordination service, that's the role you play."),
    (55, "Exactly. Leader election, distributed locks, service discovery. If we are down, nothing can safely agree on anything."),
    (68, "I want to get into the migration story, but first, what did the original architecture look like?"),
    (76, "The original system was a home-grown implementation of Multi-Paxos. It was written by two very smart people who both left within a year of each other."),
    (92, "Classic."),
    (95, "And the thing with Paxos is that the paper describes a single-decree protocol. Everything you need for a real log, the leader lease, log compaction, membership changes, is left as an exercise for the reader."),
    (116, "So you had this bespoke protocol that nobody fully understood any more."),
    (121, "Right. We had a system that worked, mostly, but every time we touched it we were scared. There was no spec beyond the code."),
    (135, "Let's talk about replication. How did writes flow through the old system?"),
    (142, "A client sends a write to whichever node it thinks is the leader. The leader proposes it, and it needs acknowledgements from a majority of the cluster before it's committed. Classic majority quorum."),
    (162, "And with five nodes that means three acks."),
    (166, "Three acks, yes. That's the whole trick: any two majorities overlap in at least one node, so you can never commit two conflicting values. That overlap is the entire safety argument."),
    (185, "Where did it go wrong?"),
    (190, "Our first serious incident was a network partition between two racks. The switch misbehaved and we ended up with two groups of nodes that could each talk internally but not to each other."),
    (209, "And each side thought the other side was dead."),
    (214, "Each side thought the other side was dead, and because of a bug in how we handled lease expiry, both sides elected a leader. Two leaders, both accepting writes."),
    (232, "That's the nightmare."),
    (236, "That's the nightmare. We later learned to call it by its proper name, but at the time we just called it the Tuesday incident."),
    (250, "How do you even detect that two leaders exist?"),
    (256, "We didn't, not quickly. The symptom was clients seeing writes disappear. A write would be acknowledged on one side and then overwritten when the partition healed and the logs were reconciled."),
    (276, "So data loss, essentially."),
    (280, "Effectively, yes. We added fencing tokens after that. Every leader term gets a monotonically increasing number and downstream systems reject anything from a stale term."),
    (298, "Fencing tokens are the thing Martin Kleppmann wrote about with the lock service example, right?"),
    (305, "That's the one. The storage layer must be the thing that enforces it, otherwise a paused process can wake up with an expired lease and still do damage."),
    (322, "Let's move to observability. What did you instrument?"),
    (328, "The most useful metric turned out to be commit latency at the ninety-ninth percentile, broken down by term. Whenever a term changed we would see a latency cliff, and that told us elections were happening too often."),
    (350, "Too many elections means your heartbeat timeouts are tuned badly?"),
    (355, "Usually. Our heartbeat interval was a hundred milliseconds and the election timeout was three hundred, which sounds fine until garbage collection pauses the leader for four hundred milliseconds."),
    (374, "So the followers think the leader is gone and start an election."),
    (378, "And then the old leader comes back and discovers it was deposed. Nothing unsafe, but it's a thundering herd of client retries every time."),
    (392, "We've been talking for a while about the old system. Walk me through the decision to migrate."),
    (400, "It came down to understandability. When we evaluated alternatives, the strongest argument was that we could explain the protocol to a new hire in an afternoon."),
    (418, "And that pointed you at Raft."),
    (422, "It pointed us at Raft. Raft is designed around understandability. There's one leader, the log flows one direction, and the rules for who can become leader are simple: you need the most up-to-date log."),
    (443, "How long did the migration take?"),
    (447, "About nine months end to end. The hardest part wasn't the protocol, it was doing it with zero downtime for a service that everything depends on."),
    (463, "Did you look at just adopting etcd or ZooKeeper instead of writing your own Raft?"),
    (470, "We did. We ended up using an existing Raft library and building our state machine on top of it rather than taking a whole system, because our data model and our client protocol were already baked into hundreds of services."),
    (492, "Let's take a short break and then dig into the incident that really forced the decision."),
    (500, "Sounds good."),
    (720, "Okay, we're back. Before the break you hinted there was one incident that made the migration non-negotiable."),
    (731, "Yeah. So the honest version of the story is that the rewrite was on the roadmap for two years and kept getting pushed."),
    (745, "Until?"),
    (748, "Until the second partition. The first one, the Tuesday incident, we patched. The second one hit during a deploy and the patch didn't cover it."),
    (762, "What was different?"),
    (766, "The difference was that membership was changing at the same time. We were adding a sixth node, and our hand-rolled membership change had a window where the old and new configurations disagreed on what a majority was."),
    (786, "That's the joint consensus problem."),
    (790, "It's exactly the thing joint consensus exists to solve, and we had just not implemented it correctly."),
    (800, "I'm going to let you say the line."),
    (855, "We ran into Split-Brain issues in production early on, so we had to migrate from Paxos to Raft to achieve reliable consensus."),
    (860, "The Raft migration itself kicked off the following quarter. We started by running the Raft cluster as a shadow, replaying every committed entry from the old log, and diffing the state machines nightly."),
    (882, "And when did you cut over?"),
    (887, "We flipped reads first, served from the Raft replicas, and compared results for three weeks. Then we moved writes with a kill switch that could flip back in seconds. Nobody ever had to use it."),
    (910, "Did anything about Raft surprise you once it was in production?"),
    (917, "Log compaction. Snapshotting a multi-gigabyte state machine while still serving traffic is where most of the engineering actually went. The consensus part is maybe a fifth of the code."),
    (937, "People underestimate that."),
    (941, "Everyone underestimates that. Also, linearizable reads: if you want a read to reflect the latest committed write you still have to go through the leader or use a read index, and that costs a round trip."),
    (962, "Let's talk about testing. How do you gain confidence in something like this?"),
    (969, "Deterministic simulation. We run the whole cluster in a single process with a simulated network and a seeded random scheduler, and we inject partitions, delays, clock skew, disk failures, all of it."),
    (990, "Like the FoundationDB approach."),
    (994, "Very much inspired by FoundationDB, and by Jepsen for the black-box side. Jepsen found a bug in our read path during the shadow period, which was humbling and extremely useful."),
    (1012, "What's the bug?"),
    (1016, "A follower could serve a stale read right after a leader change because it hadn't learned the new commit index yet. Textbook, and we still shipped it."),
    (1032, "Let's zoom out. If someone is building a coordination service today, what do you tell them?"),
    (1040, "Don't. Use etcd. But if you must, write the invariants down before the code, test with simulation from day one, and assume the network will partition at the worst possible moment."),
    (1060, "And the clocks?"),
    (1063, "Never trust the clocks. Clock skew between nodes is real, NTP drifts, virtual machines get paused. Any lease logic has to tolerate a process sleeping for seconds."),
    (1080, "We're almost out of time. One more thing: Byzantine faults. Do you worry about them?"),
    (1088, "Not in a datacenter you control. Raft and Paxos both assume crash faults, not malicious nodes. If you need Byzantine tolerance you're in a different world with different protocols and three times the replicas."),
    (1110, "That's a great place to end. Thank you so much."),
    (1115, "Thank you, this was fun."),
    (1120, "That's it for today's episode. If you enjoyed it, share it with someone who is about to write their own consensus protocol, and talk them out of it."),
]


def _segments() -> list[TranscriptSegment]:
    segs = []
    for i, (start, text) in enumerate(_SCRIPT):
        end = _SCRIPT[i + 1][0] - 0.5 if i + 1 < len(_SCRIPT) else start + 8
        segs.append(TranscriptSegment(id=i, start=float(start), end=float(end), text=text))
    return segs


def _mention(segs: list[TranscriptSegment], second: int, chunks: list[Chunk]) -> Mention:
    seg = next((s for s in segs if s.start <= second <= s.end), None)
    chunk = next((c for c in chunks if c.start <= second <= c.end), None)
    return Mention(start=float(second), end=seg.end if seg else None,
                   snippet=(seg.text if seg else "")[:220], chunk_id=chunk.id if chunk else None)


def build_demo_graph() -> Graph:
    segs = _segments()
    chunks = chunk_transcript(segs, window_minutes=6, overlap_seconds=45)

    def N(id_: str, label: str, layer: str, difficulty: str, eli5: str, summary: str = "",
          mentions: list[int] = (), aliases: list[str] = (), inferred_from: list[str] = ()) -> Node:  # noqa: N802
        ms = [_mention(segs, s, chunks) for s in mentions]
        return Node(id=id_, label=label, layer=layer, difficulty=difficulty, eli5=eli5, summary=summary,
                    mentions=ms, chunk_ids=sorted({m.chunk_id for m in ms if m.chunk_id}),
                    aliases=list(aliases), inferred_from=list(inferred_from))

    nodes = [
        # ── Blue: core concepts (explicitly discussed) ───────────────────────
        N("core_raft_migration", "Team Migration to Raft", "core", "intermediate",
          "The team replaced their hand-written Paxos system with Raft, a consensus algorithm built to be easy to understand. They ran both side by side, compared results, then switched over gradually.",
          "The central story of the interview: a nine-month, zero-downtime move from home-grown Multi-Paxos to a Raft library, motivated by understandability and two partition incidents.",
          mentions=[400, 422, 447, 860, 887]),
        N("core_leader_election", "Leader Election", "core", "intermediate",
          "A group of servers vote on which one is in charge. If the boss stops answering, the others hold a new vote. Raft picks the candidate with the most up-to-date log.",
          "Discussed as the cluster's core job and the source of latency cliffs when elections happen too often.",
          mentions=[55, 374, 422]),
        N("core_log_replication", "Log Replication", "core", "intermediate",
          "Every change is written as an entry in an ordered list (the log). The leader copies new entries to followers, and once most have it, the entry is permanent.",
          "The write path: leader proposes, majority acknowledges, entry is committed.",
          mentions=[142, 166, 860]),
        N("core_fencing_tokens", "Fencing Tokens", "core", "advanced",
          "Each new leader gets a bigger number than the last. Storage systems refuse anything stamped with an old number, so a confused ex-leader cannot do damage.",
          "Introduced after the first partition incident so stale leaders are rejected downstream.",
          mentions=[280, 298, 305]),
        N("core_heartbeat_timeouts", "Heartbeat & Election Timeouts", "core", "intermediate",
          "The leader sends a regular 'I'm alive' ping. If followers miss enough pings they assume it died and start an election. Tuning these timers badly causes needless elections.",
          "GC pauses longer than the election timeout caused spurious elections and client retry storms.",
          mentions=[350, 355, 378]),
        N("core_log_compaction", "Log Compaction & Snapshots", "core", "advanced",
          "The log grows forever, so periodically you take a photo of the current state (a snapshot) and throw away the old entries. Doing this without pausing traffic is hard.",
          "Called out as where most of the real engineering effort went.",
          mentions=[917]),
        N("core_deterministic_simulation", "Deterministic Simulation Testing", "core", "advanced",
          "Run the entire cluster inside one program with a fake network and a fixed random seed, so you can replay any failure exactly and find bugs before production.",
          "The team's main testing strategy, inspired by FoundationDB.",
          mentions=[969, 994]),
        N("core_zero_downtime_migration", "Shadow Cluster Cut-over", "core", "intermediate",
          "Run the new system next to the old one, feed it the same data, compare answers, then switch readers and finally writers with a quick way to switch back.",
          "The migration strategy: shadow replay, read cut-over, write cut-over with a kill switch.",
          mentions=[860, 887]),
        # ── Orange: dropped jargon (mentioned, never explained) ──────────────
        N("jargon_split_brain", "Split-Brain", "jargon", "intermediate",
          "Imagine two managers who each think the other quit, so both start giving orders. In a cluster, a network break can make two groups each elect their own leader, and they accept conflicting writes.",
          "Named at 14:15 as the production failure that forced the migration; described (without the name) during the Tuesday incident.",
          mentions=[855]),
        N("jargon_paxos", "Paxos", "jargon", "advanced",
          "A famous recipe for getting unreliable computers to agree on a value. Proven correct but notoriously hard to turn into a real system.",
          "The original home-grown protocol; criticised for leaving leases, compaction and membership as 'an exercise for the reader'.",
          mentions=[76, 95, 855, 1088], aliases=["Multi-Paxos"]),
        N("jargon_network_partition", "Network Partition", "jargon", "beginner",
          "A network failure that splits a cluster into islands that cannot talk to each other, even though every machine is still running.",
          "The trigger for both incidents.",
          mentions=[190, 748, 1040]),
        N("jargon_joint_consensus", "Joint Consensus", "jargon", "advanced",
          "A safe way to change which servers are in the cluster: for a short time, decisions must be approved by BOTH the old and new membership, so there is never a gap.",
          "The mechanism the team had mis-implemented, causing the second partition incident.",
          mentions=[786, 790]),
        N("jargon_linearizable_reads", "Linearizable Reads", "jargon", "advanced",
          "A read that is guaranteed to see the newest write, as if there were only one copy of the data. Costs an extra round trip in Raft.",
          "Mentioned as a production surprise and the source of the Jepsen-found bug.",
          mentions=[941, 1016]),
        N("jargon_jepsen", "Jepsen", "jargon", "intermediate",
          "A black-box testing tool that hammers a database while breaking the network, then checks whether it lied about its guarantees.",
          "Found a stale-read bug during the shadow period.",
          mentions=[994]),
        N("jargon_etcd", "etcd", "jargon", "beginner",
          "A popular open-source key-value store built on Raft; the default coordination service for Kubernetes.",
          "Recommended as the thing to use instead of writing your own.",
          mentions=[463, 1040]),
        N("jargon_zookeeper", "ZooKeeper", "jargon", "beginner",
          "An older coordination service from the Hadoop world, using its own protocol (ZAB) rather than Raft.",
          mentions=[463]),
        N("jargon_foundationdb", "FoundationDB", "jargon", "intermediate",
          "A distributed database famous for testing itself with deterministic simulation years before it was fashionable.",
          mentions=[990, 994]),
        N("jargon_clock_skew", "Clock Skew", "jargon", "beginner",
          "Different machines' clocks disagree, sometimes by seconds. Any logic that says 'this lease expires at time T' has to survive that.",
          mentions=[969, 1063]),
        N("jargon_byzantine", "Byzantine Faults", "jargon", "advanced",
          "Failures where a node doesn't just crash but actively lies. Raft and Paxos do not handle this; blockchains and BFT protocols do, at much higher cost.",
          mentions=[1080, 1088], aliases=["Byzantine Fault Tolerance", "BFT"]),
        N("jargon_leases", "Leader Lease", "jargon", "intermediate",
          "A time-limited permission to act as leader. When it expires you must stop, even if nobody told you to.",
          mentions=[95, 214, 305, 1063]),
        # ── Purple: implicit prerequisites (never named in the video) ────────
        N("prereq_consensus", "Distributed Consensus", "prerequisite", "intermediate",
          "Getting several computers to agree on one answer even when some crash or messages are lost. It is the problem that Paxos and Raft both solve.",
          inferred_from=["jargon_split_brain", "jargon_paxos", "core_raft_migration"]),
        N("prereq_quorum", "Quorum", "prerequisite", "beginner",
          "A majority. With five servers, three must agree. Any two majorities share at least one server, which is what prevents two different decisions.",
          inferred_from=["jargon_split_brain", "core_leader_election", "core_log_replication"]),
        N("prereq_state_machine_replication", "State Machine Replication", "prerequisite", "intermediate",
          "If every server starts in the same state and applies the same commands in the same order, they all end up identical. The log is the list of commands.",
          inferred_from=["core_log_replication", "core_log_compaction"]),
        N("prereq_cap", "CAP Theorem", "prerequisite", "beginner",
          "During a network partition a system must choose: keep answering (availability) or stay correct (consistency). Coordination services choose consistency.",
          inferred_from=["jargon_network_partition", "jargon_linearizable_reads"]),
        N("prereq_failure_detection", "Failure Detection", "prerequisite", "beginner",
          "You cannot tell a crashed computer from a slow one. Timeouts are a guess, and every guess can be wrong in both directions.",
          inferred_from=["core_heartbeat_timeouts", "jargon_split_brain"]),
        N("prereq_crash_vs_byzantine", "Fault Models", "prerequisite", "intermediate",
          "Protocols are proven under assumptions about how things fail: crash-stop, crash-recovery, or Byzantine. Picking the wrong model voids the proof.",
          inferred_from=["jargon_byzantine", "jargon_paxos"]),
    ]

    E = lambda s, t, r: Edge(id=f"e_{s}_{t}", source=s, target=t, relation=r)  # noqa: E731
    edges = [
        # prerequisite_for (purple → others)
        E("prereq_consensus", "jargon_split_brain", "prerequisite_for"),
        E("prereq_consensus", "jargon_paxos", "prerequisite_for"),
        E("prereq_consensus", "core_raft_migration", "prerequisite_for"),
        E("prereq_quorum", "jargon_split_brain", "prerequisite_for"),
        E("prereq_quorum", "core_leader_election", "prerequisite_for"),
        E("prereq_quorum", "core_log_replication", "prerequisite_for"),
        E("prereq_state_machine_replication", "core_log_replication", "prerequisite_for"),
        E("prereq_state_machine_replication", "core_log_compaction", "prerequisite_for"),
        E("prereq_cap", "jargon_network_partition", "prerequisite_for"),
        E("prereq_cap", "jargon_linearizable_reads", "prerequisite_for"),
        E("prereq_failure_detection", "core_heartbeat_timeouts", "prerequisite_for"),
        E("prereq_failure_detection", "jargon_split_brain", "prerequisite_for"),
        E("prereq_crash_vs_byzantine", "jargon_byzantine", "prerequisite_for"),
        E("prereq_crash_vs_byzantine", "jargon_paxos", "prerequisite_for"),
        # the reference scenario
        E("jargon_split_brain", "core_raft_migration", "leads_to"),
        E("jargon_paxos", "core_raft_migration", "compared_with"),
        E("jargon_network_partition", "jargon_split_brain", "leads_to"),
        E("jargon_joint_consensus", "core_raft_migration", "part_of"),
        # the rest of the story
        E("core_leader_election", "core_raft_migration", "part_of"),
        E("core_log_replication", "core_raft_migration", "part_of"),
        E("core_heartbeat_timeouts", "core_leader_election", "uses"),
        E("jargon_leases", "core_leader_election", "uses"),
        E("jargon_leases", "core_fencing_tokens", "related_to"),
        E("core_fencing_tokens", "jargon_split_brain", "contrasts_with"),
        E("core_log_compaction", "core_raft_migration", "part_of"),
        E("core_zero_downtime_migration", "core_raft_migration", "part_of"),
        E("core_deterministic_simulation", "core_raft_migration", "uses"),
        E("jargon_foundationdb", "core_deterministic_simulation", "example_of"),
        E("jargon_jepsen", "jargon_linearizable_reads", "related_to"),
        E("jargon_clock_skew", "jargon_leases", "related_to"),
        E("jargon_etcd", "core_raft_migration", "compared_with"),
        E("jargon_zookeeper", "jargon_etcd", "compared_with"),
        E("jargon_byzantine", "jargon_paxos", "contrasts_with"),
    ]

    media_kind, media_url, source_url = "none", None, None
    demo_media = settings.demo_media_url.strip()
    if demo_media and is_youtube(demo_media) and youtube_id(demo_media):
        media_kind, media_url, source_url = "youtube", youtube_id(demo_media), demo_media

    g = Graph(
        id=DEMO_ID,
        title="From Paxos to Raft: Surviving Split-Brain in Production",
        description=("Demo graph. A fictional engineering interview about migrating a coordination service from "
                     "home-grown Multi-Paxos to Raft after two network-partition incidents. Click the orange "
                     "Split-Brain node to jump to 14:15."),
        source_type="demo", source_url=source_url, media_kind=media_kind, media_url=media_url,
        duration=float(segs[-1].end), language="en", status="ready", model_used="hand-curated demo",
        is_demo=True, transcript=segs, chunks=chunks, nodes=nodes, edges=edges,
    )
    g.recompute_stats()
    return g


def seed_if_missing(db: Database, force: bool = False) -> bool:
    if db.demo_exists() and not force:
        return False
    db.save_graph(build_demo_graph())
    return True
