# Deployment Runbook

Deployments are performed by the GitHub Actions pipeline. Manual applies from a
workstation are reserved for recovering from a broken pipeline.

## Pipeline stages

The pipeline is deliberately split, because the infrastructure code owns the
container registry while the workloads cannot start until an image exists in it.

1. **Lint and test.** Static checks and the unit suite. No AWS access.
2. **Validate.** Formatting and type checking of the infrastructure code, with
   no backend initialised so no credentials are required.
3. **Bootstrap.** Confirms the deploy credentials resolve to the expected
   account, then creates the state bucket if absent.
4. **Registry.** Applies only the container registry resource.
5. **Build.** Builds the image and pushes it tagged with the commit SHA.
6. **Apply.** Full apply, pointing the workloads at that tag, then waits for
   the service to reach a steady state.
7. **Smoke.** Verifies the deployed stack answers a real question.

## Image tagging

Images are tagged with the commit SHA and the registry rejects tag overwrites.
A given tag therefore always refers to one specific build, which makes rollback
a matter of redeploying a known tag. Mutable tags such as `latest` make the
currently running code ambiguous and are not used.

## First deployment

A first deployment provisions the search domain, which takes between fifteen
and twenty-five minutes. The apply step allows forty-five minutes. Subsequent
deployments that only change the image typically complete in three to four
minutes.

## Rollback

To roll back, redeploy the previous commit SHA as the image tag. The service
performs a rolling replacement and the deployment circuit breaker will revert
automatically if the replacement tasks fail their health checks.

The circuit breaker only protects against tasks that fail to become healthy. It
does not detect an application that starts successfully but answers incorrectly.
For that class of fault, roll back explicitly.

Infrastructure changes are not rolled back by redeploying an image. Revert the
offending commit and let the pipeline apply the reverted configuration.

## Health checks

Two independent checks exist and they are not interchangeable.

The container health check runs inside the task and calls the liveness endpoint
over the loopback interface. It answers "is this process alive".

The load balancer health check calls the same endpoint across the network from
the public subnets. It answers "can traffic reach this task". A task can pass
the first and fail the second when a security group is misconfigured.

The liveness endpoint is intentionally trivial and does not touch the search
domain. A dependency outage should not cause healthy tasks to be killed and
replaced in a loop.

## Readiness versus liveness

A separate readiness endpoint reports whether the search index is reachable and
exists. It is used by operators and by the smoke stage, never by the load
balancer. Wiring dependency checks into load balancer health would convert a
degraded search domain into a total outage.

## Verifying a deployment

After the apply, confirm three things. The service reports a steady state with
the expected running count. The load balancer returns a successful liveness
response. A question posted to the query endpoint returns an answer with at
least one citation, which proves the whole path including retrieval and
generation.
