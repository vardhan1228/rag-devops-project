# Ingestion Pipeline

Ingestion converts raw documents into searchable passages. It runs in four
stages: load, chunk, embed, index.

## Loading

The loader accepts a local filesystem path or an `s3://bucket/prefix` URI and
yields one record per document. Three formats are recognised: `.txt`, `.md`,
and `.pdf`. Anything else is skipped rather than failing the batch, because a
single unsupported attachment in a folder of hundreds should not abort the run.

PDF text extraction is performed page by page and the pages are joined with
blank lines, which preserves enough structure for the chunker to find paragraph
boundaries. Scanned PDFs with no embedded text layer produce empty output and
are skipped; they need OCR first, which the pipeline does not perform.

Documents whose extracted text is empty or whitespace-only are dropped at this
stage so they never reach the embedding model.

## Chunking

Passages are built by greedily packing sentences into a character window.
Defaults are a 1000 character window with 150 characters of overlap.

The splitter works top down. Text is first divided on blank lines into
paragraphs, then paragraphs are divided into sentences on terminal punctuation.
Sentences are appended to the current passage until adding the next one would
exceed the window, at which point the passage is emitted.

Overlap exists to protect facts that straddle a boundary. When a passage is
emitted, its trailing characters are carried forward as the prefix of the next
one. Without overlap, a sentence such as "the retention period is thirty days"
can be split so that neither resulting passage contains a complete statement,
and neither will retrieve well.

A single sentence longer than the window is hard split at the character level.
This is rare in prose but common in machine-generated content such as log
dumps or minified payloads.

Every passage gets a stable identifier of the form `<document-id>::<ordinal>`.
Because the identifier is deterministic, re-ingesting an unchanged document
overwrites the same index documents instead of creating duplicates. This makes
the pipeline idempotent and makes full reindexing safe to run at any time.

## Embedding

Each passage is sent to Amazon Titan Text Embeddings V2, configured for 1024
dimensions with normalisation enabled. Normalised vectors let cosine similarity
be computed as a dot product, which is marginally cheaper at query time.

The embedding model is single-input, so batching is a loop over slices rather
than a true batch request. The slice size bounds memory use and makes retry
behaviour predictable.

Throttling is expected under load and is handled with exponential backoff over
four attempts. Only throttling and service-unavailable responses are retried.
An access denied response is raised immediately, because retrying a permissions
error wastes time and obscures the real fault.

## Indexing

Passages are written with the bulk API. The index is created on first write
with an explicit mapping rather than relying on dynamic inference, because a
`knn_vector` field must declare its dimension and search method up front.

The bulk helper is configured not to raise on individual document errors. A
malformed passage should not discard the other nine hundred in the batch. The
per-document failures are counted and the first few are returned in the ingest
summary for diagnosis.

Writes use `refresh=True` so that content is searchable the moment ingestion
reports success. This costs throughput and would be wrong for a bulk backfill
of millions of passages, where periodic refresh is far cheaper.

## Nightly reindex

A scheduled job re-ingests the entire corpus every night at 02:00 UTC. Because
passage identifiers are deterministic, this is a no-op for unchanged documents
and repairs any passage lost to a failed invocation during the day. The job
reports the number of passages written and the number of documents skipped.
