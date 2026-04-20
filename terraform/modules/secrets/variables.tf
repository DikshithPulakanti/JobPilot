variable "anthropic_api_key" {
  type      = string
  sensitive = true
}

variable "openai_api_key" {
  type      = string
  sensitive = true
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "github_token" {
  type      = string
  sensitive = true
}
