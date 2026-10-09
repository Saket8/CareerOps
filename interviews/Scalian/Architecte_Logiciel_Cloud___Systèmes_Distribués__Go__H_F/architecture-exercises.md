# Whiteboard Architecture Exercises

## Exercise 1: Resilient Telecom GenAI CloudOps Platform
- **Objective:** Draw the end-to-end dataflow for an intelligent alerting pipeline that analyzes OCI logs, routes events to an air-gapped local LLM, and triggers automated remediation.
- **Key Components:** OCI Service Connector Hub, ONS (Notifications), Private OKE Worker Nodes, LangChain ChatOps agent, OCI Vault for secrets, Terraform IaC definitions.

## Exercise 2: Hybrid Multi-Cloud Network with Palo Alto VM-Series
- **Objective:** Design network topology connecting on-prem data centers to OCI and Azure with centralized egress inspection.
- **Key Components:** Dynamic Routing Gateway (DRG), IPSec VPN tunnels, Palo Alto VM-Series firewalls in inspection VCN, NLB route tables, FastConnect redundancy.
