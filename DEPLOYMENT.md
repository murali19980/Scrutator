# Scrutator Academic – Deployment Guide

## 🐳 Docker (Recommended)

### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+

### Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/murali19980/Scrutator.git
   cd Scrutator
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and supply your OPENROUTER_API_KEY and other parameters
   ```

3. **Build and run with Docker Compose**
   ```bash
   docker-compose up -d
   ```

4. **Access the services**
   - Web UI: http://localhost:7860
   - REST API: http://localhost:8000
   - Health Check: http://localhost:8000/health

---

## 🐧 Local Installation

### Prerequisites
- Python 3.10+

### Steps

1. **Clone and set up environment**
   ```bash
   git clone https://github.com/murali19980/Scrutator.git
   cd Scrutator
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -e .
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your keys
   ```

3. **Run the Web UI**
   ```bash
   python -m api.web_ui
   ```

4. **Run the CLI**
   ```bash
   python -m api.cli "quantum computing" --academic
   ```

---

## ☁️ Cloud Deployment

### Deploy to AWS EC2

1. Launch a `t3.medium` (or larger) instance running Ubuntu Server.
2. Install Docker and Docker Compose.
3. Clone the codebase, write `.env`, and launch `docker-compose up -d`.
4. Configure Security Group rules to expose ports `7860` (Web UI) and `8000` (REST API).

### Security Configurations

- **Basic Auth**: Ensure `SCRUTATOR_WEB_UI_USERNAME` and `SCRUTATOR_WEB_UI_PASSWORD` are specified in `.env` to restrict UI accessibility.
- **REST Keys**: Keep `SCRUTATOR_API_KEY` configured in `.env` for header validation (`X-API-Key`).
- **CORS Restrictions**: Set `CORS_ORIGINS` to your domain names (e.g., `https://yourui.com`) to block cross-origin browser exploits.
