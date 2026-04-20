#!/bin/bash
set -euxo pipefail

dnf install -y python3.11 python3.11-pip git curl

curl -fsSL https://rpm.nodesource.com/setup_18.x | bash -
dnf install -y nodejs

export ANTHROPIC_API_KEY=$(aws ssm get-parameter \
  --name /jobpilot/anthropic_api_key --with-decryption \
  --query Parameter.Value --output text --region ${aws_region})
export OPENAI_API_KEY=$(aws ssm get-parameter \
  --name /jobpilot/openai_api_key --with-decryption \
  --query Parameter.Value --output text --region ${aws_region})
export GITHUB_TOKEN=$(aws ssm get-parameter \
  --name /jobpilot/github_token --with-decryption \
  --query Parameter.Value --output text --region ${aws_region})
export DB_PASSWORD=$(aws ssm get-parameter \
  --name /jobpilot/db_password --with-decryption \
  --query Parameter.Value --output text --region ${aws_region})

git clone "https://$GITHUB_TOKEN@github.com/DikshithPulakanti/JobPilot.git" /home/ec2-user/JobPilot
chown -R ec2-user:ec2-user /home/ec2-user/JobPilot

cd /home/ec2-user/JobPilot/backend
python3.11 -m pip install -r requirements.txt

python3.11 -m playwright install-deps chromium
python3.11 -m playwright install chromium

sudo -u ec2-user bash -c 'cd /home/ec2-user/JobPilot/frontend && npm install && npm run build'
sudo -u ec2-user bash -c 'cd /home/ec2-user/JobPilot/frontend && nohup npm start -- --port 3000 >> /home/ec2-user/frontend.log 2>&1 &'

mkdir -p /var/log/jobpilot
chown ec2-user:ec2-user /var/log/jobpilot

cat >/home/ec2-user/JobPilot/backend/.env <<ENVFILE
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
OPENAI_API_KEY=$OPENAI_API_KEY
DATABASE_URL=postgresql://${db_username}:$DB_PASSWORD@${rds_address}:5432/${db_name}
PLAYWRIGHT_HEADLESS=true
JOBPILOT_MAX_APPLICATIONS_PER_RUN=0
NEXT_PUBLIC_API_URL=http://${elastic_ip}:8000
ENVFILE
chown ec2-user:ec2-user /home/ec2-user/JobPilot/backend/.env
chmod 600 /home/ec2-user/JobPilot/backend/.env

cat >/etc/systemd/system/jobpilot.service <<'UNIT'
[Unit]
Description=JobPilot FastAPI
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/JobPilot/backend
EnvironmentFile=/home/ec2-user/JobPilot/backend/.env
ExecStart=/usr/local/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=append:/var/log/jobpilot/uvicorn.log
StandardError=append:/var/log/jobpilot/uvicorn.log

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable jobpilot
systemctl start jobpilot

dnf install -y amazon-cloudwatch-agent

cat >/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<CWCFG
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/jobpilot/uvicorn.log",
            "log_group_name": "/jobpilot/backend",
            "log_stream_name": "{instance_id}"
          }
        ]
      }
    }
  }
}
CWCFG

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
