resource "aws_cloudwatch_log_group" "backend" {
  name              = "/jobpilot/backend"
  retention_in_days = 14
}

resource "aws_ssm_parameter" "anthropic_api_key" {
  name        = "/jobpilot/anthropic_api_key"
  description = "JobPilot Anthropic API key"
  type        = "SecureString"
  value       = var.anthropic_api_key
  # default AWS managed key for SSM
  key_id = "alias/aws/ssm"
}

resource "aws_ssm_parameter" "openai_api_key" {
  name        = "/jobpilot/openai_api_key"
  description = "JobPilot OpenAI API key"
  type        = "SecureString"
  value       = var.openai_api_key
  key_id      = "alias/aws/ssm"
}

resource "aws_ssm_parameter" "db_password" {
  name        = "/jobpilot/db_password"
  description = "JobPilot RDS password"
  type        = "SecureString"
  value       = var.db_password
  key_id      = "alias/aws/ssm"
}

resource "aws_ssm_parameter" "github_token" {
  name        = "/jobpilot/github_token"
  description = "GitHub token for cloning JobPilot"
  type        = "SecureString"
  value       = var.github_token
  key_id      = "alias/aws/ssm"
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "jobpilot_ec2" {
  name               = "jobpilot-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

data "aws_kms_key" "ssm_default" {
  key_id = "alias/aws/ssm"
}

data "aws_iam_policy_document" "ec2_ssm_logs" {
  statement {
    sid = "SSMParametersJobpilot"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
    ]
    resources = [
      "arn:aws:ssm:*:*:parameter/jobpilot/*",
    ]
  }

  statement {
    sid = "DecryptSSMWithDefaultKey"
    actions = [
      "kms:Decrypt",
    ]
    resources = [data.aws_kms_key.ssm_default.arn]
  }

  statement {
    sid = "CloudWatchLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "jobpilot_ec2_inline" {
  name   = "jobpilot-ec2-ssm-logs"
  role   = aws_iam_role.jobpilot_ec2.id
  policy = data.aws_iam_policy_document.ec2_ssm_logs.json
}

resource "aws_iam_instance_profile" "jobpilot_ec2" {
  name = "jobpilot-ec2-profile"
  role = aws_iam_role.jobpilot_ec2.name
}
