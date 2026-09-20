# Platform Architecture

The CloudRAG platform answers natural language questions over an internal
document corpus. It is built from four independently deployable pieces.

## Components

**Document store.** All source documents live in a single versioned S3 bucket.
Anything written under the `uploads/` prefix is treated as corpus material.
Objects written under `_build/` are deployment artifacts and are deliberately
excluded from ingestion so that build tarballs never end up in search results.

**Ingestion worker.** An AWS Lambda function packaged as a container image. It
is invoked by S3 object-created notifications, one invocation per uploaded
object. The function loads the object, splits it into passages, requests an
embedding vector for each passage, and writes the results into the search
index. Failed invocations are retried once and then delivered to a dead letter
queue so nothing is silently dropped.

**Search index.** An Amazon OpenSearch domain holding one document per passage.
Each document carries the passage text, the identifier of the source object,
the passage ordinal within that source, and a 1024-dimension embedding vector
indexed with HNSW for approximate nearest neighbour search.

**Query service.** A FastAPI application on ECS Fargate, fronted by an
Application Load Balancer. It serves both the browser console and the JSON API.

## Request path

A question travels through the system as follows.

1. The browser posts the question to the query service.
2. The service embeds the question with the same embedding model used at
   ingestion time. Using a different model here is the single most common cause
   of poor retrieval, because the two vector spaces are not comparable.
3. It runs two searches in parallel: a vector k-nearest-neighbour search and a
   BM25 keyword search.
4. The two ranked lists are merged with reciprocal rank fusion.
5. The top passages are formatted into a numbered context block, truncated to
   fit a character budget.
6. The context and question are sent to a Bedrock text generation model, which
   is instructed to answer only from the supplied context and to cite the
   numbered passages it used.
7. The answer and its citations are returned to the caller.

## Why two retrievers

Vector search handles paraphrase well. A question asking "how do I undo a bad
release" will retrieve a passage about rollback procedures even though it
shares no words with the question. It is weak on rare exact tokens: error
codes, flag names, product identifiers.

Keyword search is the mirror image. It nails exact tokens and fails on
paraphrase. Running both and fusing the rankings gives good behaviour on both
question styles without tuning a weight between them.

## Network layout

The platform runs inside a dedicated VPC spanning two availability zones. The
load balancer occupies the public subnets. The query service, the ingestion
worker, and the search domain all sit in private subnets with no inbound route
from the internet. Outbound calls to AWS APIs leave through a NAT gateway,
except for S3 traffic, which uses a gateway endpoint and therefore never
touches the NAT or incurs data processing charges.
