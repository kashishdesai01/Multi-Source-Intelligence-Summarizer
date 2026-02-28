output "cloudfront_url" {
  value = aws_cloudfront_distribution.cdn.domain_name
}
output "cloudfront_dist_id" {
  value = aws_cloudfront_distribution.cdn.id
}
output "frontend_bucket" {
  value = aws_s3_bucket.frontend.id
}
