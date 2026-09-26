# Follow-up plan: acim.org source URLs for references

## Context

Deferred from the canonical-reference work. The reviewer wanted a `source_url` alongside
the canonical citation (`reference: T-4.in.1:3`, `source_url:
https://acim.org/acim/chapter-4/introduction/en/s/79?wid=toc`), kept as separate fields so
the reference is the semantic citation and the URL is just a locator.

**Why deferred:** the URL is not derivable from the corpus. acim.org blocks automated
fetch (HTTP 403), and the path's `/s/79` segment plus `?wid=` parameter are opaque — not a
function of chapter/section/paragraph we can compute. There is no URL data stored anywhere
in the corpus today (confirmed: no `url` field on `Source`, none in the markdown
frontmatter or `corpus.jsonl`).

## Options to resolve the mapping (pick when picked up)

1. **Curated mapping table** `reference -> url`, stored as data (e.g.
   `data/acim/urls.jsonl`) and joined at load time. Needs sourcing the `/s/<n>` ids —
   manual, or from a licensed/exported dataset from the Foundation for Inner Peace.
   Predictable and verifiable, but a real data-gathering task.
2. **Constructed path without the opaque id** — build
   `acim.org/acim/chapter-4/introduction/en/...` from our fields and the frontmatter
   spelled-out titles, omitting `/s/<n>`. Risk: may 404 or resolve to the wrong anchor, and
   we cannot verify (site blocks fetch). Not recommended without a way to check.
3. **Link to a fetchable mirror** whose URL scheme *is* derivable from the canonical
   reference (some ACIM text mirrors key off `T-4.in.1` directly). Changes the destination
   but gives a reliable, computable link.

## Shape (once a mapping exists)

- Add `source_url: str | None = None` to `Source` (`src/domain/sources/models.py`) —
  backward-compatible defaulted field.
- Populate in `sources_acim.py` loader (from the mapping table or constructed path).
- Add `source_url: str | None` to `ClaimResult` / `CitedClaim`, plumb like `reference`.
- Web: make the `.cited-source` chip a link when `source_url` is present; plain text
  otherwise. Keep the canonical `reference` as the visible label either way.

## Open questions

- Is a licensed/exported acim.org URL dataset obtainable, or is this manual? That decides
  option 1's feasibility.
- Should the link open the paragraph or the specific sentence? The `:sentence` part of the
  reference may not have a distinct anchor on the destination.
- Verify any chosen scheme against a handful of known references before trusting it (the
  site blocking fetch means this is a manual spot-check).
