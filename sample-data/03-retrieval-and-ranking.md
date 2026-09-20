# Retrieval and Ranking

Retrieval decides which passages the generation model is allowed to see. It is
the component with the largest effect on answer quality, and the cheapest one
to improve.

## Vector search

The question is embedded and compared against passage vectors with approximate
nearest neighbour search. The index uses HNSW with cosine similarity.

HNSW is approximate by design. Recall is traded for latency, which is almost
always the right trade at this corpus size. Exact search would require scanning
every vector, and the accuracy gain is not measurable in answer quality.

An optional filter restricts the search to a single source document. This
supports "ask about this document" workflows, where showing a passage from an
unrelated file would be confusing even if it is topically similar.

## Keyword search

The same question is also run as a BM25 match against the passage text. BM64 is
not used; the standard BM25 implementation is what OpenSearch provides.

Keyword search earns its place on queries containing rare tokens. Version
strings, error identifiers, configuration flag names, and proper nouns are
frequently absent from the embedding model's training distribution and are
therefore represented poorly as vectors.

## Reciprocal rank fusion

The two result lists have incompatible scores. Cosine similarity lives roughly
between zero and one; BM25 is unbounded and varies with corpus statistics.
Normalising them against each other requires choosing a weight, and any fixed
weight is wrong for some queries.

Reciprocal rank fusion sidesteps the problem by discarding the scores and using
only the ranks. Each passage receives `1 / (k + rank)` from every list it
appears in, with `k` set to 60, and the contributions are summed.

Two properties follow. A passage ranked highly by both retrievers outscores one
ranked first by a single retriever, which is the desired behaviour: agreement
between independent methods is evidence. And the formula is scale free, so it
needs no tuning when the corpus grows or the embedding model changes.

Each retriever is asked for twice the requested number of passages before
fusion, giving the merge enough candidates to reorder meaningfully.

## Context assembly

Surviving passages are rendered into numbered blocks, each labelled with its
source. Numbering is what makes citation possible: the model is told to
reference `[1]` and `[2]`, and those markers map back to specific objects in
the document store.

Blocks are added until a character budget of 12000 is reached, then assembly
stops. Truncating at a block boundary rather than mid-passage matters, because
a half sentence of context is worse than no context. The model may quote the
fragment as though it were complete.

## Generation

The prompt instructs the model to answer only from the supplied context, to
cite the passages used, and to say plainly when the context does not contain
the answer. Temperature is zero, which makes answers reproducible and reduces
the chance of invented detail.

When retrieval returns nothing at all, the generation call is skipped entirely
and a fixed message is returned. Calling the model with no context invites a
confident answer drawn purely from parametric memory, which is the worst
possible failure mode for a system whose value rests on being grounded.

## Evaluating changes

Retrieval changes are assessed against a fixed set of roughly sixty questions
with known correct source documents. The metric is recall at five: the fraction
of questions whose correct source appears among the top five passages. Answer
wording is not scored, because it varies between model versions and drowns out
the retrieval signal being measured.
