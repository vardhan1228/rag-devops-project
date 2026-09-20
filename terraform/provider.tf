terraform {
  # use_lockfile (S3-native state locking) requires 1.11 or newer.
  required_version = ">= 1.11.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.82"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  /**
   * Partial backend configuration: the bucket and region are supplied at init
   * time so the same code works across accounts.
   *
   *   terraform init \
   *     -backend-config="bucket=<state-bucket>" \
   *     -backend-config="region=us-east-1"
   *
   * use_lockfile enables S3-native state locking (Terraform >= 1.11), so no
   * DynamoDB table is needed. To work without remote state locally, run
   * `terraform init -backend=false` for validate-only workflows.
   */
  backend "s3" {
    key          = "rag-devops-project/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  name       = "${var.project_name}-${var.environment}"
  account_id = data.aws_caller_identity.current.account_id

  # Default to the repository this stack creates; override for external images.
  image = var.container_image != "" ? var.container_image : "${aws_ecr_repository.api.repository_url}:${var.image_tag}"

  # With no explicit allow-list, only callers inside the VPC can reach the API.
  api_ingress_cidrs = length(var.allowed_ingress_cidrs) > 0 ? var.allowed_ingress_cidrs : [var.vpc_cidr]
}
