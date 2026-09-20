output "web_url" {
  description = "Open this in a browser to use the RAG console."
  value       = "http://${aws_lb.api.dns_name}"
}

output "alb_dns_name" {
  description = "Public DNS name of the load balancer."
  value       = aws_lb.api.dns_name
}

output "vpc_id" {
  description = "VPC created by this stack."
  value       = aws_vpc.main.id
}

output "private_subnet_ids" {
  description = "Private subnets hosting ECS, Lambda, and OpenSearch."
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "Public subnets hosting the NAT gateway and build host."
  value       = aws_subnet.public[*].id
}

output "builder_instance_id" {
  description = "Build host instance id. Connect with: aws ssm start-session --target <id>"
  value       = var.builder_enabled ? aws_instance.builder[0].id : null
}

output "build_command" {
  description = "Run this to build and push the image from the build host."
  value = var.builder_enabled ? join(" ", [
    "aws ssm send-command --region ${var.aws_region}",
    "--instance-ids ${aws_instance.builder[0].id}",
    "--document-name AWS-RunShellScript",
    "--parameters commands='/usr/local/bin/build-and-push.sh ${var.image_tag}'",
  ]) : null
}

output "container_image" {
  description = "Image URI the workloads run."
  value       = local.image
}

output "chat_model_id" {
  description = "Bedrock generation model in use."
  value       = var.chat_model_id
}

output "documents_bucket" {
  description = "S3 bucket that holds source documents. Upload under uploads/ to trigger ingestion."
  value       = aws_s3_bucket.documents.id
}

output "documents_bucket_arn" {
  description = "ARN of the documents bucket."
  value       = aws_s3_bucket.documents.arn
}

output "opensearch_endpoint" {
  description = "VPC-only OpenSearch endpoint used by the app."
  value       = aws_opensearch_domain.vectors.endpoint
}

output "opensearch_index" {
  description = "Index name holding the embedded chunks."
  value       = var.opensearch_index
}

output "ecr_repository_url" {
  description = "Push the API/ingest image here."
  value       = aws_ecr_repository.api.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster running the API."
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service running the API."
  value       = aws_ecs_service.api.name
}

output "ingest_lambda_name" {
  description = "Ingestion Lambda triggered by S3 uploads."
  value       = aws_lambda_function.ingest.function_name
}

output "ingest_dlq_url" {
  description = "Dead-letter queue for failed ingests."
  value       = aws_sqs_queue.ingest_dlq.url
}

output "api_key_secret_arn" {
  description = "Secrets Manager ARN holding the API key. Read it with the AWS CLI; it is not printed here."
  value       = aws_secretsmanager_secret.api_key.arn
}

output "api_security_group_id" {
  description = "Security group attached to the API tasks."
  value       = aws_security_group.api.id
}
