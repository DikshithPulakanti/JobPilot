module "secrets" {
  source = "./modules/secrets"

  anthropic_api_key = var.anthropic_api_key
  openai_api_key    = var.openai_api_key
  db_password       = var.db_password
  github_token      = var.github_token
}

module "networking" {
  source = "./modules/networking"

  your_ip = var.your_ip
}

module "database" {
  source = "./modules/database"

  aws_region            = var.aws_region
  private_subnet_ids    = module.networking.private_subnet_ids
  rds_security_group_id = module.networking.sg_rds_id
  db_name               = var.db_name
  db_username           = var.db_username
  db_password           = var.db_password
  db_instance_class     = var.db_instance_class

  depends_on = [module.secrets]
}

module "backend" {
  source = "./modules/backend"

  aws_region                = var.aws_region
  public_subnet_id          = module.networking.public_subnet_ids[0]
  backend_security_group_id = module.networking.sg_backend_id
  ec2_instance_type         = var.ec2_instance_type
  iam_instance_profile_name = module.secrets.ec2_instance_profile_name
  rds_address               = module.database.rds_endpoint
  db_username               = var.db_username
  db_name                   = var.db_name

  depends_on = [module.database, module.secrets, module.networking]
}

module "frontend" {
  source = "./modules/frontend"

  ec2_public_dns = module.backend.ec2_public_dns

  depends_on = [module.backend]
}
