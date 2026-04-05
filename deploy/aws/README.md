# Deploy Morgenruf on AWS

## 🚀 One-Click Deploy

### Starter (~$15/mo) — Single EC2 instance
Best for small teams. Runs docker-compose on a single server.

[![Launch Starter Stack](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home#/stacks/new?stackName=morgenruf-starter&templateURL=https://raw.githubusercontent.com/morgenruf/morgenruf/main/deploy/aws/starter.yaml)

**What gets created:**
- EC2 t3.small (Amazon Linux 2023)
- PostgreSQL 16 in Docker
- Nginx reverse proxy
- Elastic IP

**After deploy:**
1. Copy the `PublicIP` from stack Outputs
2. Point your domain's A record → that IP
3. SSH in and run: `cd /opt/morgenruf && certbot --nginx -d yourdomain.com`
4. Add `https://yourdomain.com/slack/oauth_redirect` to Slack app redirect URLs
5. Visit `https://yourdomain.com` to install the bot

---

### Production (~$25/mo) — ECS Fargate Spot + RDS
Zero server management. Auto-healing. Recommended for teams that need reliability.

[![Launch Production Stack](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home#/stacks/new?stackName=morgenruf-prod&templateURL=https://raw.githubusercontent.com/morgenruf/morgenruf/main/deploy/aws/production.yaml)

**What gets created:**
- ECS Fargate Spot task (256 CPU / 512MB RAM)
- RDS PostgreSQL t4g.micro (private subnet)
- Application Load Balancer + HTTPS
- Secrets Manager for credentials
- CloudWatch Logs

**Prerequisites:**
- ACM certificate for your domain (free via AWS Certificate Manager)
- Get ARN from ACM console → paste as `CertificateArn` parameter

**After deploy:**
1. Copy `ALBDNSName` from Outputs
2. Create CNAME: `yourdomain.com` → ALBDNSName
3. Add redirect URL to Slack app
4. Visit your domain to install

---

## Cost Breakdown

| Resource | Starter | Production |
|----------|---------|------------|
| Compute | EC2 t3.small ~$13 | Fargate Spot ~$3 |
| Database | Docker postgres $0 | RDS t4g.micro ~$13 |
| Load Balancer | Nginx (included) | ALB ~$16 |
| Storage | 20GB gp3 ~$1.6 | 20GB gp3 ~$2.3 |
| **Total** | **~$15/mo** | **~$25/mo** |

> Prices based on us-east-1. [AWS Pricing Calculator](https://calculator.aws)

---

## Parameters Reference

| Parameter | Required | Description |
|-----------|----------|-------------|
| `SlackClientId` | ✅ | Slack App → Basic Information → Client ID |
| `SlackClientSecret` | ✅ | 32-char hex secret |
| `SlackSigningSecret` | ✅ | 32-char hex signing secret |
| `AppDomain` | ✅ | Your domain e.g. `standup.mycompany.com` |
| `DBPassword` | ✅ | Min 12 chars |
| `FlaskSecretKey` | ❌ | Auto-generated if blank |
| `InstanceType` | ❌ | Starter only. Default: t3.small |
| `KeyPairName` | ❌ | Starter only. For SSH access |
| `CertificateArn` | ✅ | Production only. ACM cert ARN |

---

## Updating

**Starter:**
```bash
ssh ec2-user@YOUR_IP
cd /opt/morgenruf
docker-compose pull && docker-compose up -d
```

**Production:**
```bash
aws ecs update-service --cluster morgenruf --service morgenruf --force-new-deployment
```
