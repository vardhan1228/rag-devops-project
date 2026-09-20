# Cost and Scaling

## What the monthly bill is made of

In a single-environment deployment sized for development, roughly sixty dollars
a month, the spend is concentrated in two line items that have nothing to do
with request volume.

The search domain is the largest. One `t3.small.search` data node with a 20 GiB
gp3 volume runs about twenty-six dollars a month. It is billed per hour whether
or not a single query arrives.

The NAT gateway is second, about thirty-two dollars a month plus data
processing. It too is billed hourly.

The container service is comparatively small. One Fargate task at half a vCPU
and one gigabyte of memory is around nine dollars a month.

Model usage is per token and is negligible at development volumes. A question
with five retrieved passages consumes a few thousand input tokens and a few
hundred output tokens.

## Reducing idle cost

Because the two largest items are hourly rather than per request, the effective
way to cut a development bill is to remove idle capacity, not to optimise
queries.

Replacing the NAT gateway with interface endpoints for the model service,
registry, secrets, and logs removes the hourly NAT charge. Roughly five
interface endpoints are needed, at about seven dollars each, so the saving is
marginal. The NAT is simpler and usually the better choice below that threshold.

Destroying a development environment overnight is the largest available saving
and eliminates both items for the hours it is down.

The optional build host should be switched off once an image is in the registry.
It is a small instance, around fifteen dollars a month, and contributes nothing
between builds.

## Scaling the query service

The service scales on average CPU utilisation with a target of sixty-five
percent. Scale out waits sixty seconds; scale in waits three hundred. The
asymmetry is intentional: adding capacity late hurts users, whereas removing it
early risks immediate re-scaling.

Maximum capacity is four times the baseline. The desired count is ignored on
subsequent applies so that an autoscaling decision is not reverted by the next
deployment.

CPU is an imperfect signal here, because a task waiting on a model response is
idle rather than busy. Request concurrency would track load better, and is the
natural next change if scaling proves sluggish under real traffic.

## Scaling the search domain

A single data node has no redundancy: a node failure is an outage, and some
configuration changes force a blue-green replacement. Production should run at
least two nodes across two availability zones, with replica shards enabled.

Vector search is memory bound. HNSW graphs are held in memory, and the working
set grows with the number of passages and the vector dimension. Long before
storage fills, memory pressure will dictate the next instance size.

Reducing the embedding dimension is the cheapest lever on memory. The embedding
model supports smaller output dimensions at a modest accuracy cost, and halving
the dimension roughly halves the graph's memory footprint. Changing it requires
a full reindex.

## Ingestion throughput

Ingestion is embarrassingly parallel across documents, since one invocation
handles one object. Concurrency is therefore bounded by the model's throttling
limits rather than by the platform.

Passage count, not document count, determines cost and time. A single large
document can produce thousands of passages and take longer than a hundred small
ones.
