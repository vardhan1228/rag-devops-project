/**
 * Docker build host.
 *
 * The workstation has no Docker, so image builds happen on a small EC2
 * instance instead. It sits in a public subnet with NO inbound rules at all:
 * access is via SSM Session Manager, which works over the instance's outbound
 * connection, so there is no SSH port and no key pair to manage.
 *
 * Set builder_enabled = false once the image is in ECR to stop the charge.
 */

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_security_group" "builder" {
  count = var.builder_enabled ? 1 : 0

  name        = "${local.name}-builder"
  description = "Build host: egress only, managed through SSM"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${local.name}-builder" }
}

resource "aws_vpc_security_group_egress_rule" "builder_all" {
  count = var.builder_enabled ? 1 : 0

  security_group_id = aws_security_group.builder[0].id
  description       = "Outbound for package installs, SSM, and ECR push"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# ------------------------------------------------------------------- IAM
data "aws_iam_policy_document" "ec2_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "builder" {
  count = var.builder_enabled ? 1 : 0

  name               = "${local.name}-builder"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

# Session Manager access, no inbound SSH required.
resource "aws_iam_role_policy_attachment" "builder_ssm" {
  count = var.builder_enabled ? 1 : 0

  role       = aws_iam_role.builder[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "builder" {
  statement {
    sid       = "EcrAuth"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "EcrPushToThisRepo"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.api.arn]
  }

  statement {
    sid       = "ReadBuildContext"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.documents.arn}/_build/*"]
  }

  # Lets an operator smoke-test the private API from this host without the key
  # ever appearing in an SSM command parameter or shell history.
  statement {
    sid       = "ReadApiKeyForSmokeTests"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.api_key.arn]
  }
}

resource "aws_iam_role_policy" "builder" {
  count = var.builder_enabled ? 1 : 0

  name   = "${local.name}-builder"
  role   = aws_iam_role.builder[0].id
  policy = data.aws_iam_policy_document.builder.json
}

resource "aws_iam_instance_profile" "builder" {
  count = var.builder_enabled ? 1 : 0

  name = "${local.name}-builder"
  role = aws_iam_role.builder[0].name
}

# ------------------------------------------------------------------ instance
locals {
  builder_user_data = <<-EOT
    #!/bin/bash
    set -euxo pipefail

    dnf update -y
    dnf install -y docker tar gzip
    systemctl enable --now docker

    cat >/usr/local/bin/build-and-push.sh <<'SCRIPT'
    #!/bin/bash
    # Usage: build-and-push.sh <image-tag>
    set -euo pipefail

    TAG="$${1:-${var.image_tag}}"
    BUCKET="${aws_s3_bucket.documents.id}"
    REGISTRY="${aws_ecr_repository.api.repository_url}"
    REGION="${var.aws_region}"
    WORKDIR=$(mktemp -d)

    trap 'rm -rf "$WORKDIR"' EXIT

    aws s3 cp "s3://$BUCKET/_build/source.tar.gz" "$WORKDIR/source.tar.gz" --region "$REGION"
    tar -xzf "$WORKDIR/source.tar.gz" -C "$WORKDIR"

    aws ecr get-login-password --region "$REGION" \
      | docker login --username AWS --password-stdin "$${REGISTRY%%/*}"

    docker build -t "$REGISTRY:$TAG" "$WORKDIR"
    docker push "$REGISTRY:$TAG"

    echo "PUSHED $REGISTRY:$TAG"
    SCRIPT

    chmod +x /usr/local/bin/build-and-push.sh
    touch /var/lib/cloud/instance/builder-ready
  EOT
}

resource "aws_instance" "builder" {
  count = var.builder_enabled ? 1 : 0

  ami                         = data.aws_ssm_parameter.al2023.value
  instance_type               = var.builder_instance_type
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.builder[0].id]
  iam_instance_profile        = aws_iam_instance_profile.builder[0].name
  associate_public_ip_address = true
  user_data                   = local.builder_user_data
  user_data_replace_on_change = true

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 2 # Docker containers may need IMDS
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 30
    encrypted   = true
  }

  tags = { Name = "${local.name}-builder" }
}
