/**
 * Container registries -- one per service. Each service's Dockerfile lives
 * next to its own code:
 *
 *   app/api/Dockerfile        ->  <name>-api     ->  ECS Fargate  (uvicorn)
 *   app/ingestion/Dockerfile  ->  <name>-ingest  ->  Lambda       (S3 handler)
 *
 * app/retrieval/ has no Dockerfile and no registry, because retrieval has no
 * entrypoint: it is a library the API imports and runs in-process.
 *
 * Both images are pushed with the same tag: the git commit SHA. Tags are
 * IMMUTABLE, so a tag always means exactly one build and a rollback is simply
 * redeploying an older tag.
 */

resource "aws_ecr_repository" "api" {
  name                 = "${local.name}-api"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = var.environment != "prod"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_repository" "ingest" {
  name                 = "${local.name}-ingest"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = var.environment != "prod"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

# Every deploy pushes a new tag, so without this both repositories grow forever.
resource "aws_ecr_lifecycle_policy" "keep_recent" {
  for_each = {
    api    = aws_ecr_repository.api.name
    ingest = aws_ecr_repository.ingest.name
  }

  repository = each.value

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the 10 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
