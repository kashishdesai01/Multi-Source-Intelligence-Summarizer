output "cloudfront_url" {
  description = "Frontend CloudFront URL"
  value       = module.s3_cloudfront.cloudfront_url
}
output "alb_dns" {
  description = "Backend Application Load Balancer DNS"
  value       = module.networking.alb_dns
}
output "ecr_repo_url" {
  description = "ECR repository URL for Docker pushes"
  value       = module.ecr.repo_url
}
