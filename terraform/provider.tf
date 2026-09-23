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
   * Remote state lives in an S3 bucket you create once, by hand:
   *
   *   aws s3api create-bucket --bucket <your-bucket> --region us-east-1
   *   aws s3api put-bucket-versioning --bucket <your-bucket> \
   *     --versioning-configuration Status=Enabled
   *
   * The bucket name is supplied at init time, so the same code works in any
   * account:
   *
   *   terraform init -backend-config="bucket=<your-bucket>" \
   *                  -backend-config="region=us-east-1"
   *
   * use_lockfile is S3-native state locking, so no DynamoDB table is needed.
   * To check syntax without any backend at all: terraform init -backend=false
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

locals {
  name       = "${var.project_name}-${var.environment}"
  account_id = data.aws_caller_identity.current.account_id

  # One image per workload, both tagged with the same commit SHA. See ecr.tf.
  api_image    = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
  ingest_image = "${aws_ecr_repository.ingest.repository_url}:${var.image_tag}"

  # With no explicit allow-list, only callers inside the VPC can reach the API.
  api_ingress_cidrs = length(var.allowed_ingress_cidrs) > 0 ? var.allowed_ingress_cidrs : [var.vpc_cidr]
}
