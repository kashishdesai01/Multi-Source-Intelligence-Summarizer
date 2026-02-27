variable "app_name"      { default = "multidoc-summarizer" }
variable "aws_region"    { default = "us-east-1" }
variable "image_tag"     { default = "latest" }
variable "openai_api_key" {
  description = "OpenAI API key — stored in Secrets Manager"
  sensitive   = true
}
variable "mongodb_uri" {
  description = "MongoDB Atlas connection string"
  sensitive   = true
}
