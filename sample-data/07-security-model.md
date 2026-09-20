# Security Model

## Identity and service access

Nothing in the platform stores AWS credentials. The query service and the
ingestion worker each assume their own task role, and the AWS SDK signs every
request with temporary credentials obtained from that role. This is why no key
is configured for the model service, the document store, or the search domain:
those calls are authorized by role, and the signature is added automatically.

The two roles are separate on purpose. The ingestion worker needs to read
documents and write to the index. The query service needs to read the index and
call the generation model. Neither needs the other's permissions.

Model permissions are scoped to specific model identifiers rather than granted
as a wildcard, so a code change cannot silently begin using a more expensive
model. Cross-region inference profiles require both the profile and the
underlying regional model to be permitted, because a profile routes requests to
model copies in other regions.

## Caller authentication is a separate question

Role-based access authenticates the platform to AWS. It says nothing about who
is allowed to use the platform. Those are independent concerns, and conflating
them is a common and expensive mistake.

The query service supports a shared key supplied in a request header. It is
controlled by a single setting. When the setting is enabled and no key has been
provided, the service refuses to start rather than serving an open endpoint, on
the principle that failing closed is safer than failing open.

The key is generated during provisioning, stored in a managed secret, and
injected into the container at startup. It is never committed to the repository
and never written into a container image.

When caller authentication is disabled, anyone able to reach the load balancer
can submit questions. Two consequences follow. Indexed content becomes readable
by any such caller, so the corpus is effectively public. And every question
consumes model tokens billed to the account, which makes an open endpoint a
budget risk as much as a disclosure risk.

Running without caller authentication is therefore only reasonable when network
reach is restricted, either to a known address range or behind a private
network path.

## Transport

The load balancer terminates plain HTTP unless a certificate is configured. Any
header sent to it, including an API key, crosses the network unencrypted. A
certificate and an HTTPS listener are required before the endpoint carries
anything sensitive.

Internal traffic is encrypted. The search domain enforces HTTPS, encrypts data
at rest, and encrypts traffic between nodes.

## Data at rest

The document store and the search domain are both encrypted. The store blocks
all public access and denies any request not made over TLS.

Infrastructure state deserves the same care as a credential store. It records
generated passwords and secret values in plaintext, so the state bucket is
versioned, encrypted, blocked from public access, and restricted to TLS.

## Network exposure

Only the load balancer is reachable from the internet. The query service, the
ingestion worker, and the search domain occupy private subnets. Security groups
reference each other rather than listing address ranges, so the search domain
accepts traffic from the query service's group rather than from a subnet range
that might later host something else.

The build host has no inbound rules at all. Administrative access is performed
through the managed session service over the instance's outbound connection,
which means no open administrative port and no key pair to distribute or rotate.

Instance metadata requires session tokens, which prevents a server-side request
forgery in an application from reading role credentials from the metadata
service.

## Prompt injection

Retrieved passages are untrusted input. A document in the corpus can contain
text instructing the model to ignore its instructions. The current mitigation is
limited: passages are wrapped in delimiters, the instruction to answer only from
context is placed in the system prompt, and temperature is zero.

This reduces but does not eliminate the risk. Anyone who can write to the
`uploads/` prefix can influence answers, so write access to the document store
should be treated as a privileged permission.
