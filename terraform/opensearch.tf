/**
 * VPC-attached domains need the legacy Elasticsearch service-linked role
 * (AWSServiceRoleForAmazonElasticsearchService) to create ENIs in your
 * subnets, because the domain API is still the "es" API. Note this is a
 * different role from AWSServiceRoleForAmazonOpenSearchService, which many
 * accounts already have. If this one also already exists, import it:
 *   terraform import aws_iam_service_linked_role.opensearch \
 *     arn:aws:iam::<account>:role/aws-service-role/es.amazonaws.com/AWSServiceRoleForAmazonElasticsearchService
 */
resource "aws_iam_service_linked_role" "opensearch" {
  aws_service_name = "es.amazonaws.com"
  description      = "Lets Amazon OpenSearch Service manage VPC networking for ${local.name}"
}

resource "aws_security_group" "opensearch" {
  name        = "${local.name}-opensearch"
  description = "Allows HTTPS from the API and ingest workloads only"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${local.name}-opensearch" }
}

resource "aws_vpc_security_group_ingress_rule" "opensearch_from_api" {
  security_group_id            = aws_security_group.opensearch.id
  description                  = "HTTPS from application tasks"
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.api.id
}

resource "aws_vpc_security_group_egress_rule" "opensearch_all" {
  security_group_id = aws_security_group.opensearch.id
  description       = "Allow all outbound"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_cloudwatch_log_group" "opensearch" {
  name              = "/aws/opensearch/${local.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_resource_policy" "opensearch" {
  policy_name = "${local.name}-opensearch-logs"

  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "es.amazonaws.com" }
      Action    = ["logs:PutLogEvents", "logs:CreateLogStream"]
      Resource  = "${aws_cloudwatch_log_group.opensearch.arn}:*"
    }]
  })
}

resource "aws_opensearch_domain" "vectors" {
  domain_name    = local.name
  engine_version = "OpenSearch_2.17"

  cluster_config {
    instance_type            = var.opensearch_instance_type
    instance_count           = var.opensearch_instance_count
    zone_awareness_enabled   = var.opensearch_instance_count > 1
    dedicated_master_enabled = var.environment == "prod"

    dynamic "zone_awareness_config" {
      for_each = var.opensearch_instance_count > 1 ? [1] : []
      content {
        availability_zone_count = 2
      }
    }
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = var.opensearch_volume_size
  }

  # Private domain: reachable only from inside the VPC.
  vpc_options {
    subnet_ids         = slice(aws_subnet.private[*].id, 0, min(var.opensearch_instance_count, var.az_count))
    security_group_ids = [aws_security_group.opensearch.id]
  }

  encrypt_at_rest {
    enabled = true
  }

  node_to_node_encryption {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  /**
   * Fine-grained access control is intentionally OFF.
   *
   * With FGAC on, OpenSearch's internal security plugin authorizes every
   * request and only the configured master user has rights. Additional IAM
   * principals must be mapped through the _plugins/_security API, which is a
   * provisioning step Terraform cannot do natively. Authorization here is
   * handled by the domain access policy below, which admits only the two task
   * roles, on a VPC-only domain with encryption in transit and at rest.
   *
   * For production, prefer turning this back on and mapping both roles via
   * the OpenSearch security API or the opensearch Terraform provider.
   */
  advanced_security_options {
    enabled                        = false
    anonymous_auth_enabled         = false
    internal_user_database_enabled = false
  }

  log_publishing_options {
    log_type                 = "INDEX_SLOW_LOGS"
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch.arn
  }

  # IAM-only access: signed SigV4 requests from the two task roles.
  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        AWS = [aws_iam_role.ecs_task.arn, aws_iam_role.lambda_ingest.arn]
      }
      Action   = "es:ESHttp*"
      Resource = "arn:aws:es:${var.aws_region}:${local.account_id}:domain/${local.name}/*"
    }]
  })

  depends_on = [
    aws_cloudwatch_log_resource_policy.opensearch,
    aws_iam_service_linked_role.opensearch,
  ]
}
