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
output "cloudfront_dist_id" {
  description = "CloudFront Distribution ID (For GitHub Secrets)"
  value       = module.s3_cloudfront.cloudfront_dist_id
}
output "frontend_bucket" {
  description = "S3 Frontend Bucket Name (For GitHub Secrets)"
  value       = module.s3_cloudfront.frontend_bucket
}
