resource "aws_security_group" "lambda" {
  name        = "${local.name}-lambda"
  description = "Egress-only group for the ingestion Lambda"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${local.name}-lambda" }
}

resource "aws_vpc_security_group_egress_rule" "lambda_all" {
  security_group_id = aws_security_group.lambda.id
  description       = "Allow all outbound (S3, Bedrock, OpenSearch)"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# The Lambda reaches OpenSearch through its own SG.
resource "aws_vpc_security_group_ingress_rule" "opensearch_from_lambda" {
  security_group_id            = aws_security_group.opensearch.id
  description                  = "HTTPS from ingestion Lambda"
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.lambda.id
}

resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/aws/lambda/${local.name}-ingest"
  retention_in_days = var.log_retention_days
}

# Container-image Lambda so ingestion runs the exact same code as the API.
resource "aws_lambda_function" "ingest" {
  function_name = "${local.name}-ingest"
  role          = aws_iam_role.lambda_ingest.arn
  package_type  = "Image"
  image_uri     = local.image
  timeout       = 300
  memory_size   = 1024

  # The image's default CMD starts uvicorn for ECS; Lambda overrides the
  # entrypoint with the runtime interface client so one image serves both.
  image_config {
    entry_point = ["/usr/local/bin/python", "-m", "awslambdaric"]
    command     = ["app.ingestion.indexer.lambda_handler"]
  }

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      OPENSEARCH_ENDPOINT = aws_opensearch_domain.vectors.endpoint
      OPENSEARCH_INDEX    = var.opensearch_index
      EMBED_MODEL_ID      = var.embed_model_id
      EMBED_DIMENSION     = tostring(var.embed_dimension)
      DOCUMENTS_BUCKET    = aws_s3_bucket.documents.id
      LOG_LEVEL           = "INFO"
    }
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [aws_cloudwatch_log_group.ingest]
}

resource "aws_lambda_permission" "allow_s3_invoke" {
  statement_id   = "AllowExecutionFromS3Bucket"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.ingest.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.documents.arn
  source_account = local.account_id
}

# Failed ingests land here instead of vanishing.
resource "aws_sqs_queue" "ingest_dlq" {
  name                      = "${local.name}-ingest-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_lambda_function_event_invoke_config" "ingest" {
  function_name          = aws_lambda_function.ingest.function_name
  maximum_retry_attempts = 1

  destination_config {
    on_failure {
      destination = aws_sqs_queue.ingest_dlq.arn
    }
  }
}

data "aws_iam_policy_document" "lambda_dlq" {
  statement {
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingest_dlq.arn]
  }
}

resource "aws_iam_role_policy" "lambda_dlq" {
  name   = "${local.name}-lambda-dlq"
  role   = aws_iam_role.lambda_ingest.id
  policy = data.aws_iam_policy_document.lambda_dlq.json
}
