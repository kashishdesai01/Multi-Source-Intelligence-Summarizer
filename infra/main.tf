terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  backend "s3" {
    bucket = "multidoc-terraform-state"
    key    = "prod/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region
}

module "ecr" {
  source   = "./modules/ecr"
  app_name = var.app_name
}

module "networking" {
  source   = "./modules/networking"
  app_name = var.app_name
}

module "secrets" {
  source           = "./modules/secrets"
  app_name         = var.app_name
  openai_api_key   = var.openai_api_key
  mongodb_uri      = var.mongodb_uri
}

module "ecs" {
  source           = "./modules/ecs"
  app_name         = var.app_name
  aws_region       = var.aws_region
  ecr_repo_url     = module.ecr.repo_url
  image_tag        = var.image_tag
  vpc_id           = module.networking.vpc_id
  public_subnets   = module.networking.public_subnets
  private_subnets  = module.networking.private_subnets
  alb_sg_id        = module.networking.alb_sg_id
  ecs_sg_id        = module.networking.ecs_sg_id
  alb_arn          = module.networking.alb_arn
  secrets_arn      = module.secrets.secret_arn
}

module "s3_cloudfront" {
  source   = "./modules/s3_cloudfront"
  app_name = var.app_name
  alb_dns  = module.networking.alb_dns
}
