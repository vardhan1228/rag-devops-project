# Incident Playbook

Symptoms first, then the checks that distinguish causes. Each entry ends with
the remedy.

## Answers report that no relevant content was found

The query path is healthy but retrieval returned nothing.

Check whether the index exists and holds documents. A newly provisioned
environment with no ingestion run yet is the most common cause, and the
readiness endpoint reports the index as absent.

If the index exists but is empty, inspect the ingestion worker's logs and the
dead letter queue. A permissions fault on the search domain produces an
authorization error on the first write, which fails every invocation.

If the index holds documents but a specific question retrieves nothing, confirm
that the embedding model in use matches the one used at ingestion. Changing the
model or its dimension without reindexing leaves the stored vectors in a
different space from the query vector, and results become effectively random.
The remedy is a full reindex.

## Ingestion invocations fail immediately

A duration of a few hundred milliseconds indicates the function failed before
doing work.

An authorization error against the search domain usually means fine-grained
access control is enabled and the worker's role is not mapped inside the
security plugin. Being permitted by the domain access policy is not sufficient
when fine-grained access control is active: it authorizes separately, and only
the configured master user has rights until other principals are mapped.

A network interface creation error means the execution role lacks the
permissions a VPC-attached function requires. The basic execution policy is not
enough; the VPC access policy is needed.

A timeout with no log output points at networking. A function in a private
subnet with no outbound route cannot reach the embedding service and will hang
until the timeout expires.

## Every request returns an authorization failure

The service requires an API key and the caller is not sending a matching one.
Confirm whether the deployment has authentication enabled. When it is disabled
the endpoint is open, and an authorization failure instead suggests the key
check was re-enabled without the key being distributed.

## Tasks cycle between starting and stopping

Read the stopped reason on the task, not just the service events.

An image pull failure means the tag does not exist in the registry. This happens
when an apply runs before the build stage has pushed.

A container that exits immediately with no application log usually failed during
startup configuration. The service refuses to start when authentication is
enabled but no key was injected, which is deliberate: failing closed is safer
than serving an unauthenticated endpoint by accident.

Repeated health check failures with a task that appears to run mean the check
cannot reach the port. Verify the security group permits the load balancer to
reach the task port.

## Latency spikes on queries

Each query performs one embedding call, two searches, and one generation call.
Generation dominates.

Check whether throttling is occurring on the model. Under sustained load the
platform receives throttling responses, and the embedding path retries with
backoff, which converts throttling into latency rather than errors.

If latency is confined to search, check the domain's CPU and JVM memory
pressure. A single undersized data node is the usual cause in non-production
environments.

## The load balancer returns a gateway error

No healthy targets are registered. Confirm the service has running tasks and
that the target group reports them healthy. An empty target group with running
tasks indicates the service was created without a load balancer attachment, or
that the tasks are failing the network-level health check.

## Escalation

Record the request identifier, the trace identifier, and the image tag in the
incident channel. The image tag is the most useful single fact, because it
identifies exactly which build is running.
