"""Forum (social) environment — the social-information-diffusion layer.

Models a single per-experiment forum where agents can **post**, **read**,
**comment**, and **follow** other posters. This is the social channel that
lets information / sentiment spread between agents (cf. OASIS social
simulation); for a prediction market it captures herding, rumour spread
and peer imitation that a pure order-book cannot.

Design / reproducibility notes
------------------------------
- **State is plain data** (dataclasses + lists/dicts/sets), so a `Forum`
  instance pickles cleanly. The `Forum` is attached to `Simulation.forum`,
  therefore the existing checkpoint pickle of the whole `Simulation`
  (see `runner/checkpoint.py`) automatically captures the forum, and a
  resumed run keeps every post/comment/follow.
- **The *mechanism* is deterministic**: post/comment ids are assigned by a
  monotonic counter, and `read()` ranking is a fully deterministic sort
  (follow-priority, then recency, then id as a stable tiebreak). The *text
  content* of posts/comments is produced by the LLM, so it is NOT
  bit-for-bit reproducible across runs — but the structure, ordering and
  diffusion graph are. Logging each forum action (runner events) preserves
  auditability of what was actually written.
- The forum imposes **no per-tick rate limit itself**; the bound on how
  many social actions an agent may take per tick (`K_social`) is enforced
  in the decision runtime so the forum stays a passive store.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Post:
    """A top-level forum post authored by one agent at a given tick."""
    id: int
    author_id: int
    tick: int
    content: str
    # ids of comments attached to this post, in creation order.
    comment_ids: list[int] = field(default_factory=list)


@dataclass
class Comment:
    """A reply attached to a Post."""
    id: int
    post_id: int
    author_id: int
    tick: int
    content: str


@dataclass
class Forum:
    """Per-experiment social board. One instance lives on
    `Simulation.forum`.

    Attributes
    ----------
    posts:
        all top-level posts, in creation (id) order.
    comments:
        all comments, in creation (id) order.
    follows:
        ``agent_id -> set(followed_agent_id)``. A follow is one-directional
        (like Twitter), used only to *prioritise* whose posts an agent
        sees in its feed; it never hides non-followed content.
    """
    posts: list[Post] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    follows: dict[int, set[int]] = field(default_factory=dict)
    # Monotonic id counters; kept on the instance so they survive pickle
    # and never reissue an id after a resume.
    _next_post_id: int = 0
    _next_comment_id: int = 0

    # -- writes ---------------------------------------------------------

    def post(self, author_id: int, content: str, tick: int) -> Post:
        """Append a new top-level post and return it."""
        p = Post(
            id=self._next_post_id, author_id=int(author_id),
            tick=int(tick), content=str(content),
        )
        self._next_post_id += 1
        self.posts.append(p)
        return p

    def comment(
        self, author_id: int, post_id: int, content: str, tick: int,
    ) -> Comment | None:
        """Attach a comment to an existing post. Returns the Comment, or
        None if `post_id` does not exist (so the runtime can report a
        no-op back to the LLM instead of corrupting state)."""
        parent = self.get_post(post_id)
        if parent is None:
            return None
        c = Comment(
            id=self._next_comment_id, post_id=int(post_id),
            author_id=int(author_id), tick=int(tick), content=str(content),
        )
        self._next_comment_id += 1
        self.comments.append(c)
        parent.comment_ids.append(c.id)
        return c

    def follow(self, agent_id: int, target_id: int) -> bool:
        """`agent_id` starts following `target_id`. Self-follows and
        duplicate follows are no-ops. Returns True if a NEW follow edge
        was created."""
        agent_id, target_id = int(agent_id), int(target_id)
        if agent_id == target_id:
            return False
        followed = self.follows.setdefault(agent_id, set())
        if target_id in followed:
            return False
        followed.add(target_id)
        return True

    # -- reads ----------------------------------------------------------

    def get_post(self, post_id: int) -> Post | None:
        for p in self.posts:
            if p.id == int(post_id):
                return p
        return None

    def followed_by(self, agent_id: int) -> set[int]:
        return set(self.follows.get(int(agent_id), set()))

    def read(
        self, agent_id: int, limit: int = 5, *, prioritize_followed: bool = True,
    ) -> list[Post]:
        """Return up to `limit` posts for `agent_id`'s feed.

        Ranking (deterministic):
          1. exclude the agent's own posts (it already has those in memory),
          2. if `prioritize_followed`, posts by followed authors rank above
             everyone else's,
          3. within each band, most-recent tick first,
          4. higher post id first as a stable tiebreak.

        This makes followed authors the primary diffusion channel while
        still surfacing recent "trending" posts from the wider crowd.
        """
        followed = self.followed_by(agent_id)
        candidates = [p for p in self.posts if p.author_id != int(agent_id)]

        def sort_key(p: Post) -> tuple:
            is_followed = 1 if (prioritize_followed and p.author_id in followed) else 0
            # negate so that "higher" sorts first under ascending sort
            return (-is_followed, -p.tick, -p.id)

        candidates.sort(key=sort_key)
        return candidates[: max(0, int(limit))]

    def get_feed_for(self, agent_id: int, limit: int = 5) -> list[Post]:
        """Alias for `read` with follow-prioritisation on (the feed the
        agent would see when it opens the forum)."""
        return self.read(agent_id, limit=limit, prioritize_followed=True)

    def comments_for(self, post_id: int, limit: int = 3) -> list[Comment]:
        """Most-recent comments on a post (recency-desc, id tiebreak)."""
        rows = [c for c in self.comments if c.post_id == int(post_id)]
        rows.sort(key=lambda c: (-c.tick, -c.id))
        return rows[: max(0, int(limit))]
