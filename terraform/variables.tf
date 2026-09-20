variable "project_name" {
  description = "Short project slug used to name resources."
  type        = string
  default     = "rag-devops"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

# ---------------------------------------------------------------- networking
variable "vpc_cidr" {
  description = "CIDR block for the VPC this stack creates."
  type        = string
  default     = "10.50.0.0/16"

  validation {
    condition     = can(cidrsubnet(var.vpc_cidr, 8, 0))
    error_message = "vpc_cidr must be a valid CIDR with room for /24 subnets (use /16 or /20)."
  }
}

variable "az_count" {
  description = "Number of availability zones to span."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 1 && var.az_count <= 3
    error_message = "az_count must be between 1 and 3."
  }
}

variable "allowed_ingress_cidrs" {
  description = "CIDRs allowed to reach the API port directly. Defaults to the VPC only."
  type        = list(string)
  default     = []
}

variable "allowed_web_cidrs" {
  description = <<-EOT
    CIDRs allowed to reach the public load balancer. The listener is plain HTTP,
    so narrow this to your own address unless you add a TLS certificate.
  EOT
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# ------------------------------------------------------------------- search
variable "opensearch_instance_type" {
  description = "OpenSearch data node instance type."
  type        = string
  default     = "t3.small.search"
}

variable "opensearch_instance_count" {
  description = "Number of OpenSearch data nodes. Use 2+ in production."
  type        = number
  default     = 1
}

variable "opensearch_volume_size" {
  description = "EBS volume size per OpenSearch node, in GiB."
  type        = number
  default     = 20
}

variable "opensearch_index" {
  description = "Index name holding embedded chunks."
  type        = string
  default     = "rag-chunks"
}

# ------------------------------------------------------------------- models
variable "embed_model_id" {
  description = "Bedrock embedding model id."
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "embed_dimension" {
  description = "Embedding vector dimension; must match the model output."
  type        = number
  default     = 1024
}

variable "chat_model_id" {
  description = "Bedrock text generation model id, called through the Converse API."
  type        = string
  default     = "amazon.nova-lite-v1:0"
}

# ---------------------------------------------------------------- containers
variable "image_tag" {
  description = "Tag of the image in the stack's ECR repository."
  type        = string
  default     = "v2"
}

variable "container_image" {
  description = "Override the full image URI. Leave empty to use the ECR repo created here."
  type        = string
  default     = ""
}

variable "api_port" {
  description = "Port the API listens on inside the container."
  type        = number
  default     = 8000
}

variable "api_cpu" {
  description = "Fargate task CPU units."
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "Fargate task memory in MiB."
  type        = number
  default     = 1024
}

variable "api_desired_count" {
  description = "Number of API tasks to run."
  type        = number
  default     = 1
}

variable "log_retention_days" {
  description = "CloudWatch log retention."
  type        = number
  default     = 7
}

# ---------------------------------------------------------------- build host
variable "builder_instance_type" {
  description = "EC2 instance type for the Docker build host."
  type        = string
  default     = "t3.small"
}

variable "builder_enabled" {
  description = "Create the Docker build host. Set to false to stop paying for it once the image is pushed."
  type        = bool
  default     = true
}
