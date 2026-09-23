# Architecture

Five diagrams, each answering one question. Sources are Mermaid text in
`docs/diagrams/*.mmd`; PNG and SVG are rendered from them and committed so they
display here without any tooling.

Regenerate after editing a source:

```powershell
powershell -ExecutionPolicy Bypass -File docs/render-diagrams.ps1
```

The script renders every `.mmd` to both formats. It drives Mermaid CLI through
headless Chrome, using the Chrome or Edge already installed rather than
downloading a Chromium, which is why it needs no Graphviz and no extra setup.

---

## 1. Where things sit, and what may talk to what

![Network topology](diagrams/01-network-topology.png)

One VPC, `10.50.0.0/16`, across two availability zones.

Only the load balancer is reachable from the internet. Fargate tasks, the Lambda
ENIs, and the OpenSearch node all sit in private subnets with
`assign_public_ip = false`, so nothing can dial them from outside. Their
outbound calls leave through the NAT gateway.

Two details worth noticing. S3 traffic uses a gateway endpoint rather than the
NAT, which costs nothing hourly and avoids NAT data processing charges. And
security groups reference each other rather than IP ranges, so "OpenSearch
accepts traffic from the API" stays true even if subnets are later reused for
something else.

There is a single NAT gateway, in one AZ, to keep cost down. That is a
deliberate development trade-off: losing that AZ cuts egress for the whole
workload. Production should run one per AZ.

---

## 2. Which service calls which, and with what credential

![Service interactions](diagrams/02-service-interactions.png)

Separating the read path from the write path is the useful way to look at this.

**Read path.** A question arrives at the load balancer, reaches FastAPI, and
fans out to three calls: embed the question, search the index, generate the
answer.

**Write path.** An upload to S3 fires an event, the Lambda reads the object,
embeds the passages, and writes them to the same index the read path queries.

The two paths hold separate IAM roles. The API may read the index and call the
models; the Lambda may read documents and write the index. Neither carries the
other's permissions.

Each path has its own image, and each Dockerfile sits in the directory whose
code it builds. Open a service's folder and its build recipe is right there
next to its entrypoint:

```
app/api/            main.py       + Dockerfile   ->  ECS Fargate
app/ingestion/      indexer.py    + Dockerfile   ->  Lambda
app/retrieval/      rag.py, search.py            ->  no Dockerfile
```

| Dockerfile | Base image | Runs on | Starts |
| --- | --- | --- | --- |
| `app/api/Dockerfile` | `python:3.12-slim` | ECS Fargate | `uvicorn` on port 8000 |
| `app/ingestion/Dockerfile` | `public.ecr.aws/lambda/python:3.12` | Lambda | `lambda_handler` |

Two images, not three, even though `app/` has three packages. `app/retrieval/`
gets no Dockerfile because retrieval has no entrypoint: `main.py` imports
`answer_question` and `hybrid_search` and calls them in-process, so retrieval
ships *inside* the API image. The rule is one Dockerfile per process that
starts, not one per folder.

Both are built with the repo root as the Docker context, since each image needs
`app/` and `requirements.txt`:

```bash
docker build -f app/api/Dockerfile       -t rag-api    .
docker build -f app/ingestion/Dockerfile -t rag-ingest .
```

So the chunking and embedding code is literally the same code in both places.
What differs is only how the process is started, and that difference now lives
in the Dockerfile beside the code, rather than in an entrypoint override buried
in the Lambda resource.

No AWS credentials exist in either image or in the code. Every AWS call is SigV4
signed from the task role. That is what "Bedrock connects automatically" means,
and it is a different question from whether a browser needs a key to call your
API.

---

## 3. How a question becomes an answer

![Query request flow](diagrams/03-query-request-flow.png)

The interesting step is fusion. Two retrievers run against the same index: k-NN
on the embedding vector, and BM25 on the passage text. Vector search handles
paraphrase, keyword search handles exact rare tokens such as `t3.small.search`
or a specific threshold. Most questions benefit from one or the other, and you
cannot tell which in advance.

Their scores cannot be compared: cosine similarity sits near zero to one, BM25
is unbounded and shifts with corpus statistics. Normalising them requires
choosing a weight, and any fixed weight is wrong for some queries. So fusion
discards the scores and uses rank alone, summing `1 / (60 + rank)` across both
lists. A passage both retrievers rank highly beats one that only a single
retriever loved, which is the behaviour you want, because agreement between
independent methods is evidence.

If retrieval returns nothing, the model is never called. Handing an LLM an empty
context invites a confident answer from memory alone, which is the worst failure
mode for a system whose value is being grounded in your documents.

---

## 4. How documents become searchable passages

![Ingestion flow](diagrams/04-ingestion-flow.png)

Load, chunk, embed, index. Chunking packs sentences into a 1000 character window
with 150 characters of overlap; the overlap protects facts that would otherwise
straddle a boundary and retrieve poorly from either side.

There are two ways in. Path A is the S3 event, one invocation per uploaded
object, which is what happens when someone drops a file in the bucket. Path B is
an explicit reindex the pipeline invokes, which drops the index and rebuilds it
from the bucket in a single call.

Path B exists because deleting an object from S3 does not delete its passages
from the index. Without it, replacing the corpus leaves the old passages behind
to keep surfacing in answers. It also sidesteps a race that path A hit in
practice: seven concurrent invocations each checked whether the index existed,
all saw "no", and all tried to create it, so one won and the rest crashed with
`resource_already_exists_exception`. `ensure_index` now treats that specific
error as success, and one invocation avoids the contention entirely.

Passage ids are deterministic, `docId::ordinal`, so re-ingesting a document
overwrites the same index documents instead of duplicating them.

---

## 5. How a push reaches production

![Deployment pipeline](diagrams/05-deployment-pipeline.png)

Three jobs, cheapest first.

`checks` needs no AWS access at all: `ruff` on the Python, `terraform fmt` and
`terraform validate` with `-backend=false`. A typo fails in under a minute
without touching the account. Pull requests stop here.

`deploy` is one job with four steps, in this order for a specific reason.
Terraform creates the two ECR repositories, but the ECS service and the Lambda
each reference an image tag inside one of them, and a single apply fails on a
fresh account because the tags do not exist yet. So it applies only the
repositories, pushes both images tagged with the commit SHA, applies everything
else, then seeds the corpus. That is step ordering, not a reason for separate
jobs, so it authenticates and runs `terraform init` once.

Because tags are immutable and equal to the commit SHA, the running code is
never ambiguous, and a rollback is redeploying an older tag.

The state bucket is not created by the pipeline. You create it once by hand and
set the `TF_STATE_BUCKET` repository variable; the deploy job fails with a clear
message if it is missing. Bootstrapping the thing that holds your state is a
one-time act, and having a pipeline do it hides where state lives.

The last job earns its place. It asserts `/health` returns 200, `/ready` reports
the index exists, and a real question comes back with citations. That covers the
whole path end to end: S3 event, Lambda, embeddings, OpenSearch k-NN, and
generation. A deployment that starts cleanly but cannot answer anything fails
the build.

---

## Current configuration worth knowing

| Setting | Value | Note |
| --- | --- | --- |
| `require_auth` | `false` | `/query` is open to anyone who can reach the ALB |
| `allowed_web_cidrs` | `0.0.0.0/0` | The only access control while auth is off |
| ALB listener | HTTP :80 | No certificate, so traffic is unencrypted |
| `opensearch_instance_count` | 1 | No redundancy; a node loss is an outage |
| `api_desired_count` | 1 | Autoscales to 4 on CPU |
| NAT gateways | 1 | Single AZ egress |

The first three combine into a real exposure: an open, unencrypted endpoint that
spends Bedrock tokens on your account for every question asked. Narrowing
`allowed_web_cidrs` to your own address is the one change worth making before
leaving this running:

```bash
terraform apply -var 'allowed_web_cidrs=["YOUR.IP.HERE/32"]'
```
