resource "aws_secretsmanager_secret" "app_secrets" {
  name                    = "${var.app_name}-keys"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "app_secrets_version" {
  secret_id = aws_secretsmanager_secret.app_secrets.id
  secret_string = jsonencode({
    OPENAI_API_KEY = var.openai_api_key,
    MONGODB_URI    = var.mongodb_uri
  })
}
