/**
 * Internet-facing Application Load Balancer fronting the API and web UI.
 *
 * SECURITY NOTE: this listener is plain HTTP because the stack has no domain
 * or ACM certificate. The API key the UI sends therefore crosses the internet
 * unencrypted. Narrow allowed_web_cidrs to your own address, or add a
 * certificate and switch the listener to HTTPS, before using it for real data.
 */

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "Public entry point for the web UI and API"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${local.name}-alb" }
}

resource "aws_vpc_security_group_ingress_rule" "alb_in" {
  for_each = toset(var.allowed_web_cidrs)

  security_group_id = aws_security_group.alb.id
  description       = "Web traffic from ${each.value}"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  cidr_ipv4         = each.value
}

# Only the ALB may talk to the tasks; egress is scoped to the task port.
resource "aws_vpc_security_group_egress_rule" "alb_to_tasks" {
  security_group_id            = aws_security_group.alb.id
  description                  = "Forward to API tasks"
  from_port                    = var.api_port
  to_port                      = var.api_port
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.api.id
}

resource "aws_vpc_security_group_ingress_rule" "api_from_alb" {
  security_group_id            = aws_security_group.api.id
  description                  = "API traffic from the load balancer"
  from_port                    = var.api_port
  to_port                      = var.api_port
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.alb.id
}

resource "aws_lb" "api" {
  name               = substr("${local.name}-alb", 0, 32)
  load_balancer_type = "application"
  internal           = false
  subnets            = aws_subnet.public[*].id
  security_groups    = [aws_security_group.alb.id]

  drop_invalid_header_fields = true
  idle_timeout               = 120
  enable_deletion_protection = var.environment == "prod"

  tags = { Name = "${local.name}-alb" }
}

resource "aws_lb_target_group" "api" {
  name        = substr("${local.name}-tg", 0, 32)
  port        = var.api_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.main.id

  deregistration_delay = 30

  health_check {
    enabled             = true
    path                = "/health"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = { Name = "${local.name}-tg" }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
