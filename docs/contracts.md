# NoSpoilers contracts and implementation decisions

## Scope and assumptions

One user, one local Python application, SQLite, no cloud account required. The supplied repository was empty apart from README/license and contained no Jev implementation. The user authorized routine choices and uninterrupted implementation. Existing cloud tasks are already isolated: use this checkout, do not create a worktree unless explicitly requested.

Alternatives considered: a framework/database stack would add deployment and dependency work with no benefit for this local MVP; an external model on each pick would add latency and repeated narrative handling. The chosen standard-library server uses preprocessed private features. Browser styling is entirely local; no external fonts, images, trailers, analytics, or scripts.

## JSON import v1

Top-level exact fields: `version: 1`, `mode: "real" | "demo"`, `movies: []`, optional `history: []`. Maximum 10,000 movies and 20 MB through the CLI. Validation precedes a single SQLite transaction, so malformed records cannot partially import. Duplicate movie/history IDs within one payload are rejected. Existing rows merge by `(mode, id)`. Public text is bounded, rendered as text, and never interpreted as HTML.

A movie has these allowed fields:

| Field | Meaning |
| --- | --- |
| `id` | Required namespaced stable ID, e.g. `local:your-id`, `tmdb:123`. Namespace is lowercase letters/digits/underscore/hyphen, starting with a letter; suffix allows letters/digits/underscore/dot/hyphen. |
| `title`, `year` | Required identifying title (1–200 characters) and integer year (1880–2200). |
| `runtime` | Optional positive integer minutes (1–1000), or null/omitted for unknown. |
| `source_ids` | Optional object mapping source name to string ID; retained privately as explicit identity mappings. |
| `availability` | Optional list of offers; no entries means unknown. |
| `private` | Optional private profile; omission means unknown features. |

An offer has exact fields `region` (two uppercase letters), `provider` (name), `access_type` (`included`, `rent`, `buy`, `free`, `ads`), `source`, `checked_at` (ISO timestamp with time zone), and optional `url`. Invalid times are rejected. Offers expire after **7 days**, including exactly 7 days; future timestamps are unusable until their time arrives. Import and TMDB refresh are explicit; there is no background freshness assumption.

Configured link policy currently accepts only `source: "tmdb"` with HTTPS host exactly `www.themoviedb.org`, path `/movie/<positive ID>/watch`, optional sole query parameter `locale=<offer region>`, and no fragments/user info/port. Imported offers with other URLs may inform availability constraints but never become clickable links. Source metadata is trusted only to the extent the authorized importer/source is trusted. No fabricated offers exist for fictional titles. Stale/unverified links are omitted.

Private profile exact allowed fields:

- `schema_version: 1` and `features`: **all six** keys below, numeric 0–1 or `null` for unknown; booleans, infinities and NaN are rejected.
- `source_text`: optional authorized text, at most 100,000 characters. `source_refs`: optional list of source references.
- `missing`: optional list of missing-data indicators. Unknown feature values themselves are authoritative.
- `provenance`: required object, recording source evidence versus derived/fixture interpretation, source/extractor/model/prompt versions as applicable. Imported provenance is private, not proof of accuracy.

| Feature | 0 | 1 |
| --- | --- | --- |
| pace | Deliberate | Fast |
| warmth | Cool | Warm |
| intensity | Gentle | Intense |
| character | Little character emphasis | Strong character emphasis |
| wonder | Grounded | Wonder-focused |
| closure | Open | Resolved |

These compact dimensions are implementation choices, not learned model weights. Narrative properties can be spoiler-bearing and remain private. Incompatible schema versions are rejected on import and extraction; re-extract using a compatible version. No inferred preferences or fabricated source material fill missing values.

History entry exact fields: `id`, optional `rating` (`liked`, `neutral`, `disliked`, or null), optional `notes` (up to 2,000 chars), optional `watched` (must be true). History IDs must resolve to existing or simultaneously imported movie records. Imports retain watched movie profiles. Set null to record watched-but-unrated. Upsert replaces the title’s current rating; it never adds a second vote. Watched status is independent of rating. Notes are user data, not selector instructions; the reference ranker does not interpret them.

`examples/demo.json` contains 12 fictional films with private fixture profiles, and no reactions or real streaming offers. `examples/demo-history.json` contains three separately opt-in synthetic reactions and requires those IDs to exist. `examples/import-template.json` starts a real catalog with unknown features. Do not substitute synthetic history for the real profile.

## Selection and session state

Constraints are stored independently per mode: `max_runtime` (nullable), `region` (default US), `providers` (default empty), `access_types` (default included), bounded `mood` (null/calm/bright/absorbing), `show_runtime`, `show_availability`.

Eligibility is ordinary application code. It excludes watched IDs, this session’s temporary exclusions, runtime over the limit or unknown under a limit, and missing/stale/mismatched offers under a hard provider constraint. Region, access type and provider must match the **same** fresh offer. Empty providers explicitly means unrestricted catalog; unknown availability is then allowed and labeled, with no unverified link. No constraint is silently relaxed.

The browser’s HttpOnly SameSite session cookie identifies separate `offered` and `exclusions` records. Another-one requests must reference an ID offered to that session/mode. These never update history. Explicit reset clears temporary exclusions; changed cookies make a fresh session. The profile’s ratings and notes persist across server restarts. Decision records retain private feature/preference/constraint snapshots and schema/backend/fallback/elapsed time for reproducibility, without copying narrative text.

The reusable Python selector receives `select(preference, candidates, mood)`. Candidates contain only IDs and versioned private feature profiles, not titles or story text. Preferences contain compatible rated examples and signed weights: liked +1, neutral 0, disliked −1. Unknown dimensions are excluded pairwise. For each candidate, compute mean `weight × (1 − mean absolute difference)` over comparable examples. With a mood and features, mix 80% rating score and 20% mood closeness; if no comparable ratings exist use mood alone. Mood target dimensions are declared in `core.MOODS` (calm: pace/intensity 0.2; bright: warmth 0.9, wonder 0.8; absorbing: character 0.9, intensity 0.7). Highest score wins; ascending stable ID breaks ties. No random state or claimed confidence. No ratings/no mood: unpersonalized stable-ID starting pick. Ratings with no compatible features: explicitly unpersonalized. Personalized/mood selection with no comparable candidate information: abstain.

Exact output: `{"id":"one-of-the-input-IDs"}` or `{"abstain":"insufficient_information|no_acceptable_candidate|inference_error"}` (one reason string, not the literal pipe notation). Every other field, prose, invalid type, and out-of-set ID is rejected. Recheck current eligibility before presentation. Failures become fixed neutral messages. Reference fallback is opt-in and persisted in diagnostics.

### Future Jev command bridge

No real Jev dependency is installed or verified. Missing prerequisite: an actual Jev implementation/checkpoint or callable API plus its input/option schema, context limits, runtime/inference requirements, and access if needed. `CommandSelector` is a narrow adapter protocol for the integrator, not an invented Jev API.

A configured executable reads one JSON object on stdin with `schema_version`, `preference`, `mood`, `candidates` (flat `{id,features}` profiles), `criteria`, and explicit `permitted_outcomes`. It returns exactly one decision JSON object on stdout. No shell execution. A 30-second timeout, nonzero exit, malformed JSON, excessive stdout (>1 MB after capture), or invalid result yields bounded failure. stderr is captured and never echoed. Trust only executables you control; command execution is an explicit developer operation. Output capture is not an OS sandbox or hard resource quota.

An explicit capacity is required. The bridge takes the first N eligible IDs in ascending order, then validates within that shortlist. This deterministic policy can bias recommendations, and has **not** been evaluated against a real Jev or genuine feedback. Reference selection uses the full eligible set. A fabricated protocol subprocess is tested only as a protocol test.

## Extraction contract

Command extraction reads `{operation:"extract",schema_version:1,feature_names:[...],source_data:<untrusted text>,contract:<fixed instructions>}` from stdin. Output must be exactly `{schema_version:1,features:<six dimension object>}`. No persuasive text, rationale or unexpected fields is accepted. The model must derive interpretations only from supplied authorized evidence, preserve unknowns, and treat instructions embedded in source text as data. The application validates schema/range but cannot guarantee a configured model’s semantic accuracy or instruction resistance.

Cache identity is SHA-256 of `(source SHA-256, extractor kind, immutable extractor version, feature schema version)`. Provenance records the source hash. Change the extractor version whenever model, prompt or settings change. Source changes miss cache; matching compatible entries are reused. The CLI stages all updated movie records before a transactional import. Model failures cannot publish partial enrichment; already verified cache entries may remain reusable. A normal selection has no extraction call path.

Fixture extraction is explicitly fixed, credential-free, and restricted to the demo CLI; precomputed demo profiles remain the default. Real model extraction is **pending** without a configured executable/model. Tests use a real lightweight subprocess producing a specified JSON fixture, not model inference.

## Disclosure boundary and local security

`public_movie` is the separate exact allowlist serializer: `{id,title,year,runtime,availability}`; each offer contains only `{provider,region,access_type,source,checked_at,url}`. Search has only `{id,title,year}`. History adds the user’s current rating, note, watched status. Settings expose explicit constraints and counts, never private learned examples. Diagnostics expose backend/version, aggregate fallback use, outcome code and measured last-call timing, never model output.

Only `/`, `/app.js`, `/style.css` are static routes. No database, fixtures, imports, raw source or developer private-inspection endpoint is served. No full movie object is serialized for hiding in CSS or hydration. JavaScript builds user/source text with `textContent`, and no HTML templating of movie data. Normal request logging is disabled. Errors use fixed codes and fixed neutral copy; subprocess source/output/stderr are not logged. CSP permits only local assets and prevents framing. HTTP responses use no-store; links use noreferrer/noopener, with no previews. Host and Origin checks plus JSON-only writes protect local endpoints against browser cross-origin writes and DNS rebinding. This is loopback-only and has no remote authentication, encryption, or multi-user authorization.

Titles themselves can reveal information; this is a software field-disclosure policy, not a promise that identifiers convey none. Authorized imports should put narratives only in private fields, never misuse identifying title/provider fields for plot text. The private SQLite database and CLI tools are explicit developer access, separate from viewing.

## Evaluation limits

Synthetic fixtures prove feature-to-preference-to-pick connectivity, including changed ratings and seen IDs retained outside the unseen set. They do not prove personal taste quality. No genuine ratings were supplied: no held-out comparison, quality benchmark, cost claim, latency advantage, or trained adaptation is justified. Diagnostics time actual selector calls only; reference selection makes no model or network calls. Kernstein and Kiragraph are not required; pure selectors and explicit data contracts are reusable integration points.
